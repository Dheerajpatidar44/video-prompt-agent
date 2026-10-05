"""Deterministic, rule-based Prompt Reviewer.

Every check is pure Python / regex / rapidfuzz / spaCy — **no LLM calls**.
The reviewer never blocks the pipeline; it reports issues so the corrector
can resolve them.
"""
import re
import uuid
import logging
from math import isclose
from typing import List, Set, Dict, Optional

from app.schemas.generated_prompt import GeneratedPrompt, PromptSet
from app.schemas.scene_plan import MasterScenePlan, ScenePlan, ShotPlan
from app.schemas.specification import VideoSpecification
from app.schemas.review_report import (
    ReviewIssue, ReviewReport, ReviewStatus,
    IssueSeverity, IssueCategory,
)
from app.validators.text_utils import extract_descriptors, find_conflicting_attributes

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------
INTERNAL_ID_PATTERNS = [
    re.compile(r"\bshot_\d+\b", re.IGNORECASE),
    re.compile(r"\bscene_\d+\b", re.IGNORECASE),
    re.compile(r"\bprompt_\d+\b", re.IGNORECASE),
    re.compile(r"\bchar_\w+\b", re.IGNORECASE),
    re.compile(r"\bloc_\w+\b", re.IGNORECASE),
    re.compile(r"\bprod_\w+\b", re.IGNORECASE),
]

PLACEHOLDER_PATTERNS = [
    re.compile(r"\bTODO\b", re.IGNORECASE),
    re.compile(r"\[INSERT", re.IGNORECASE),
    re.compile(r"\{\{"),
    re.compile(r"\blorem ipsum\b", re.IGNORECASE),
    re.compile(r"(?:^|\s)#{2,}\s", re.MULTILINE),   # markdown headings
    re.compile(r"\*\*[^*]+\*\*"),                     # markdown bold
]

HALLUCINATED_CAMERA_PATTERNS = [
    re.compile(r"\b\d+\s*mm\b", re.IGNORECASE),
    re.compile(r"\bf/\d+(?:\.\d+)?\b", re.IGNORECASE),
    re.compile(r"\bISO\s*\d+\b", re.IGNORECASE),
    re.compile(r"\bshutter speed\b", re.IGNORECASE),
    re.compile(r"\baperture\b", re.IGNORECASE),
    re.compile(r"\bsensor size\b", re.IGNORECASE),
]

# Dialogue detection: look for quoted text after speech verbs
DIALOGUE_PATTERN = re.compile(
    r'(?:says?|speaks?|speaking|whispers?|shouts?|exclaims?|murmurs?|asks?|replies?|announces?)\s*[,:]*\s*["\u201c]([^"\u201d]+)["\u201d]',
    re.IGNORECASE,
)

# Audio/voice direction markers in prompt text
AUDIO_MARKERS = re.compile(
    r"\b(?:audio|voiceover|voice-over|lip[- ]?sync|dialogue|narrat(?:es?|ion)|speaks?|says?)\b",
    re.IGNORECASE,
)

# Tools known to support audio generation
TOOLS_WITH_AUDIO: Set[str] = {"Veo"}


def _uid() -> str:
    return str(uuid.uuid4())[:8]


