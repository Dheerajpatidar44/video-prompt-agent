"""Combined schema for the generation phase: scenes + prompts in one LLM call."""
from pydantic import BaseModel
from typing import Optional, List


class GeneratedShotPlan(BaseModel):
    shot_id: str
    shot_number: int
    scene_id: str
    start_time: float
    end_time: float
    duration_seconds: float
    purpose: str
    subject: str
    action: str
    framing: Optional[str] = None
    camera_angle: Optional[str] = None
    camera_movement: Optional[str] = None
    composition: Optional[str] = None
    lighting: Optional[str] = None
    visual_focus: Optional[str] = None
    product_focus: Optional[str] = None
    source_actions: List[str] = []


class GeneratedScenePlan(BaseModel):
    scene_id: str
    scene_number: int
    title: str
    purpose: str
    narrative_role: str = "ACTION"
    start_time: float
    end_time: float
    duration_seconds: float
    location_id: Optional[str] = None
    character_ids: List[str] = []
    product_ids: List[str] = []
    shots: List[GeneratedShotPlan] = []


class GeneratedPromptItem(BaseModel):
    prompt_id: str
    scene_id: str
    shot_id: str
    sequence_number: int
    duration_seconds: float
    prompt_text: str
    negative_constraints: Optional[str] = None
    continuity_requirements: List[str] = []
    source_actions: List[str] = []


class GenerationResult(BaseModel):
    """Combined output: scenes + prompts from ONE LLM call."""
    scenes: List[GeneratedScenePlan] = []
    total_duration: float = 0.0
    prompts: List[GeneratedPromptItem] = []
