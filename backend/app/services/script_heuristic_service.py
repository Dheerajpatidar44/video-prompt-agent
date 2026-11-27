"""Deterministic script heuristic and timing pre-checker service.

Extracts objective narrative structure, dialogue timing constraints, scene environments,
and Google Veo native clip slotting before invoking LLM reasoning.
"""
import re
import logging
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

from app.utils.aspect_ratio import (
    RE_HORIZONTAL_KEYWORDS,
    RE_VERTICAL_KEYWORDS,
    detect_aspect_ratio_from_script,
)

logger = logging.getLogger(__name__)


class DialogueLine(BaseModel):
    speaker: str
    text: str
    word_count: int
    estimated_seconds: float


class SceneStructure(BaseModel):
    scene_number: int
    header: str
    setting_type: str  # "INT", "EXT", "UNKNOWN"
    lighting_time: str  # "DAY", "NIGHT", "GOLDEN_HOUR", "UNKNOWN"
    summary_hint: str


class ScriptPreCheckReport(BaseModel):
    detected_duration_seconds: Optional[float] = None
    veo_recommended_shots: List[int] = Field(default_factory=list)  # e.g. [6, 4] for 10s
    aspect_ratio_hint: Optional[str] = None
    aspect_ratio_explicit: bool = False
    scene_count: int = 1
    detected_scenes: List[SceneStructure] = Field(default_factory=list)
    dialogue_lines: List[DialogueLine] = Field(default_factory=list)
    total_dialogue_words: int = 0
    estimated_speech_seconds: float = 0.0
    dialogue_timing_feasible: bool = True
    warnings: List[str] = Field(default_factory=list)
    deterministic_summary_text: str = ""


