import json
import logging
from app.graph.state import AgentState
from app.schemas.agent import AgentStatus, GapStatus, Importance
from app.schemas.specification import VideoSpecification, SpecStatus
from app.llm.ollama import LLMService, LLMException
from app.prompts.video_specification import VIDEO_SPECIFICATION_PROMPT

logger = logging.getLogger(__name__)

def build_video_spec(state: AgentState) -> AgentState:
    """Build the final VideoSpecification structured object from current state."""
    logger.info("Building Video Specification...")

    original_script = state.get("original_script", "")
    analysis = state.get("analysis", {})
    gaps = state.get("gaps", [])
    answers = state.get("answers", [])
    
    # We only care about OPEN gaps for unresolved issues, and RESOLVED gaps for context
    gaps_json = [g.model_dump() for g in gaps]
    answers_json = [a.model_dump() for a in answers]
    
    prompt = VIDEO_SPECIFICATION_PROMPT.format(
        script=original_script,
        analysis=json.dumps(analysis, indent=2),
        gaps=json.dumps(gaps_json, indent=2),
        answers=json.dumps(answers_json, indent=2)
    )
    
    llm = LLMService()
    try:
        spec = llm.generate_structured(prompt, VideoSpecification)
    except LLMException as e:
        logger.error(f"Failed to generate VideoSpecification: {e}")
        return {**state, "status": AgentStatus.ERROR, "error": str(e)}

    # Safe defaults injection
    from app.core.config import settings
    from app.schemas.specification import SpecSource

    if spec.output_requirements.duration_seconds is None:
        spec.output_requirements.duration_seconds = settings.default_duration_seconds
        spec.output_requirements.source = SpecSource.SYSTEM_DEFAULT
        logger.info(f"Duration missing. Applying SYSTEM_DEFAULT: {settings.default_duration_seconds}s")
        
    if spec.output_requirements.aspect_ratio is None:
        spec.output_requirements.aspect_ratio = settings.default_aspect_ratio
        if spec.output_requirements.source != SpecSource.SYSTEM_DEFAULT:
            # If duration had a source but aspect ratio was missing, we can't easily set source for just one field in the current schema without a wrapper,
            # but we set it on the parent output_requirements object for tracking.
            spec.output_requirements.source = SpecSource.SYSTEM_DEFAULT
        logger.info(f"Aspect ratio missing. Applying SYSTEM_DEFAULT: {settings.default_aspect_ratio}")

    # Deterministic Validation & Status Checking
    # 1. Any CRITICAL or IMPORTANT open gaps that are NOT in unresolved_items should be added.
    blocking_gaps = [g for g in gaps if g.status == GapStatus.OPEN and g.importance in (Importance.CRITICAL, Importance.IMPORTANT)]
    
    # Ensure blocking gaps are represented
    existing_unresolved_ids = set()
    for item in spec.unresolved_items:
        existing_unresolved_ids.update(item.related_gap_ids)
        
    for bg in blocking_gaps:
        if bg.id not in existing_unresolved_ids:
            # If it's a safe field that we just defaulted (like duration/timing), don't block
            if bg.category.value in ["TIMING", "ASPECT_RATIO"]:
                continue
                
            from app.schemas.specification import UnresolvedItem
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

    # 2. Check for blocking items to determine status
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
