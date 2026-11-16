"""Combined schema for the generation phase: scenes + prompts in one LLM call."""
from enum import Enum
from pydantic import BaseModel, Field
from typing import Optional, List


class VisualAssetRole(str, Enum):
    CHARACTER = "CHARACTER"
    PRODUCT = "PRODUCT"
    ENVIRONMENT = "ENVIRONMENT"
    ACTION_KEYFRAME = "ACTION_KEYFRAME"
    PROP_OR_OBJECT = "PROP_OR_OBJECT"


class ShotImageAssetPlan(BaseModel):
    asset_id: str = Field(description="Unique entity identifier, e.g., 'char_priya', 'prod_earbuds', 'env_office_rain'")
    role: VisualAssetRole
    is_master_entity: bool = Field(default=False, description="True if this entity appears across multiple shots")
    reuse_asset_id: Optional[str] = Field(default=None, description="ID of a previously generated master asset to reuse without calling API")
    user_reference_category: Optional[str] = Field(default=None, description="'character', 'product', or 'brand' if mapped to user uploads")
    generation_prompt: Optional[str] = Field(default=None, description="Cinematic prompt for Gemini if fresh generation is needed")
    aspect_ratio: str = Field(default="16:9")
 

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
    keyframe_image_prompt: Optional[str] = Field(
        default=None,
        description=(
            "Static photographic description of the OPENING FIRST FRAME (T=0s) of this shot. "
            "Describes only what is visible at the very first moment: subject appearance, pose, "
            "placement inside the script environment, and lighting. "
            "Single unified frame only — no sequential actions, no transitions, no dialogue."
        ),
    )
    negative_constraints: Optional[str] = None
    continuity_requirements: List[str] = []
    source_actions: List[str] = []
    image_assets: List[ShotImageAssetPlan] = Field(default_factory=list)


class GenerationResult(BaseModel):
    """Combined output: scenes + prompts from ONE LLM call."""
    scenes: List[GeneratedScenePlan] = []
    total_duration: float = 0.0
    prompts: List[GeneratedPromptItem] = []