class ScriptHeuristicService:
    # Speaking speed: ~2.5 words per second for standard cinematic pacing
    WORDS_PER_SECOND = 2.5

    # Regex patterns
    RE_SCENE_HEADER = re.compile(
        r"^\s*(?:(?:INT|EXT|INT\./EXT|EXT\./INT|SCENE)\b[^\n]*|\b(?:SCENE\s+\d+)\b[^\n]*)",
        re.IGNORECASE | re.MULTILINE,
    )
    RE_TIMESTAMP_RANGE = re.compile(
        r"(\d{1,2}\s*:\s*\d{2})\s*[\s\-\–\—\~\ufffdto]+\s*(\d{1,2}\s*:\s*\d{2})"
    )
    # Second-based creator timestamp ranges: "0-2s:", "0–2s", "0 to 2s", "3–8s:", "[0-120 sec]"
    RE_SECOND_RANGE = re.compile(
        r"(?:^|[\n\r;|\(\[])\s*(\d{1,4}(?:\.\d+)?)\s*(?:s|sec|seconds?)?\s*[\-–—~to]+\s*(\d{1,4}(?:\.\d+)?)\s*(?:s|sec|seconds?)\b\s*[:\-\)\]]?",
        re.IGNORECASE | re.MULTILINE,
    )
    RE_DIALOGUE = re.compile(
        r'(?:^|[\n|.;])\s*([A-Za-z][A-Za-z0-9_\- ]{1,25}?)\s*(?:\([^)]*\))?\s*:\s*["\']?([^"\'\n\r|]{2,200})["\']?',
        re.MULTILINE,
    )
    RE_MINUTE_SECOND_COMPOUND = re.compile(
        r"\b(\d{1,2})\s*(?:minutes?|mins?)\s*(?:and\s*)?(\d{1,2})\s*(?:seconds?|secs?|s)\b",
        re.IGNORECASE,
    )
    RE_MINUTE_DURATION = re.compile(
        r"\b(?:(\d{1,2}(?:\.\d+)?)\s*(?:minutes?|mins?)\b|(\d{1,2})\s*(?:-minute|-min)\b)",
        re.IGNORECASE,
    )
    RE_DURATION = re.compile(
        r"\b(?:(\d{1,4}(?:\.\d+)?)\s*(?:seconds?|secs?|s)\b|(\d{1,4})\s*(?:-second|-sec)\b)",
        re.IGNORECASE,
    )
    RE_VERTICAL = RE_VERTICAL_KEYWORDS
    RE_HORIZONTAL = RE_HORIZONTAL_KEYWORDS

    @staticmethod
    def _parse_timestamp_seconds(ts_str: str) -> int:
        clean = ts_str.replace(" ", "")
        parts = clean.split(":")
        return int(parts[0]) * 60 + int(parts[1])

    @staticmethod
    def calculate_veo_shot_slots(target_duration: float) -> List[int]:
        """Snaps a target video duration to Google Veo's fixed clip blocks (4s, 6s, 8s)."""
        d = round(float(target_duration))
        if d <= 4:
            return [4]
        elif d <= 6:
            return [6]
        elif d <= 8:
            return [8]
        elif d == 10:
            return [6, 4]
        elif d == 12:
            return [6, 6]
        elif d == 14:
            return [6, 4, 4]
        elif d == 16:
            return [8, 8]
        elif d <= 20:
            return [6, 6, 4, 4]
        elif d <= 24:
            return [6, 6, 6, 6]
        elif d <= 30:
            return [8, 8, 8, 6]
        else:
            # General fallback: combinations of 6s and 8s
            shots = []
            remaining = d
            while remaining > 0:
                if remaining >= 8:
                    shots.append(8)
                    remaining -= 8
                elif remaining >= 6:
                    shots.append(6)
                    remaining -= 6
                else:
                    shots.append(4)
                    remaining -= 4
            return shots

    @staticmethod
    def audit_dialogue(script_text: str, target_duration: Optional[float]) -> tuple[List[DialogueLine], int, float, bool, List[str]]:
        lines: List[DialogueLine] = []
        warnings: List[str] = []

        ignore_speakers = {
            "NOTE", "SCENE", "HTTP", "HTTPS", "PROMPT", "CAMERA", "ACTION",
            "TEXT OVERLAY", "ON-SCREEN TEXT", "GRAPHIC", "SUPER", "TITLE",
            "STOPWATCH", "ON-SCREEN STOPWATCH", "FORMAT", "DURATION",
            "ASPECT", "ASPECT RATIO", "PRODUCT", "BRAND", "TARGET",
            "AWARENESS", "ANGLE", "FILLS", "AUDIO", "VISUAL", "TIMESTAMP", "TIME",
            "UPPER HALF", "BOTTOM HALF", "TOP HALF", "LEFT HALF", "RIGHT HALF",
            "SPLIT SCREEN", "SPLIT-SCREEN", "POPUP", "POP-UP", "CLEAR POPUP",
            "NOTIFICATION", "ALERT", "MODAL", "BANNER", "BADGE", "OVERLAY",
            "STICKER", "BUBBLE", "MESSAGE", "SCREEN", "CARD", "UI"
        }

        matches = ScriptHeuristicService.RE_DIALOGUE.findall(script_text)
        total_words = 0

        for speaker, speech in matches:
            clean_speaker = speaker.strip().title()
            spk_up = clean_speaker.upper()
            if (
                not clean_speaker
                or not clean_speaker[0].isalpha()
                or spk_up in ignore_speakers
                or any(kw in spk_up for kw in ["HALF", "OVERLAY", "STOPWATCH", "SCREEN", "POPUP", "POP-UP", "MODAL", "ALERT", "CARD", "NOTIF"])
            ):
                continue
            clean_speech = speech.strip()
            if not re.search(r"[A-Za-z]", clean_speech):
                continue
            words = len(clean_speech.split())
            if words == 0:
                continue
            est_seconds = round(words / ScriptHeuristicService.WORDS_PER_SECOND, 1)
            lines.append(DialogueLine(
                speaker=clean_speaker,
                text=clean_speech,
                word_count=words,
                estimated_seconds=est_seconds,
            ))
            total_words += words

        total_est_seconds = round(total_words / ScriptHeuristicService.WORDS_PER_SECOND, 1)
        dialogue_feasible = True

        if target_duration is not None and target_duration > 0:
            if total_est_seconds > target_duration:
                dialogue_feasible = False
                warnings.append(
                    f"Dialogue overflow: Script contains {total_words} words requiring ~{total_est_seconds}s to speak, "
                    f"which exceeds the {target_duration}s target video duration."
                )

        return lines, total_words, total_est_seconds, dialogue_feasible, warnings

    @staticmethod
    def extract_scenes(script_text: str) -> List[SceneStructure]:
        scenes: List[SceneStructure] = []
        matches = ScriptHeuristicService.RE_SCENE_HEADER.findall(script_text)

        if matches:
            for idx, header in enumerate(matches):
                header_str = header.strip()
                setting = "UNKNOWN"
                if re.search(r"\bINT\b", header_str, re.I):
                    setting = "INT"
                elif re.search(r"\bEXT\b", header_str, re.I):
                    setting = "EXT"

                lighting = "UNKNOWN"
                if re.search(r"\b(?:NIGHT|DARK)\b", header_str, re.I):
                    lighting = "NIGHT"
                elif re.search(r"\b(?:GOLDEN HOUR|SUNSET|SUNRISE|DUSK|DAWN)\b", header_str, re.I):
                    lighting = "GOLDEN_HOUR"
                elif re.search(r"\b(?:DAY|MORNING|AFTERNOON)\b", header_str, re.I):
                    lighting = "DAY"

                scenes.append(SceneStructure(
                    scene_number=idx + 1,
                    header=header_str,
                    setting_type=setting,
                    lighting_time=lighting,
                    summary_hint=header_str
                ))
            return scenes

        # 2. Check for Second-based Timestamp Scene Markers: e.g. "0-2s:", "3-8s:", "0–2s: ..."
        timestamp_lines = []
        for line in script_text.splitlines():
            line_clean = line.strip()
            if not line_clean:
                continue
            m = ScriptHeuristicService.RE_SECOND_RANGE.match(line_clean)
            if m:
                start_s = m.group(1)
                end_s = m.group(2)
                desc = line_clean[m.end():].lstrip(":- ").strip()
                timestamp_lines.append((start_s, end_s, desc or line_clean))

        if timestamp_lines:
            scenes = []
            for idx, (st, en, desc) in enumerate(timestamp_lines):
                scenes.append(SceneStructure(
                    scene_number=idx + 1,
                    header=f"SCENE {idx + 1} [{st}s - {en}s]",
                    setting_type="INT" if re.search(r"\b(?:ROOM|OFFICE|KITCHEN|BEDROOM|DESK|PHONE|INSIDE|INTERIOR)\b", desc, re.I) else "UNKNOWN",
                    lighting_time="DAY",
                    summary_hint=desc[:120].strip() or f"Narrative beat {st}s to {en}s"
                ))
            return scenes

        # 3. Check for Commercial AV Storyboard Table shots / Timestamps
        table_shots = []
        for line in script_text.splitlines():
            line_clean = line.strip()
            if not line_clean or line_clean.startswith("| ---") or "Timest" in line_clean:
                continue
            ts_m = ScriptHeuristicService.RE_TIMESTAMP_RANGE.search(line_clean)
            if ts_m:
                parts = [p.strip() for p in line_clean.split("|") if p.strip()]
                start_t = ts_m.group(1).replace(" ", "")
                end_t = ts_m.group(2).replace(" ", "")

                visual_desc = ""
                for p in parts:
                    if not ScriptHeuristicService.RE_TIMESTAMP_RANGE.search(p) and len(p) > 8:
                        if not p.lower().startswith("audio") and not p.lower().startswith("vo"):
                            visual_desc = p
                            break
                if not visual_desc and parts:
                    visual_desc = parts[0]

                table_shots.append((start_t, end_t, visual_desc))

        if table_shots:
            for idx, (st, en, desc) in enumerate(table_shots):
                setting = "UNKNOWN"
                if re.search(r"\b(?:ROOM|CHAIR|FLOOR|BEDROOM|KITCHEN|OFFICE|INSIDE|INTERIOR)\b", desc, re.I):
                    setting = "INT"
                elif re.search(r"\b(?:OUTSIDE|EXTERIOR|STREET|PARK|ROAD|BEACH)\b", desc, re.I):
                    setting = "EXT"

                lighting = "UNKNOWN"
                if re.search(r"\b(?:MORNING|DAY|SUNSHINE|AFTERNOON)\b", desc, re.I):
                    lighting = "DAY"
                elif re.search(r"\b(?:NIGHT|DARK)\b", desc, re.I):
                    lighting = "NIGHT"
                elif re.search(r"\b(?:SUNSET|GOLDEN HOUR|DUSK|DAWN)\b", desc, re.I):
                    lighting = "GOLDEN_HOUR"

                scenes.append(SceneStructure(
                    scene_number=idx + 1,
                    header=f"SHOT {idx + 1} [{st} - {en}]",
                    setting_type=setting,
                    lighting_time=lighting,
                    summary_hint=desc[:120].strip()
                ))
            return scenes

        # Single implicit scene if no headers exist
        return [SceneStructure(
            scene_number=1,
            header="SCENE 1 (Single Continuous Scene)",
            setting_type="UNKNOWN",
            lighting_time="UNKNOWN",
            summary_hint=script_text[:120].strip()
        )]

    @staticmethod
    def detect_duration_and_aspect(script_text: str) -> tuple[Optional[float], Optional[str]]:
        duration: Optional[float] = None

        # Check explicit "duration: 120s" or "duration: 2 minutes" or "final video length: 90"
        explicit_m = re.search(
            r"(?:final\s+)?(?:video\s+)?(?:duration|length|runtime)\s*[:=-]?\s*(\d{1,4}(?:\.\d+)?)\s*(minutes?|mins?|min|m|seconds?|secs?|s)?\b",
            script_text,
            re.IGNORECASE,
        )
        if explicit_m:
            try:
                val = float(explicit_m.group(1))
                unit = (explicit_m.group(2) or "").lower()
                duration = val * 60.0 if unit.startswith("m") else val
            except ValueError:
                pass

        # Check explicit timestamp ranges (second-based and colon-based)
        if duration is None:
            max_ts = 0.0
            second_ranges = ScriptHeuristicService.RE_SECOND_RANGE.findall(script_text)
            for _, end_str in second_ranges:
                try:
                    val = float(end_str)
                    if val > max_ts:
                        max_ts = val
                except ValueError:
                    pass

            colon_matches = ScriptHeuristicService.RE_TIMESTAMP_RANGE.findall(script_text)
            for _, end_col in colon_matches:
                col_val = float(ScriptHeuristicService._parse_timestamp_seconds(end_col))
                if col_val > max_ts:
                    max_ts = col_val

            if max_ts > 0:
                duration = max_ts

        # Fallback to standalone duration mentions ("1 minute 30 seconds", "2 minutes", "120s")
        if duration is None:
            compound_m = ScriptHeuristicService.RE_MINUTE_SECOND_COMPOUND.search(script_text)
            if compound_m:
                try:
                    duration = float(compound_m.group(1)) * 60.0 + float(compound_m.group(2))
                except ValueError:
                    pass

        if duration is None:
            min_match = ScriptHeuristicService.RE_MINUTE_DURATION.search(script_text)
            if min_match:
                val_str = min_match.group(1) or min_match.group(2)
                try:
                    duration = float(val_str) * 60.0
                except ValueError:
                    pass

        if duration is None:
            dur_match = ScriptHeuristicService.RE_DURATION.search(script_text)
            if dur_match:
                val_str = dur_match.group(1) or dur_match.group(2)
                try:
                    duration = float(val_str)
                except ValueError:
                    pass

        aspect, _ = detect_aspect_ratio_from_script(script_text)

        return duration, aspect

    @classmethod
    def scan_script(
        cls, script_text: str, explicit_target_duration: Optional[float] = None
    ) -> ScriptPreCheckReport:
        """Executes the full deterministic pre-check pipeline on the script."""
        detected_dur, _ = cls.detect_duration_and_aspect(script_text)
        aspect, aspect_explicit = detect_aspect_ratio_from_script(script_text)
        effective_duration = explicit_target_duration or detected_dur

        veo_slots = cls.calculate_veo_shot_slots(effective_duration) if effective_duration else [6, 4]
        scenes = cls.extract_scenes(script_text)
        dialogue, total_words, est_time, feasible, warnings = cls.audit_dialogue(
            script_text, effective_duration
        )

        # Build clean formatted bullet points
        dur_text = f"{effective_duration}s" if effective_duration else "Not explicitly specified (Defaulting to 10s)"
        slots_text = (
            f" -> Google Veo Clip Slotting: {' + '.join(f'{s}s' for s in veo_slots)}"
            " (Fallback suggestion only if raw script does not specify per-shot splits)"
        )
        if aspect:
            suffix = " (Explicit)" if aspect_explicit else " (Advisory keyword hint)"
            aspect_text = f"Aspect Ratio Detected: {aspect}{suffix}"
        else:
            aspect_text = "Aspect Ratio: None detected (Default 16:9)"

        lines_summary = []
        lines_summary.append(f"- Duration: {dur_text}{slots_text}")
        lines_summary.append(f"- {aspect_text}")
        lines_summary.append(f"- Candidate Scene Boundary Hints (Advisory - verify against raw script):")
        for sc in scenes[:25]:
            lines_summary.append(f"  * Scene {sc.scene_number}: {sc.header} [{sc.setting_type}/{sc.lighting_time}]")

        if dialogue:
            lines_summary.append(f"- Dialogue & Voiceover Hints: {len(dialogue)} line(s), {total_words} words (Estimated speech: ~{est_time}s)")
            for d in dialogue[:20]:
                lines_summary.append(f"  * {d.speaker}: \"{d.text}\" ({d.word_count} words)")
            if not feasible:
                lines_summary.append(f"  ⚠️ TIMING ADVISORY: Spoken dialogue (~{est_time}s) may exceed target duration ({effective_duration}s).")
        else:
            lines_summary.append("- Dialogue & Voiceover Hints: No structured dialogue tags detected via regex. Check raw script narrative directly for voiceovers or unformatted dialogue.")

        return ScriptPreCheckReport(
            detected_duration_seconds=effective_duration,
            veo_recommended_shots=veo_slots,
            aspect_ratio_hint=aspect,
            aspect_ratio_explicit=aspect_explicit,
            scene_count=len(scenes),
            detected_scenes=scenes,
            dialogue_lines=dialogue,
            total_dialogue_words=total_words,
            estimated_speech_seconds=est_time,
            dialogue_timing_feasible=feasible,
            warnings=warnings,
            deterministic_summary_text="\n".join(lines_summary)
        )
