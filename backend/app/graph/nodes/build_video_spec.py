import json
import logging
from typing import Optional
from app.graph.state import AgentState
from app.schemas.agent import AgentStatus, GapCategory, GapStatus, Importance
from app.schemas.specification import VideoSpecification, SpecStatus, SpecSource, UnresolvedItem
from app.llm import llm_service
from app.prompts.video_specification import (
    VIDEO_SPECIFICATION_PROMPT,
    VIDEO_SPECIFICATION_SYSTEM_INSTRUCTION,
    VIDEO_SPECIFICATION_USER_PROMPT,
)
from app.core.config import settings
from app.utils.aspect_ratio import (
    detect_aspect_ratio_from_script,
    infer_orientation_from_aspect_ratio,
    normalize_aspect_ratio,
)

logger = logging.getLogger(__name__)


def _extract_user_aspect_ratio(gaps, questions, answers) -> Optional[str]:
    """Return explicit aspect ratio from user Q&A answers or resolved ASPECT_RATIO gaps."""
    for g in gaps or []:
        if getattr(g, "category", None) == GapCategory.ASPECT_RATIO and getattr(g, "status", None) == GapStatus.RESOLVED:
            parsed = normalize_aspect_ratio(getattr(g, "current_value", None))
            if parsed:
                return parsed

    aspect_q_ids = {
        getattr(q, "id", None)
        for q in (questions or [])
        if getattr(q, "category", None) == GapCategory.ASPECT_RATIO
    }
    for ans in reversed(answers or []):
        ans_text = getattr(ans, "answer", None)
        if getattr(ans, "question_id", None) in aspect_q_ids:
            parsed = normalize_aspect_ratio(ans_text)
            if parsed:
                return parsed

    # Respect explicit ratio/orientation typed in any answer (most recent first)
    for ans in reversed(answers or []):
        ans_text = getattr(ans, "answer", None) or ""
        detected, is_explicit = detect_aspect_ratio_from_script(ans_text)
        if detected and is_explicit:
            return detected

    return None


