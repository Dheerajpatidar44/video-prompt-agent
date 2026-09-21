from app.graph.state import AgentState
from app.schemas.agent import AgentStatus

def initialize_state(state: AgentState) -> AgentState:
    """Initialize defaults for the agent state."""
    return {
        **state,
        "current_round": state.get("current_round", 0),
        "max_rounds": state.get("max_rounds", 2),
        "gaps": state.get("gaps", []),
        "questions": state.get("questions", []),
        "answers": state.get("answers", []),
        "scene_plan": state.get("scene_plan", []),
        "generated_prompts": state.get("generated_prompts", []),
        "validation_results": state.get("validation_results", {}),
        "characters": state.get("characters", []),
        "locations": state.get("locations", []),
        "products": state.get("products", []),
        "actions": state.get("actions", []),
        "camera_requirements": state.get("camera_requirements", []),
        "lighting": state.get("lighting", []),
        "reference_images": state.get("reference_images", []),
        "status": AgentStatus.ANALYZING,
    }
