from app.graph.state import AgentState
from app.schemas.agent import AgentStatus, QuestionStatus
import logging

logger = logging.getLogger(__name__)

def update_state(state: AgentState) -> AgentState:
    """Receive user answers and update the agent state."""
    new_answers = state.get("new_answers", [])
    if not new_answers:
        logger.warning("update_state called but no new_answers provided.")
        return state

    # Match answers to questions
    questions = list(state.get("questions", []))
    answers = list(state.get("answers", []))
    
    question_map = {q.id: q for q in questions}
    
    for ans in new_answers:
        if ans.question_id in question_map:
            q = question_map[ans.question_id]
            if q.status == QuestionStatus.PENDING:
                q.status = QuestionStatus.ANSWERED
                q.answer = ans.answer
                answers.append(ans)
            else:
                logger.warning(f"Answer provided for question {ans.question_id} that is not PENDING.")
        else:
            logger.warning(f"Answer provided for unknown question {ans.question_id}.")

    # Clear new_answers
    # Increment round counter
    current_round = state.get("current_round", 0) + 1
    
    # Switch status out of WAITING_FOR_USER to ANALYZING for the re_analyze step
    return {
        **state,
        "questions": questions,
        "answers": answers,
        "new_answers": [],
        "current_round": current_round,
        "status": AgentStatus.ANALYZING
    }