async def build_video_spec(state: AgentState) -> AgentState:
    """Build the final VideoSpecification structured object from current state."""
    logger.info("Building Video Specification...")

    original_script = state.get("original_script", "")
    analysis = state.get("analysis", {})
    gaps = state.get("gaps", [])
    questions = state.get("questions", [])
    answers = state.get("answers", [])
    thread_id = state.get("project_id", "")
    
    # We only care about OPEN gaps for unresolved issues, and RESOLVED gaps for context
    gaps_json = [g.model_dump() for g in gaps]
    answers_json = [a.model_dump() for a in answers]
    
    script_precheck = state.get("script_precheck") or {}
    detected_dur = script_precheck.get("detected_duration_seconds")

    user_aspect = _extract_user_aspect_ratio(gaps, questions, answers)
    script_aspect, script_aspect_explicit = detect_aspect_ratio_from_script(original_script)
    if script_aspect is None:
        script_aspect = normalize_aspect_ratio(script_precheck.get("aspect_ratio_hint"))
        script_aspect_explicit = bool(script_precheck.get("aspect_ratio_explicit"))

    raw_analysis_aspect = (
        analysis.get("aspect_ratio") if isinstance(analysis, dict) else getattr(analysis, "aspect_ratio", None)
    )
    analysis_aspect = normalize_aspect_ratio(raw_analysis_aspect)

    req_parts = []
    if detected_dur:
        req_parts.append(f"Target Video Duration: {int(detected_dur)} seconds (MANDATORY HARD CEILING - DO NOT EXCEED)")
    if user_aspect:
        req_parts.append(f"Aspect Ratio (User Confirmed): {user_aspect} (MANDATORY — DO NOT CHANGE)")
    elif script_aspect and script_aspect_explicit:
        req_parts.append(f"Aspect Ratio (Explicit in Script): {script_aspect} (MANDATORY — DO NOT CHANGE)")
    elif analysis_aspect:
        req_parts.append(f"Aspect Ratio (From Script Analysis): {analysis_aspect}")
    elif script_aspect:
        req_parts.append(f"Aspect Ratio Hint (Advisory Keyword): {script_aspect} (Verify against raw script)")
    req_parts.append("Format in output_requirements: duration_seconds as integer, aspect_ratio as string")

    output_requirements_text = "\n".join(req_parts) if req_parts else "None specified by user."

    try:
        user_prompt = VIDEO_SPECIFICATION_USER_PROMPT.format(
            script=original_script,
            analysis=json.dumps(analysis, indent=2),
            gaps=json.dumps(gaps_json, indent=2),
            answers=json.dumps(answers_json, indent=2),
            output_requirements=output_requirements_text,
        )
        spec = await llm_service.generate_structured(
            user_prompt,
            VideoSpecification,
            system_instruction=VIDEO_SPECIFICATION_SYSTEM_INSTRUCTION,
            operation="build_video_spec",
            thread_id=thread_id,
        )
    except Exception as e:
        logger.error(f"Failed to generate VideoSpecification: {e}")
        return {**state, "status": AgentStatus.ERROR, "error": str(e)}

    # Safe defaults injection & script duration enforcement (Python — no LLM needed)
    if detected_dur:
        if spec.output_requirements.duration_seconds != int(detected_dur):
            logger.info(f"Enforcing explicit script duration: {int(detected_dur)}s (was {spec.output_requirements.duration_seconds})")
            spec.output_requirements.duration_seconds = int(detected_dur)
            spec.output_requirements.source = SpecSource.SCRIPT
    elif spec.output_requirements.duration_seconds is None:
        spec.output_requirements.duration_seconds = settings.default_duration_seconds
        spec.output_requirements.source = SpecSource.SYSTEM_DEFAULT
        logger.info(f"Duration missing. Applying SYSTEM_DEFAULT: {settings.default_duration_seconds}s")

    # Deterministic aspect-ratio precedence (Python — guarantees no stray keyword override)
    llm_aspect = normalize_aspect_ratio(spec.output_requirements.aspect_ratio)
    if user_aspect:
        if llm_aspect != user_aspect:
            logger.info(f"Enforcing user-confirmed aspect ratio: {user_aspect} (was {spec.output_requirements.aspect_ratio})")
        spec.output_requirements.aspect_ratio = user_aspect
        spec.output_requirements.source = SpecSource.USER
    elif script_aspect and script_aspect_explicit:
        if llm_aspect != script_aspect:
            logger.info(f"Enforcing explicit script aspect ratio: {script_aspect} (was {spec.output_requirements.aspect_ratio})")
        spec.output_requirements.aspect_ratio = script_aspect
        spec.output_requirements.source = SpecSource.SCRIPT
    elif analysis_aspect:
        if llm_aspect != analysis_aspect:
            logger.info(f"Restoring script-analysis aspect ratio: {analysis_aspect} (was {spec.output_requirements.aspect_ratio})")
        spec.output_requirements.aspect_ratio = analysis_aspect
        if spec.output_requirements.source == SpecSource.UNKNOWN:
            spec.output_requirements.source = SpecSource.SCRIPT
    elif llm_aspect:
        spec.output_requirements.aspect_ratio = llm_aspect
    else:
        spec.output_requirements.aspect_ratio = script_aspect or settings.default_aspect_ratio
        if not user_aspect and not (detected_dur and spec.output_requirements.source == SpecSource.SCRIPT):
            spec.output_requirements.source = SpecSource.SCRIPT if script_aspect else SpecSource.SYSTEM_DEFAULT
        logger.info(f"Aspect ratio assigned: {spec.output_requirements.aspect_ratio}")

    inferred_orientation = infer_orientation_from_aspect_ratio(spec.output_requirements.aspect_ratio)
    if inferred_orientation:
        spec.output_requirements.orientation = inferred_orientation

    logger.info(
        f"Locked VideoSpecification output_requirements: duration={spec.output_requirements.duration_seconds}s, "
        f"aspect_ratio={spec.output_requirements.aspect_ratio}, orientation={spec.output_requirements.orientation}, "
        f"source={spec.output_requirements.source}"
    )

    # Deterministic Validation & Status Checking
    blocking_gaps = [g for g in gaps if g.status == GapStatus.OPEN and g.importance in (Importance.CRITICAL, Importance.IMPORTANT)]
    
    existing_unresolved_ids = set()
    for item in spec.unresolved_items:
        existing_unresolved_ids.update(item.related_gap_ids)
        
    for bg in blocking_gaps:
        if bg.id not in existing_unresolved_ids:
            if bg.category.value in ["TIMING", "ASPECT_RATIO"]:
                continue
                
            spec.unresolved_items.append(
                UnresolvedItem(
                    id=f"unres_{bg.id}",
                    category=bg.category.value,
                    description=bg.description,
                    related_gap_ids=[bg.id],
                    severity=bg.importance.value,
                    reason="Carried over from unresolved gaps",
                    blocking=True if bg.importance == Importance.CRITICAL else False
                )
            )

    is_blocked = any(item.blocking for item in spec.unresolved_items)
    
    if is_blocked:
        spec.status = SpecStatus.BLOCKED
    else:
        spec.status = SpecStatus.READY

    return {
        **state,
        "video_specification": spec,
        "status": AgentStatus.GENERATING
    }
