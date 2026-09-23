from typing import List, Dict, Any
from app.graph.state import AgentState
from app.schemas.agent import AgentStatus, GapStatus, Importance, QuestionGenerationResult, QuestionStatus
from app.llm.ollama import LLMService, LLMException
from app.prompts.question_generator import QUESTION_GENERATOR_PROMPT
import uuid
import logging

logger = logging.getLogger(__name__)

# Configurable constants (could be moved to app.core.config)
# Max questions limitation removed. Questions are now purely dynamic.

def ask_questions(state: AgentState) -> AgentState:
    """Convert important gaps into user-facing clarification questions."""
    
    gaps = state.get("gaps", [])
    
    # Filter eligible gaps: OPEN and (CRITICAL or IMPORTANT)
    eligible_gaps = [
        g for g in gaps 
        if g.status == GapStatus.OPEN and g.importance in [Importance.CRITICAL, Importance.IMPORTANT]
    ]
    
    if not eligible_gaps:
        # No questions to ask
        return {
            **state,
            "status": AgentStatus.ANALYZING # Or PROCEED logic handles this
        }

    script_analysis = state.get("analysis", {})
    original_script = state.get("original_script", "")
    
    # Prepare LLM input
    gaps_json = [g.model_dump() for g in eligible_gaps]
    
    prompt = QUESTION_GENERATOR_PROMPT.format(
        script=original_script,
        analysis=script_analysis,
        gaps=gaps_json
    )
    
    llm = LLMService()
    try:
        result = llm.generate_structured(prompt, QuestionGenerationResult)
    except LLMException as e:
        logger.error(f"Failed to generate questions: {e}")
        return {**state, "status": AgentStatus.ERROR, "error": str(e)}

    # Configurable constants (could be moved to app.core.config)
    # The number of questions is now strictly dynamic based on gaps, 
    # so we no longer use a MAX_QUESTIONS_PER_ROUND constant.
    
    # Deterministic processing
    existing_questions = state.get("questions", [])
    current_round = state.get("current_round", 0)
    
    valid_gap_ids = {g.id for g in eligible_gaps}
    
    processed_questions = []
    
    for q in result.questions:
        # Validate gap_ids exist
        valid_q_gaps = [gid for gid in q.gap_ids if gid in valid_gap_ids]
        
        if not valid_q_gaps:
            # Semantic mapping fallback attempt could go here, but for now
            # if we can't reliably map the question to a real gap, we discard it
            # to avoid polluting the state with orphaned questions.
            logger.warning(f"Discarding LLM generated question due to invalid or unmappable gap_ids: {q.gap_ids}")
            continue
            
        q.gap_ids = valid_q_gaps
        
        # Enforce priority based on the underlying gaps if LLM downplays it
        if q.priority in [Importance.OPTIONAL, Importance.INFERABLE]:
            logger.warning(f"LLM generated OPTIONAL/INFERABLE priority for question. Upgrading to IMPORTANT.")
            q.priority = Importance.IMPORTANT
            
        # Ensure fresh ID and proper status
        q.id = str(uuid.uuid4())
        q.status = QuestionStatus.PENDING
        q.round_number = current_round
        
        processed_questions.append(q)
        
    # Deduplicate against existing questions based on question text
    existing_q_texts = {q.question.lower().strip() for q in existing_questions}
    unique_questions = []
    for q in processed_questions:
        txt = q.question.lower().strip()
        if txt not in existing_q_texts:
            existing_q_texts.add(txt)
            unique_questions.append(q)
            
    # Sort by priority
    priority_map = {
        Importance.CRITICAL: 0,
        Importance.IMPORTANT: 1,
        Importance.OPTIONAL: 2,
        Importance.INFERABLE: 3
    }
    
    unique_questions.sort(key=lambda x: priority_map.get(x.priority, 99))
    
    final_questions = unique_questions
    
    status = AgentStatus.WAITING_FOR_USER if final_questions else AgentStatus.ANALYZING
    
    return {
        **state,
        "questions": existing_questions + final_questions,
        "status": status
    }
