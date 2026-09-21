from app.graph.state import AgentState
from app.schemas.agent import AgentStatus

def prompt_validator(state: AgentState) -> AgentState:
    """Validate script fidelity, continuity, action clarity, etc."""
    # TODO: Implement validation logic
    return {
        **state,
        "status": AgentStatus.VALIDATING,
    }
