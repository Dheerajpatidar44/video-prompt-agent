from app.graph.state import AgentState
from app.schemas.agent import Importance, GapStatus, AgentStatus


def route_after_analysis(state: AgentState) -> str:
    """Route after the combined analyze_script node.
    
    If the node already set status=WAITING_FOR_USER (questions generated),
    go to update_state (which is interrupt_before, so it pauses).
    Otherwise proceed to build spec.
    """
    status = state.get("status")
    if status == AgentStatus.WAITING_FOR_USER:
        return "WAIT_FOR_ANSWERS"
    return "PROCEED"


def route_after_gap_detection(state: AgentState) -> str:
    """Determine whether to ask questions or proceed after re-analysis."""
    gaps = state.get("gaps", [])
    
    # If we hit max rounds, proceed regardless
    current_round = state.get("current_round", 0)
    max_rounds = state.get("max_rounds", 2)
    if current_round >= max_rounds:
        return "PROCEED"
        
    has_eligible_unresolved = any(
        gap.importance in [Importance.CRITICAL, Importance.IMPORTANT] and gap.status == GapStatus.OPEN
        for gap in gaps
    )
    
    if has_eligible_unresolved:
        return "ASK_QUESTIONS"
        
    return "PROCEED"