class PromptReviewer:
    """Run all deterministic QA checks and return a ReviewReport."""

    def __init__(
        self,
        spec: VideoSpecification,
        scene_plan: MasterScenePlan,
        prompt_set: PromptSet,
        original_script: str,
        selected_tool: str = "Veo",
    ):
        self.spec = spec
        self.scene_plan = scene_plan
        self.prompt_set = prompt_set
        self.original_script = original_script
        self.selected_tool = selected_tool

        # Build lookup maps
        self._shot_map: Dict[str, ShotPlan] = {}
        self._scene_map: Dict[str, ScenePlan] = {}
        self._shot_to_scene: Dict[str, ScenePlan] = {}
        for scene in scene_plan.scenes:
            self._scene_map[scene.scene_id] = scene
            for shot in scene.shots:
                self._shot_map[shot.shot_id] = shot
                self._shot_to_scene[shot.shot_id] = scene

        self._prompt_map: Dict[str, GeneratedPrompt] = {
            p.prompt_id: p for p in prompt_set.prompts
        }

        # Spec entity IDs for cross-referencing
        self._character_ids: Set[str] = {c.id for c in spec.characters}
        self._location_ids: Set[str] = {l.id for l in spec.locations}
        self._product_ids: Set[str] = {p.id for p in spec.products}

        # Camera spec string for hallucination cross-check
        self._spec_camera_str = ""
        if spec.camera:
            self._spec_camera_str = str(spec.camera.model_dump()).lower()

    # -------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------
    def run_all_checks(self) -> ReviewReport:
        issues: List[ReviewIssue] = []

        issues.extend(self._check_structural())
        issues.extend(self._check_content_quality())
        issues.extend(self._check_continuity_drift())
        issues.extend(self._check_dialogue_timing())
        issues.extend(self._check_tool_compatibility())

        total_checks = 5
        severity_counts = {"BLOCKER": 0, "WARNING": 0, "INFO": 0}
        for iss in issues:
            severity_counts[iss.severity.value] += 1

        if not issues:
            status = ReviewStatus.PASSED
        elif severity_counts["BLOCKER"] > 0:
            # Will be resolved to PASSED_WITH_FIXES after correction stage
            status = ReviewStatus.PASSED_WITH_WARNINGS
        else:
            status = ReviewStatus.PASSED_WITH_WARNINGS

        return ReviewReport(
            status=status,
            issues=issues,
            stats={
                "total_prompts": len(self.prompt_set.prompts),
                "total_checks_run": total_checks,
                "issues_by_severity": severity_counts,
            },
        )

    # -------------------------------------------------------------------
    # Category A — Structural / Schema Checks
    # -------------------------------------------------------------------
    def _check_structural(self) -> List[ReviewIssue]:
        issues: List[ReviewIssue] = []

        # A1: Scene duration sums
        for scene in self.scene_plan.scenes:
            shot_sum = sum(sh.duration_seconds for sh in scene.shots)
            if not isclose(shot_sum, scene.duration_seconds, abs_tol=0.5):
                issues.append(ReviewIssue(
                    issue_id=f"STRUCT-{_uid()}",
                    severity=IssueSeverity.BLOCKER,
                    category=IssueCategory.STRUCTURAL,
                    scene_id=scene.scene_id,
                    field="duration_seconds",
                    message=f"Sum of shot durations ({shot_sum:.2f}s) != scene duration ({scene.duration_seconds:.2f}s).",
                    detected_value=f"{shot_sum:.2f}",
                    expected_value=f"{scene.duration_seconds:.2f}",
                ))

        # A2: Total duration consistency
        scene_sum = sum(s.duration_seconds for s in self.scene_plan.scenes)
        if not isclose(scene_sum, self.scene_plan.total_duration, abs_tol=0.5):
            issues.append(ReviewIssue(
                issue_id=f"STRUCT-{_uid()}",
                severity=IssueSeverity.BLOCKER,
                category=IssueCategory.STRUCTURAL,
                field="total_duration",
                message=f"Sum of scene durations ({scene_sum:.2f}s) != plan total ({self.scene_plan.total_duration:.2f}s).",
                detected_value=f"{scene_sum:.2f}",
                expected_value=f"{self.scene_plan.total_duration:.2f}",
            ))

        # A3: Entity ID validation (character, location, product)
        for scene in self.scene_plan.scenes:
            if scene.location_id and scene.location_id not in self._location_ids:
                issues.append(ReviewIssue(
                    issue_id=f"STRUCT-{_uid()}",
                    severity=IssueSeverity.BLOCKER,
                    category=IssueCategory.STRUCTURAL,
                    scene_id=scene.scene_id,
                    field="location_id",
                    message=f"Scene references unknown location_id '{scene.location_id}'.",
                    detected_value=scene.location_id,
                ))
            for cid in scene.character_ids:
                if cid not in self._character_ids:
                    issues.append(ReviewIssue(
                        issue_id=f"STRUCT-{_uid()}",
                        severity=IssueSeverity.BLOCKER,
                        category=IssueCategory.STRUCTURAL,
                        scene_id=scene.scene_id,
                        field="character_ids",
                        message=f"Scene references unknown character_id '{cid}'.",
                        detected_value=cid,
                    ))
            for pid in scene.product_ids:
                if pid not in self._product_ids:
                    issues.append(ReviewIssue(
                        issue_id=f"STRUCT-{_uid()}",
                        severity=IssueSeverity.BLOCKER,
                        category=IssueCategory.STRUCTURAL,
                        scene_id=scene.scene_id,
                        field="product_ids",
                        message=f"Scene references unknown product_id '{pid}'.",
                        detected_value=pid,
                    ))

        # A4: Duplicate prompt_id / shot_id
        seen_prompt_ids: Set[str] = set()
        seen_shot_ids: Set[str] = set()
        for p in self.prompt_set.prompts:
            if p.prompt_id in seen_prompt_ids:
                issues.append(ReviewIssue(
                    issue_id=f"STRUCT-{_uid()}",
                    severity=IssueSeverity.BLOCKER,
                    category=IssueCategory.STRUCTURAL,
                    prompt_id=p.prompt_id,
                    field="prompt_id",
                    message=f"Duplicate prompt_id '{p.prompt_id}'.",
                    detected_value=p.prompt_id,
                ))
            seen_prompt_ids.add(p.prompt_id)

            if p.shot_id in seen_shot_ids:
                issues.append(ReviewIssue(
                    issue_id=f"STRUCT-{_uid()}",
                    severity=IssueSeverity.BLOCKER,
                    category=IssueCategory.STRUCTURAL,
                    prompt_id=p.prompt_id,
                    shot_id=p.shot_id,
                    field="shot_id",
                    message=f"Duplicate shot_id '{p.shot_id}' across prompts.",
                    detected_value=p.shot_id,
                ))
            seen_shot_ids.add(p.shot_id)

        # A5: Contiguous sequence_number
        sorted_prompts = sorted(self.prompt_set.prompts, key=lambda p: p.sequence_number)
        for i, p in enumerate(sorted_prompts):
            expected_seq = i + 1
            if p.sequence_number != expected_seq:
                issues.append(ReviewIssue(
                    issue_id=f"STRUCT-{_uid()}",
                    severity=IssueSeverity.BLOCKER,
                    category=IssueCategory.STRUCTURAL,
                    prompt_id=p.prompt_id,
                    field="sequence_number",
                    message=f"sequence_number gap: expected {expected_seq}, got {p.sequence_number}.",
                    detected_value=str(p.sequence_number),
                    expected_value=str(expected_seq),
                ))

        # A6: Required fields not null/empty
        for p in self.prompt_set.prompts:
            for field_name in ("prompt_text", "shot_id", "scene_id"):
                val = getattr(p, field_name, None)
                if not val or (isinstance(val, str) and not val.strip()):
                    issues.append(ReviewIssue(
                        issue_id=f"STRUCT-{_uid()}",
                        severity=IssueSeverity.BLOCKER,
                        category=IssueCategory.STRUCTURAL,
                        prompt_id=p.prompt_id,
                        field=field_name,
                        message=f"Required field '{field_name}' is null or empty.",
                    ))
            if p.duration_seconds is None or p.duration_seconds <= 0:
                issues.append(ReviewIssue(
                    issue_id=f"STRUCT-{_uid()}",
                    severity=IssueSeverity.BLOCKER,
                    category=IssueCategory.STRUCTURAL,
                    prompt_id=p.prompt_id,
                    field="duration_seconds",
                    message=f"duration_seconds is missing or non-positive ({p.duration_seconds}).",
                    detected_value=str(p.duration_seconds),
                ))

        return issues

    # -------------------------------------------------------------------
    # Category B — Content Quality Checks
    # -------------------------------------------------------------------
    def _check_content_quality(self) -> List[ReviewIssue]:
        issues: List[ReviewIssue] = []

        for p in self.prompt_set.prompts:
            text_fields = {
                "prompt_text": p.prompt_text or "",
                "negative_constraints": p.negative_constraints or "",
            }

            for field_name, text in text_fields.items():
                if not text.strip():
                    continue

                # B1: Internal ID leakage
                for pattern in INTERNAL_ID_PATTERNS:
                    match = pattern.search(text)
                    if match:
                        issues.append(ReviewIssue(
                            issue_id=f"QUAL-{_uid()}",
                            severity=IssueSeverity.BLOCKER,
                            category=IssueCategory.CONTENT_QUALITY,
                            prompt_id=p.prompt_id,
                            shot_id=p.shot_id,
                            scene_id=p.scene_id,
                            field=field_name,
                            message=f"Internal ID '{match.group(0)}' leaked into {field_name}.",
                            detected_value=match.group(0),
                            auto_fixable=True,
                        ))

                # B2: Placeholder / incomplete text
                for pattern in PLACEHOLDER_PATTERNS:
                    match = pattern.search(text)
                    if match:
                        issues.append(ReviewIssue(
                            issue_id=f"QUAL-{_uid()}",
                            severity=IssueSeverity.BLOCKER,
                            category=IssueCategory.CONTENT_QUALITY,
                            prompt_id=p.prompt_id,
                            shot_id=p.shot_id,
                            field=field_name,
                            message=f"Placeholder/incomplete text detected: '{match.group(0)}'.",
                            detected_value=match.group(0),
                            auto_fixable=True,
                        ))

            # B3: Hallucinated camera parameters (in prompt_text only)
            if p.prompt_text:
                for pattern in HALLUCINATED_CAMERA_PATTERNS:
                    match = pattern.search(p.prompt_text)
                    if match:
                        matched_text = match.group(0).lower()
                        if matched_text not in self._spec_camera_str:
                            issues.append(ReviewIssue(
                                issue_id=f"QUAL-{_uid()}",
                                severity=IssueSeverity.WARNING,
                                category=IssueCategory.CONTENT_QUALITY,
                                prompt_id=p.prompt_id,
                                shot_id=p.shot_id,
                                field="prompt_text",
                                message=f"Possibly hallucinated camera parameter: '{match.group(0)}'.",
                                detected_value=match.group(0),
                                auto_fixable=True,
                            ))

            # B4: Redundant negative constraints (rapidfuzz)
            if p.negative_constraints and p.negative_constraints.strip():
                try:
                    from rapidfuzz import fuzz
                    sentences = [
                        s.strip()
                        for s in re.split(r"[.;,\n]", p.negative_constraints)
                        if s.strip() and len(s.strip()) > 5
                    ]
                    for i in range(len(sentences)):
                        for j in range(i + 1, len(sentences)):
                            score = fuzz.token_set_ratio(sentences[i], sentences[j])
                            if score > 75:
                                issues.append(ReviewIssue(
                                    issue_id=f"QUAL-{_uid()}",
                                    severity=IssueSeverity.WARNING,
                                    category=IssueCategory.CONTENT_QUALITY,
                                    prompt_id=p.prompt_id,
                                    shot_id=p.shot_id,
                                    field="negative_constraints",
                                    message=f"Possibly redundant constraints (similarity {score}%): '{sentences[i][:40]}...' vs '{sentences[j][:40]}...'",
                                    detected_value=f"{sentences[i]} | {sentences[j]}",
                                    auto_fixable=True,
                                ))
                except ImportError:
                    logger.warning("rapidfuzz not installed — skipping redundancy check.")

            # B5: Prompt length sanity (too short)
            if p.prompt_text:
                word_count = len(p.prompt_text.split())
                if word_count < 20:
                    issues.append(ReviewIssue(
                        issue_id=f"QUAL-{_uid()}",
                        severity=IssueSeverity.WARNING,
                        category=IssueCategory.CONTENT_QUALITY,
                        prompt_id=p.prompt_id,
                        shot_id=p.shot_id,
                        field="prompt_text",
                        message=f"Prompt text is suspiciously short ({word_count} words).",
                        detected_value=str(word_count),
                        expected_value="≥20 words",
                    ))

        return issues

    # -------------------------------------------------------------------
    # Category C — Continuity / Entity Drift Checks (Pure Python + rapidfuzz)
    # -------------------------------------------------------------------
    def _check_continuity_drift(self) -> List[ReviewIssue]:
        issues: List[ReviewIssue] = []
        
        try:
            from rapidfuzz import fuzz
        except ImportError:
            logger.warning("rapidfuzz not installed — continuity drift checks will be skipped.")
            return issues

        # Build entity → list of (shot_id, descriptor_tokens) across shots
        entity_descriptors: Dict[str, List[tuple]] = {}  # entity_id -> [(shot_id, {tokens})]

        for p in self.prompt_set.prompts:
            scene = self._shot_to_scene.get(p.shot_id)
            if not scene:
                continue

            # Pure Python descriptor extraction
            tokens = extract_descriptors(p.prompt_text or "")

            # Map tokens to each character/product in the parent scene
            for cid in scene.character_ids:
                entity_descriptors.setdefault(cid, []).append((p.shot_id, tokens))
            for pid in scene.product_ids:
                entity_descriptors.setdefault(pid, []).append((p.shot_id, tokens))

        # Compare descriptor sets across shots for the same entity
        for entity_id, shot_tokens_list in entity_descriptors.items():
            if len(shot_tokens_list) < 2:
                continue

            # Use first shot's descriptors as the baseline
            baseline_shot_id, baseline_tokens = shot_tokens_list[0]
            if not baseline_tokens:
                continue
                
            baseline_text = " ".join(sorted(baseline_tokens))

            for shot_id, tokens in shot_tokens_list[1:]:
                if not tokens:
                    continue
                    
                # 1. Check for direct high-confidence attribute conflicts (e.g. blonde vs brunette)
                unique_base_attrs, unique_shot_attrs = find_conflicting_attributes(baseline_tokens, tokens)
                
                if unique_base_attrs and unique_shot_attrs:
                    # We have known vocab terms on both sides that don't match
                    issues.append(ReviewIssue(
                        issue_id=f"CONT-{_uid()}",
                        severity=IssueSeverity.WARNING,
                        category=IssueCategory.CONTINUITY_DRIFT,
                        shot_id=shot_id,
                        field="prompt_text",
                        message=(
                            f"Entity '{entity_id}' has conflicting core attributes in shot '{shot_id}' "
                            f"vs baseline '{baseline_shot_id}'."
                        ),
                        detected_value=", ".join(sorted(unique_shot_attrs)),
                        expected_value=", ".join(sorted(unique_base_attrs)),
                    ))
                    continue # Skip general fuzz score if we already flagged a hard conflict
                
                # 2. General fuzzy similarity on all descriptors
                shot_text = " ".join(sorted(tokens))
                # using token_set_ratio because it handles partial overlaps gracefully
                score = fuzz.token_set_ratio(baseline_text, shot_text)
                
                # Only flag if similarity is very low (< 40) AND both have meaningful descriptor counts
                if score < 40 and len(baseline_tokens) >= 3 and len(tokens) >= 3:
                    issues.append(ReviewIssue(
                        issue_id=f"CONT-{_uid()}",
                        severity=IssueSeverity.WARNING,
                        category=IssueCategory.CONTINUITY_DRIFT,
                        shot_id=shot_id,
                        field="prompt_text",
                        message=(
                            f"Entity '{entity_id}' descriptors in shot '{shot_id}' diverge "
                            f"significantly from baseline '{baseline_shot_id}' "
                            f"(similarity: {score:.1f}%)."
                        ),
                        detected_value=", ".join(sorted(tokens)[:10]),
                        expected_value=", ".join(sorted(baseline_tokens)[:10]),
                    ))

        return issues

    # -------------------------------------------------------------------
    # Category D — Dialogue & Timing Checks
    # -------------------------------------------------------------------
    def _check_dialogue_timing(self) -> List[ReviewIssue]:
        issues: List[ReviewIssue] = []
        WORDS_PER_SECOND = 2.75  # average speaking pace
        OVERRUN_THRESHOLD = 1.15  # 15% margin

        for p in self.prompt_set.prompts:
            if not p.prompt_text:
                continue

            # Extract dialogue from prompt text
            matches = DIALOGUE_PATTERN.findall(p.prompt_text)
            if not matches:
                continue

            for dialogue_line in matches:
                word_count = len(dialogue_line.split())
                estimated_speech_seconds = word_count / WORDS_PER_SECOND

                # D1: Speech duration exceeds shot duration
                if estimated_speech_seconds > p.duration_seconds * OVERRUN_THRESHOLD:
                    issues.append(ReviewIssue(
                        issue_id=f"DIAL-{_uid()}",
                        severity=IssueSeverity.BLOCKER,
                        category=IssueCategory.DIALOGUE_TIMING,
                        prompt_id=p.prompt_id,
                        shot_id=p.shot_id,
                        field="prompt_text",
                        message=(
                            f"Dialogue ({word_count} words, ~{estimated_speech_seconds:.1f}s) "
                            f"exceeds shot duration ({p.duration_seconds:.1f}s) by >{int((OVERRUN_THRESHOLD-1)*100)}%."
                        ),
                        detected_value=f"{estimated_speech_seconds:.1f}s for '{dialogue_line[:50]}...'",
                        expected_value=f"≤{p.duration_seconds:.1f}s",
                    ))

                # D2: Check if dialogue exists in original script (invented dialogue detection)
                if self.original_script and len(dialogue_line) > 10:
                    try:
                        from rapidfuzz import fuzz
                        # Check if this dialogue line fuzzy-matches anything in the script
                        best_score = fuzz.partial_ratio(
                            dialogue_line.lower(), self.original_script.lower()
                        )
                        if best_score < 85:
                            issues.append(ReviewIssue(
                                issue_id=f"DIAL-{_uid()}",
                                severity=IssueSeverity.WARNING,
                                category=IssueCategory.DIALOGUE_TIMING,
                                prompt_id=p.prompt_id,
                                shot_id=p.shot_id,
                                field="prompt_text",
                                message=f"Dialogue line may be invented (not found in original script, match={best_score}%).",
                                detected_value=dialogue_line[:80],
                            ))
                    except ImportError:
                        pass

        return issues

    # -------------------------------------------------------------------
    # Category E — Tool Compatibility Checks
    # -------------------------------------------------------------------
    def _check_tool_compatibility(self) -> List[ReviewIssue]:
        issues: List[ReviewIssue] = []

        tool = self.selected_tool
        tool_supports_audio = tool in TOOLS_WITH_AUDIO

        if tool_supports_audio:
            return issues  # no compatibility issues if tool supports audio

        for p in self.prompt_set.prompts:
            if not p.prompt_text:
                continue

            if AUDIO_MARKERS.search(p.prompt_text):
                issues.append(ReviewIssue(
                    issue_id=f"TOOL-{_uid()}",
                    severity=IssueSeverity.WARNING,
                    category=IssueCategory.TOOL_COMPATIBILITY,
                    prompt_id=p.prompt_id,
                    shot_id=p.shot_id,
                    field="prompt_text",
                    message=f"Prompt contains audio/dialogue direction but target tool '{tool}' may not support audio generation.",
                    detected_value=AUDIO_MARKERS.search(p.prompt_text).group(0) if AUDIO_MARKERS.search(p.prompt_text) else None,
                ))

        return issues
