"""Prompt Corrector — auto-fix + targeted LLM patch fallback.

Implements the Fallback Chain:
1. Auto-fix (Python string manipulation) for auto_fixable issues.
2. One targeted LLM patch attempt for remaining BLOCKERs.
3. A second stricter LLM patch attempt if still unresolved.
4. Deterministic safe simplification as final fallback.

The corrector NEVER blocks — it always returns a usable PromptSet.
"""
import re
import copy
import logging
from typing import Optional

from app.schemas.generated_prompt import GeneratedPrompt, PromptSet
from app.schemas.specification import VideoSpecification
from app.schemas.review_report import (
    ReviewIssue, ReviewReport, ReviewStatus,
    IssueSeverity, IssueCategory,
)
from app.prompts.prompt_patch import PROMPT_PATCH_PROMPT, PromptPatchResult

logger = logging.getLogger(__name__)

# Maximum total LLM patch calls per generation run
MAX_LLM_PATCH_CALLS = 6

# Regex patterns matching internal IDs to strip
_INTERNAL_ID_RE = [
    re.compile(r"\bshot_\d+\b", re.IGNORECASE),
    re.compile(r"\bscene_\d+\b", re.IGNORECASE),
    re.compile(r"\bprompt_\d+\b", re.IGNORECASE),
    re.compile(r"\bchar_\w+\b", re.IGNORECASE),
    re.compile(r"\bloc_\w+\b", re.IGNORECASE),
    re.compile(r"\bprod_\w+\b", re.IGNORECASE),
]

# Placeholder artifacts to strip
_PLACEHOLDER_RE = [
    re.compile(r"\bTODO\b[^.]*\.?\s*", re.IGNORECASE),
    re.compile(r"\[INSERT[^\]]*\]\s*", re.IGNORECASE),
    re.compile(r"\{\{[^}]*\}\}\s*"),
    re.compile(r"\blorem ipsum[^.]*\.?\s*", re.IGNORECASE),
    re.compile(r"(?:^|\n)\s*#{2,}[^\n]*\n?", re.MULTILINE),
    re.compile(r"\*\*([^*]+)\*\*"),  # unwrap markdown bold, keeping inner text
]


def _strip_internal_ids(text: str) -> str:
    """Remove internal ID patterns from text."""
    for pattern in _INTERNAL_ID_RE:
        text = pattern.sub("", text)
    return re.sub(r"\s{2,}", " ", text).strip()


def _strip_placeholders(text: str) -> str:
    """Remove placeholder/incomplete text artifacts."""
    for i, pattern in enumerate(_PLACEHOLDER_RE):
        if i == len(_PLACEHOLDER_RE) - 1:
            # markdown bold: replace **word** with word
            text = pattern.sub(r"\1", text)
        else:
            text = pattern.sub("", text)
    return re.sub(r"\s{2,}", " ", text).strip()


def _deduplicate_negative_constraints(text: str) -> str:
    """Remove near-duplicate sentences from negative_constraints."""
    try:
        from rapidfuzz import fuzz
    except ImportError:
        return text

    sentences = [s.strip() for s in re.split(r"[.;,\n]", text) if s.strip() and len(s.strip()) > 5]
    if len(sentences) <= 1:
        return text
 
    keep = [sentences[0]]
    for s in sentences[1:]:
        is_dup = False
        for kept in keep:
            if fuzz.token_set_ratio(s, kept) > 75:
                is_dup = True
                break
        if not is_dup:
            keep.append(s)

    return ". ".join(keep) + "." if keep else text


def _strip_hallucinated_camera(text: str, spec_camera_str: str) -> str:
    """Remove hallucinated camera parameters not in the spec."""
    patterns = [
        re.compile(r"\b\d+\s*mm\b", re.IGNORECASE),
        re.compile(r"\bf/\d+(?:\.\d+)?\b", re.IGNORECASE),
        re.compile(r"\bISO\s*\d+\b", re.IGNORECASE),
    ]
    for pattern in patterns:
        match = pattern.search(text)
        if match and match.group(0).lower() not in spec_camera_str:
            text = pattern.sub("", text)
    return re.sub(r"\s{2,}", " ", text).strip()


