from typing import List
from app.graph.state import AgentState
from app.schemas.agent import AgentStatus, Gap, GapDetectionResult, GapStatus, Importance
from app.llm.ollama import llm_service, LLMException
from app.prompts.re_analyzer import RE_ANALYZER_PROMPT
import logging

logger = logging.getLogger(__name__)


def deduplicate_gaps(gaps: list[Gap]) -> list[Gap]:
    unique_gaps = []
    seen = set()
    for gap in gaps:
        key = (gap.category, gap.title.lower().strip())
        if key not in seen:
            seen.add(key)
            unique_gaps.append(gap)
    return unique_gaps


def sort_gaps(gaps: list[Gap]) -> list[Gap]:
    priority = {
        Importance.CRITICAL: 1,
        Importance.IMPORTANT: 2,
        Importance.OPTIONAL: 3,
        Importance.INFERABLE: 4,
    }
    return sorted(gaps, key=lambda g: priority.get(g.importance, 5))


async def re_analyze(state: AgentState) -> AgentState:
    """Re-evaluate gaps based on new user answers. ONE LLM call."""
    gaps = state.get("gaps", [])
    answers = state.get("answers", [])
    thread_id = state.get("project_id", "")
    
    if not gaps or not answers:
        return state

    script_analysis = state.get("analysis", {})
    original_script = state.get("original_script", "")
    
    gaps_json = [g.model_dump() for g in gaps]
    answers_json = [a.model_dump() for a in answers]
    
    prompt = RE_ANALYZER_PROMPT.format(
        script=original_script,
        analysis=script_analysis,
        gaps=gaps_json,
        answers=answers_json
    )
    
    try:
        result = await llm_service.generate_structured(
            prompt, GapDetectionResult,
            operation="re_analyze",
            thread_id=thread_id,
        )
    except LLMException as e:
        logger.error(f"Failed to re-analyze gaps: {e}")
        return {**state, "status": AgentStatus.ERROR, "error": str(e)}

    # Deterministic post-processing in Python
    existing_gap_map = {g.id: g for g in gaps}
    
    processed_gaps = []
    
    for g in result.gaps:
        if getattr(g, "status", None) is None:
            g.status = GapStatus.OPEN
        processed_gaps.append(g)
            
    # Include gaps that the LLM might have omitted
    llm_returned_ids = {g.id for g in processed_gaps}
    for old_g in gaps:
        if old_g.id not in llm_returned_ids:
            processed_gaps.append(old_g)
            
    unique_gaps = deduplicate_gaps(processed_gaps)
    sorted_gaps = sort_gaps(unique_gaps)
    
    return {
        **state,
        "gaps": sorted_gaps,
        "status": AgentStatus.ANALYZING
    }
