from typing import List
from app.graph.state import AgentState
from app.schemas.agent import AgentStatus, Gap, GapDetectionResult, GapStatus, Importance
from app.llm.ollama import LLMService, LLMException
from app.prompts.re_analyzer import RE_ANALYZER_PROMPT
from app.graph.nodes.detect_gaps import deduplicate_gaps, sort_gaps
import logging

logger = logging.getLogger(__name__)

def re_analyze(state: AgentState) -> AgentState:
    """Re-evaluate gaps based on new user answers."""
    gaps = state.get("gaps", [])
    answers = state.get("answers", [])
    
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
    
    llm = LLMService()
    try:
        result = llm.generate_structured(prompt, GapDetectionResult)
    except LLMException as e:
        logger.error(f"Failed to re-analyze gaps: {e}")
        return {**state, "status": AgentStatus.ERROR, "error": str(e)}

    # Ensure gap IDs are preserved for existing gaps, and deduplicate/sort new ones
    existing_gap_map = {g.id: g for g in gaps}
    
    processed_gaps = []
    
    for g in result.gaps:
        # Fallback to OPEN if somehow missing
        if getattr(g, "status", None) is None:
            g.status = GapStatus.OPEN
            
        if g.id in existing_gap_map:
            # Update existing gap status/details based on LLM response
            old_g = existing_gap_map[g.id]
            # LLM may have changed status to RESOLVED
            processed_gaps.append(g)
        else:
            # It's a new gap (e.g. contradiction or missing asset introduced by an answer)
            processed_gaps.append(g)
            
    # Include gaps that the LLM might have omitted by mistake
    llm_returned_ids = {g.id for g in processed_gaps}
    for old_g in gaps:
        if old_g.id not in llm_returned_ids:
            processed_gaps.append(old_g)
            
    # Validation / Deduplication / Sorting
    unique_gaps = deduplicate_gaps(processed_gaps)
    sorted_gaps = sort_gaps(unique_gaps)
    
    print("INSIDE RE_ANALYZE, PROCESSED GAPS:", [g.status for g in processed_gaps])
    print("INSIDE RE_ANALYZE, SORTED GAPS:", [g.status for g in sorted_gaps])
    
    return {
        **state,
        "gaps": sorted_gaps,
        "status": AgentStatus.ANALYZING
    }
