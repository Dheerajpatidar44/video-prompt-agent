import json
import logging
from app.graph.state import AgentState
from app.schemas.agent import AgentStatus, GapStatus, Importance
from app.schemas.specification import VideoSpecification, SpecStatus, SpecSource, UnresolvedItem
from app.llm.claude_client import llm_service, LLMException
from app.prompts.video_specification import VIDEO_SPECIFICATION_PROMPT
from app.core.config import settings

logger = logging.getLogger(__name__)

async def build_video_spec(state: AgentState) -> AgentState:
    """Build the final VideoSpecification structured object from current state."""
    logger.info("Building Video Specification...")

    original_script = state.get("original_script", "")
    analysis = state.get("analysis", {})
    gaps = state.get("gaps", [])
    answers = state.get("answers", [])
    thread_id = state.get("project_id", "")
    
    # We only care about OPEN gaps for unresolved issues, and RESOLVED gaps for context
    gaps_json = [g.model_dump() for g in gaps]
    answers_json = [a.model_dump() for a in answers]
    
    prompt = VIDEO_SPECIFICATION_PROMPT.format(
        script=original_script,
        analysis=json.dumps(analysis, indent=2),
        gaps=json.dumps(gaps_json, indent=2),
        answers=json.dumps(answers_json, indent=2)
    )
    
    try:
        spec = await llm_service.generate_structured(
            prompt, VideoSpecification,
            operation="build_video_spec",
            thread_id=thread_id,
        )
    except LLMException as e:
        logger.error(f"Failed to generate VideoSpecification: {e}")
        return {**state, "status": AgentStatus.ERROR, "error": str(e)}

    # Safe defaults injection (Python — no LLM needed)
    if spec.output_requirements.duration_seconds is None:
        spec.output_requirements.duration_seconds = settings.default_duration_seconds
        spec.output_requirements.source = SpecSource.SYSTEM_DEFAULT
        logger.info(f"Duration missing. Applying SYSTEM_DEFAULT: {settings.default_duration_seconds}s")
        
    if spec.output_requirements.aspect_ratio is None:
        spec.output_requirements.aspect_ratio = settings.default_aspect_ratio
        if spec.output_requirements.source != SpecSource.SYSTEM_DEFAULT:
            spec.output_requirements.source = SpecSource.SYSTEM_DEFAULT
        logger.info(f"Aspect ratio missing. Applying SYSTEM_DEFAULT: {settings.default_aspect_ratio}")

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
        "status": AgentStatus.VALIDATING
    }
