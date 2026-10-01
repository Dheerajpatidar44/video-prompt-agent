from typing import List
from app.graph.state import AgentState
from app.schemas.agent import AgentStatus, Gap, ReAnalysisResult, GapStatus, Importance, QuestionStatus
from app.llm.claude_client import llm_service, LLMException
from app.prompts.re_analyzer import RE_ANALYZER_PROMPT
from app.graph.routing import within_round_limit, has_unresolved_priority_gaps
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
    """Re-evaluate gaps based on new user answers, and conditionally generate new questions."""
    gaps = state.get("gaps", [])
    answers = state.get("answers", [])
    thread_id = state.get("project_id", "")
    current_round = state.get("current_round", 0)
    max_rounds = state.get("max_rounds", 2)
    
    if not gaps or not answers:
        return state

    script_analysis = state.get("analysis", {})
    original_script = state.get("original_script", "")
    
    gaps_json = [g.model_dump() for g in gaps]
    answers_json = [a.model_dump() for a in answers]
    
    rounds_remaining = within_round_limit(current_round, max_rounds)
    
    prompt = RE_ANALYZER_PROMPT.format(
        script=original_script,
        analysis=script_analysis,
        gaps=gaps_json,
        answers=answers_json,
        generate_questions=str(rounds_remaining).lower()
    )
    
    try:
        result = await llm_service.generate_structured(
            prompt, ReAnalysisResult,
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
    
    new_questions = []
    if rounds_remaining:
        for q in result.questions:
            q.round_number = current_round + 1
            q.status = QuestionStatus.PENDING
            new_questions.append(q)
    
    merged_questions = state.get("questions", []) + new_questions
    
    if rounds_remaining and has_unresolved_priority_gaps(sorted_gaps) and len(new_questions) > 0:
        final_status = AgentStatus.WAITING_FOR_USER
    else:
        final_status = AgentStatus.ANALYZING

    return {
        **state,
        "gaps": sorted_gaps,
        "questions": merged_questions,
        "status": final_status
    }