def _get_continuity_context(spec: VideoSpecification, issue: ReviewIssue) -> str:
    """Extract relevant continuity context for a targeted LLM patch."""
    parts = []

    # Include continuity bible info for the relevant entity
    if spec.continuity_bible:
        for char in spec.continuity_bible.characters:
            parts.append(f"Character '{char.id}' ({char.name}): appearance={char.appearance}, clothing={char.clothing}, hair={char.hairstyle}")
        for prod in spec.continuity_bible.products:
            parts.append(f"Product '{prod.id}' ({prod.name}): appearance={prod.appearance}, color={prod.color}")
        for loc in spec.continuity_bible.locations:
            parts.append(f"Location '{loc.id}' ({loc.name}): description={loc.description}, atmosphere={loc.atmosphere}")
        if spec.continuity_bible.wardrobe_notes:
            parts.append(f"Wardrobe notes: {'; '.join(spec.continuity_bible.wardrobe_notes)}")

    return "\n".join(parts) if parts else "No specific continuity details available."


def _safe_simplify(prompt: GeneratedPrompt, issue: ReviewIssue) -> tuple:
    """Deterministic safe fallback: strip or neutralize the problematic detail."""
    fix_log = None

    if issue.category == IssueCategory.DIALOGUE_TIMING:
        # Remove the dialogue line that overruns the duration
        if issue.detected_value:
            # Try to extract the dialogue text from detected_value
            dialogue_match = re.search(r"'([^']+)'", issue.detected_value)
            if dialogue_match:
                dialogue_text = dialogue_match.group(1)
                old_text = prompt.prompt_text
                # Remove the quoted dialogue and its speech verb
                prompt.prompt_text = re.sub(
                    rf'(?:says?|speaks?|whispers?|shouts?)\s*[,:]*\s*["\u201c]{re.escape(dialogue_text)}["\u201d]',
                    "(character speaks)",
                    prompt.prompt_text,
                    flags=re.IGNORECASE,
                )
                if prompt.prompt_text != old_text:
                    fix_log = f"Safe fallback: Shortened dialogue in shot {prompt.shot_id} to fit duration."

    elif issue.category == IssueCategory.CONTINUITY_DRIFT:
        # Cannot safely fix continuity without LLM, just log it
        fix_log = f"Safe fallback: Continuity drift in shot {prompt.shot_id} could not be auto-resolved — left as-is with warning."

    elif issue.category == IssueCategory.STRUCTURAL:
        fix_log = f"Safe fallback: Structural issue in {prompt.shot_id or 'plan'} could not be auto-resolved — left as-is with warning."

    return prompt, fix_log


