from typing import TypedDict, List, Optional, Any, Dict
from app.schemas.agent import Gap, Question, Answer, AgentStatus
from app.schemas.specification import VideoSpecification
from app.schemas.scene_plan import MasterScenePlan
from app.schemas.generated_prompt import PromptSet

class AgentState(TypedDict):
    # Core project input
    project_id: Optional[str]
    original_script: Optional[str]
    script_source: Optional[str]
    reference_images: List[str]
    
    # Processed script representation
    analysis: Dict[str, Any]
    video_specification: Optional[VideoSpecification]
    
    # Specific attributes
    characters: List[Dict[str, Any]]
    locations: List[Dict[str, Any]]
    products: List[Dict[str, Any]]
    actions: List[Dict[str, Any]]
    camera_requirements: List[Dict[str, Any]]
    lighting: List[Dict[str, Any]]
    visual_style: Optional[str]
    audio: Optional[str]
    duration: Optional[str]
    aspect_ratio: Optional[str]
    continuity_bible: Dict[str, Any]
    
    # Agent dynamic state
    gaps: List[Gap]
    questions: List[Question]
    answers: List[Answer]
    new_answers: List[Answer]
    current_round: int
    max_rounds: int
    
    # Outputs
    scene_plan: Optional[MasterScenePlan]
    prompt_set: Optional[PromptSet]
    generated_prompts: List[str]
    validation_results: Dict[str, Any]
    
    # Status
    status: AgentStatus
    error: Optional[str]
