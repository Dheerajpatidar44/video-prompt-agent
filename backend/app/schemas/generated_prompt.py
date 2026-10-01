from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from enum import Enum

class PromptStatus(str, Enum):
    DRAFT = "DRAFT"
    READY = "READY"
    BLOCKED = "BLOCKED"

from app.schemas.scene_plan import ValidationIssue

class GeneratedPrompt(BaseModel):
    prompt_id: str
    scene_id: str
    shot_id: str
    sequence_number: int
    duration_seconds: float
    prompt_text: str
    negative_constraints: Optional[str] = None
    continuity_requirements: List[str] = []
    source_traceability: List[str] = []
    source_actions: List[str] = []
    status: PromptStatus = PromptStatus.DRAFT
    validation_issues: List[ValidationIssue] = []

class PromptSet(BaseModel):
    prompts: List[GeneratedPrompt] = []
    total_duration: float = 0.0
    aspect_ratio: Optional[str] = None
    status: PromptStatus = PromptStatus.DRAFT
    validation_issues: List[ValidationIssue] = []
    generation_metadata: Dict[str, Any] = Field(default_factory=dict)
