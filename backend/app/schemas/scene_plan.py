from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum
from app.schemas.specification import SpecSource

class TransitionType(str, Enum):
    CUT = "CUT"
    DISSOLVE = "DISSOLVE"
    FADE = "FADE"
    MATCH_CUT = "MATCH_CUT"
    CAMERA_CONTINUATION = "CAMERA_CONTINUATION"
    OBJECT_TRANSITION = "OBJECT_TRANSITION"
    NONE = "NONE"
    OTHER = "OTHER"

class NarrativeRole(str, Enum):
    ESTABLISHING = "ESTABLISHING"
    INTRODUCTION = "INTRODUCTION"
    ACTION = "ACTION"
    PRODUCT_REVEAL = "PRODUCT_REVEAL"
    PRODUCT_INTERACTION = "PRODUCT_INTERACTION"
    TRANSITION = "TRANSITION"
    EMOTIONAL_BEAT = "EMOTIONAL_BEAT"
    CLIMAX = "CLIMAX"
    RESOLUTION = "RESOLUTION"
    ENDING = "ENDING"
    OTHER = "OTHER"

class PlanStatus(str, Enum):
    DRAFT = "DRAFT"
    READY = "READY"
    BLOCKED = "BLOCKED"

class ValidationIssue(BaseModel):
    issue_type: str
    description: str
    severity: str
    related_entity_id: Optional[str] = None
    blocking: bool = False

class ShotPlan(BaseModel):
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
    transition: TransitionType = TransitionType.CUT
    continuity_requirements: List[str] = []
    source_actions: List[str] = []
    source_traceability: List[str] = []
    confidence: Optional[float] = None

class ScenePlan(BaseModel):
    scene_id: str
    scene_number: int
    title: str
    purpose: str
    narrative_role: NarrativeRole
    start_time: float
    end_time: float
    duration_seconds: float
    location_id: Optional[str] = None
    character_ids: List[str] = []
    product_ids: List[str] = []
    props: List[str] = []
    actions: List[str] = []
    visual_intent: Optional[str] = None
    emotional_intent: Optional[str] = None
    transition_in: TransitionType = TransitionType.CUT
    transition_out: TransitionType = TransitionType.CUT
    continuity_requirements: List[str] = []
    shots: List[ShotPlan] = []
    source_traceability: List[str] = []
    confidence: Optional[float] = None

class MasterScenePlan(BaseModel):
    scenes: List[ScenePlan] = []
    total_duration: float = 0.0
    status: PlanStatus = PlanStatus.DRAFT
    validation_issues: List[ValidationIssue] = []
