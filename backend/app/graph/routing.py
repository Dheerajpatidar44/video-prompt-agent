from app.graph.state import AgentState
from app.schemas.agent import Importance, GapStatus

def route_after_gap_detection(state: AgentState) -> str:
    """Determine whether to ask questions or proceed."""
    gaps = state.get("gaps", [])
    
    # If we hit max rounds, we must proceed regardless of gaps
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