async def apply_corrections(
    prompt_set: PromptSet,
    report: ReviewReport,
    spec: VideoSpecification,
    llm_service,
) -> tuple:
    """Apply the full Fallback Chain to resolve all issues.

    Returns (corrected_prompt_set, final_report).
    """
    # Deep copy to avoid mutating the original
    prompt_set = prompt_set.model_copy(deep=True)
    prompt_map = {p.prompt_id: p for p in prompt_set.prompts}

    spec_camera_str = ""
    if spec.camera:
        spec_camera_str = str(spec.camera.model_dump()).lower()

    fixes_applied: list[str] = []
    llm_calls_used = 0
    resolved_issue_ids: set[str] = set()

    # -------------------------------------------------------------------
    # Step 1: Auto-fix (pure Python) for all auto_fixable issues
    # -------------------------------------------------------------------
    for issue in report.issues:
        if not issue.auto_fixable:
            continue
        if issue.prompt_id and issue.prompt_id in prompt_map:
            p = prompt_map[issue.prompt_id]
            old_text = p.prompt_text
            old_neg = p.negative_constraints

            if issue.category == IssueCategory.CONTENT_QUALITY:
                # Internal ID leakage
                if "Internal ID" in issue.message or "leaked" in issue.message:
                    p.prompt_text = _strip_internal_ids(p.prompt_text)
                    if p.negative_constraints:
                        p.negative_constraints = _strip_internal_ids(p.negative_constraints)

                # Placeholder text
                elif "Placeholder" in issue.message or "incomplete" in issue.message:
                    p.prompt_text = _strip_placeholders(p.prompt_text)
                    if p.negative_constraints:
                        p.negative_constraints = _strip_placeholders(p.negative_constraints)

                # Redundant constraints
                elif "redundant" in issue.message.lower():
                    if p.negative_constraints:
                        p.negative_constraints = _deduplicate_negative_constraints(p.negative_constraints)

                # Hallucinated camera params
                elif "camera parameter" in issue.message.lower():
                    p.prompt_text = _strip_hallucinated_camera(p.prompt_text, spec_camera_str)

            # Log the fix
            changed = (p.prompt_text != old_text) or (p.negative_constraints != old_neg)
            if changed:
                fixes_applied.append(f"Auto-fixed [{issue.category.value}]: {issue.message[:80]}")
                resolved_issue_ids.add(issue.issue_id)

    # -------------------------------------------------------------------
    # Step 2 & 3: Targeted LLM patch for remaining BLOCKERs
    # -------------------------------------------------------------------
    unresolved_blockers = [
        iss for iss in report.issues
        if iss.severity == IssueSeverity.BLOCKER
        and iss.issue_id not in resolved_issue_ids
        and iss.prompt_id is not None
    ]

    for issue in unresolved_blockers:
        if llm_calls_used >= MAX_LLM_PATCH_CALLS:
            # Hit the cap — apply safe simplification to remaining issues
            p = prompt_map.get(issue.prompt_id)
            if p:
                p, fix_log = _safe_simplify(p, issue)
                if fix_log:
                    fixes_applied.append(fix_log)
                resolved_issue_ids.add(issue.issue_id)
            continue

        p = prompt_map.get(issue.prompt_id)
        if not p:
            continue

        continuity_context = _get_continuity_context(spec, issue)

        # Attempt 1
        patched = await _try_llm_patch(
            p, issue, continuity_context, llm_service,
            strict=False,
        )
        llm_calls_used += 1

        if patched:
            p.prompt_text = patched.prompt_text
            if patched.negative_constraints is not None:
                p.negative_constraints = patched.negative_constraints
            fixes_applied.append(f"LLM patch (attempt 1) [{issue.category.value}]: {issue.message[:80]}")
            resolved_issue_ids.add(issue.issue_id)
            continue

        if llm_calls_used >= MAX_LLM_PATCH_CALLS:
            p, fix_log = _safe_simplify(p, issue)
            if fix_log:
                fixes_applied.append(fix_log)
            resolved_issue_ids.add(issue.issue_id)
            continue

        # Attempt 2 (stricter)
        patched = await _try_llm_patch(
            p, issue, continuity_context, llm_service,
            strict=True,
        )
        llm_calls_used += 1

        if patched:
            p.prompt_text = patched.prompt_text
            if patched.negative_constraints is not None:
                p.negative_constraints = patched.negative_constraints
            fixes_applied.append(f"LLM patch (attempt 2, strict) [{issue.category.value}]: {issue.message[:80]}")
            resolved_issue_ids.add(issue.issue_id)
        else:
            # Final fallback: safe simplification
            p, fix_log = _safe_simplify(p, issue)
            if fix_log:
                fixes_applied.append(fix_log)
            resolved_issue_ids.add(issue.issue_id)

    # -------------------------------------------------------------------
    # Finalize the report
    # -------------------------------------------------------------------
    report.fixes_applied = fixes_applied
    report.retries_used = llm_calls_used

    # Determine final status
    remaining_issues = [
        iss for iss in report.issues
        if iss.issue_id not in resolved_issue_ids
    ]
    remaining_blockers = [i for i in remaining_issues if i.severity == IssueSeverity.BLOCKER]

    if not report.issues:
        report.status = ReviewStatus.PASSED
    elif fixes_applied and not remaining_blockers:
        report.status = ReviewStatus.PASSED_WITH_FIXES
    else:
        report.status = ReviewStatus.PASSED_WITH_WARNINGS

    return prompt_set, report


async def _try_llm_patch(
    prompt: GeneratedPrompt,
    issue: ReviewIssue,
    continuity_context: str,
    llm_service,
    strict: bool = False,
) -> Optional[PromptPatchResult]:
    """Attempt a single targeted LLM patch for one prompt/issue pair."""
    try:
        extra_instruction = ""
        if strict:
            extra_instruction = (
                "\n\nIMPORTANT: A previous correction attempt for this exact issue was "
                "insufficient. Be more aggressive in fixing the problem. If it is a "
                "continuity issue, ensure the description matches the canonical details "
                "word-for-word. If it is a timing issue, significantly shorten the text."
            )

        patch_prompt = PROMPT_PATCH_PROMPT.format(
            prompt_text=prompt.prompt_text,
            negative_constraints=prompt.negative_constraints or "None",
            issue_category=issue.category.value,
            issue_message=issue.message + extra_instruction,
            detected_value=issue.detected_value or "N/A",
            expected_value=issue.expected_value or "N/A",
            continuity_context=continuity_context,
        )

        result = await llm_service.generate_structured(
            patch_prompt,
            PromptPatchResult,
            operation="prompt_patch",
            thread_id="reviewer",
        )
        return result

    except Exception as e:
        logger.error(f"LLM patch failed for {prompt.prompt_id}: {e}")
        return None
