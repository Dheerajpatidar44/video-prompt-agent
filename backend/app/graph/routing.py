from app.graph.state import AgentState
from app.schemas.agent import Importance, GapStatus, AgentStatus


def has_unresolved_priority_gaps(gaps: list) -> bool:
    """Check if any CRITICAL or IMPORTANT gaps remain OPEN."""
    return any(
        gap.importance in (Importance.CRITICAL, Importance.IMPORTANT)
        and gap.status == GapStatus.OPEN
        for gap in gaps
    )


def within_round_limit(current_round: int, max_rounds: int) -> bool:
    """Check if more clarification rounds are allowed."""
    return current_round < max_rounds


def route_after_analysis(state: AgentState) -> str:
    """Route after analyze_script OR re_analyze.

    If the node already set status=WAITING_FOR_USER (questions generated),
    go to update_state (which is interrupt_before, so it pauses).
    Otherwise proceed to build spec.
    """
    status = state.get("status")
    if status == AgentStatus.WAITING_FOR_USER:
        return "WAIT_FOR_ANSWERS"
    return "PROCEED"
