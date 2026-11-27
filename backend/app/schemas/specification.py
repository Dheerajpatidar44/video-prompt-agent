from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict, Any
from enum import Enum

from app.utils.aspect_ratio import normalize_aspect_ratio

class SpecSource(str, Enum):
    SCRIPT = "SCRIPT"
    USER = "USER"
    INFERRED = "INFERRED"
    SYSTEM_DEFAULT = "SYSTEM_DEFAULT"
    UNKNOWN = "UNKNOWN"

class SpecStatus(str, Enum):
    DRAFT = "DRAFT"
    READY = "READY"
    BLOCKED = "BLOCKED"

class ReferenceAssetType(str, Enum):
    PRODUCT_IMAGE = "PRODUCT_IMAGE"
    CHARACTER_REFERENCE = "CHARACTER_REFERENCE"
    LOCATION_REFERENCE = "LOCATION_REFERENCE"
    STYLE_REFERENCE = "STYLE_REFERENCE"
    LOGO = "LOGO"
    OTHER = "OTHER"

class ReferenceAsset(BaseModel):
    id: str
    type: ReferenceAssetType
    reference_path: str
    purpose: str
    required: bool = True
    associated_entity_id: Optional[str] = None
    source: SpecSource = SpecSource.UNKNOWN


class SourcedField(BaseModel):
    value: Any
    source: SpecSource
    confidence: Optional[float] = None
    original_reference: Optional[str] = None

class CharacterSpec(BaseModel):
    id: str
    name: str
    role: Optional[str] = None
    approximate_age: Optional[str] = None
    gender_presentation: Optional[str] = None
    appearance: Optional[str] = None
    hairstyle: Optional[str] = None
    clothing: Optional[str] = None
    accessories: Optional[str] = None
    source: SpecSource = SpecSource.UNKNOWN


class LocationSpec(BaseModel):
    id: str
    name: str
    type: Optional[str] = None
    description: Optional[str] = None
    environment: Optional[str] = None
    architecture: Optional[str] = None
    time_of_day: Optional[str] = None
    weather: Optional[str] = None
    atmosphere: Optional[str] = None
    source: SpecSource = SpecSource.UNKNOWN


class ProductSpec(BaseModel):
    id: str
    name: str
    category: Optional[str] = None
    description: Optional[str] = None
    appearance: Optional[str] = None
    color: Optional[str] = None
    material: Optional[str] = None
    packaging: Optional[str] = None
    logo: Optional[str] = None
    reference_asset_ids: List[str] = []
    source: SpecSource = SpecSource.UNKNOWN


class ActionSpec(BaseModel):
    id: str
    actor_id: Optional[str] = None
    action: str
    target_object_id: Optional[str] = None
    sequence_order: Optional[int] = None
    required: bool = True
    source: SpecSource = SpecSource.UNKNOWN


class CameraSpec(BaseModel):
    camera_style: Optional[str] = None
    movement: Optional[str] = None
    framing: Optional[str] = None
    shot_scale: Optional[str] = None
    perspective: Optional[str] = None
    depth_of_field: Optional[str] = None
    source: SpecSource = SpecSource.UNKNOWN


class LightingSpec(BaseModel):
    lighting_style: Optional[str] = None
    light_direction: Optional[str] = None
    color_temperature: Optional[str] = None
    contrast: Optional[str] = None
    mood: Optional[str] = None
    source: SpecSource = SpecSource.UNKNOWN


class CompositionSpec(BaseModel):
    framing_requirements: Optional[str] = None
    subject_placement: Optional[str] = None
    symmetry: Optional[str] = None
    source: SpecSource = SpecSource.UNKNOWN


class VisualStyleSpec(BaseModel):
    visual_style: Optional[str] = None
    realism_level: Optional[str] = None
    color_treatment: Optional[str] = None
    texture: Optional[str] = None
    atmosphere: Optional[str] = None
    source: SpecSource = SpecSource.UNKNOWN


class DialogueSpec(BaseModel):
    speaker_id: str
    text: str
    delivery_style: Optional[str] = None
    source: SpecSource = SpecSource.UNKNOWN


class AudioSpec(BaseModel):
    music: Optional[str] = None
    sound_effects: Optional[str] = None
    ambience: Optional[str] = None
    voiceover: Optional[str] = None
    dialogue: List[DialogueSpec] = []
    source: SpecSource = SpecSource.UNKNOWN


class OutputRequirements(BaseModel):
    @field_validator("duration_seconds", mode="before")
    @classmethod
    def sanitize_duration_seconds(cls, v: Any) -> Any:
        if v is None:
            return None
        if isinstance(v, (int, float)):
            return int(v)
        if isinstance(v, str):
            import re
            m = re.search(r"(\d+)", v)
            if m:
                return int(m.group(1))
        return None
    duration_seconds: Optional[int] = None
    @field_validator("aspect_ratio", mode="before")
    @classmethod
    def sanitize_aspect_ratio(cls, v: Any) -> Any:
        if v is None:
            return None
        return normalize_aspect_ratio(str(v))

    aspect_ratio: Optional[str] = None
    orientation: Optional[str] = None
    resolution: Optional[str] = None
    source: SpecSource = SpecSource.UNKNOWN


class ContinuityBible(BaseModel):
    characters: List[CharacterSpec] = []
    locations: List[LocationSpec] = []
    products: List[ProductSpec] = []
    important_props: List[str] = []
    wardrobe_notes: List[str] = []

class UnresolvedItem(BaseModel):
    id: str
    category: str
    description: str
    related_gap_ids: List[str] = []
    severity: str
    reason: str
    blocking: bool = False

class ConstraintSpec(BaseModel):
    id: str
    description: str
    type: str = "HARD_CONSTRAINT"  # HARD_CONSTRAINT or PREFERENCE
    source: SpecSource = SpecSource.UNKNOWN


class VideoSpecification(BaseModel):
    project_id: str
    title: Optional[str] = None
    objective: Optional[str] = None
    story_summary: Optional[str] = None
    
    output_requirements: OutputRequirements = Field(default_factory=OutputRequirements)
    
    characters: List[CharacterSpec] = []
    locations: List[LocationSpec] = []
    products: List[ProductSpec] = []
    actions: List[ActionSpec] = []
    
    camera: CameraSpec = Field(default_factory=CameraSpec)
    lighting: LightingSpec = Field(default_factory=LightingSpec)
    composition: CompositionSpec = Field(default_factory=CompositionSpec)
    visual_style: VisualStyleSpec = Field(default_factory=VisualStyleSpec)
    audio: AudioSpec = Field(default_factory=AudioSpec)
    
    constraints: List[ConstraintSpec] = []
    reference_assets: List[ReferenceAsset] = []
    
    continuity_bible: ContinuityBible = Field(default_factory=ContinuityBible)
    unresolved_items: List[UnresolvedItem] = []
    
    status: SpecStatus = SpecStatus.DRAFT
    version: int = 1

    @field_validator("output_requirements", mode="before")
    @classmethod
    def sanitize_output_requirements(cls, v: Any) -> Any:
        """Defensively handles malformed LLM outputs (e.g. XML tags, raw strings, None)."""
        if isinstance(v, OutputRequirements):
            return v
        if isinstance(v, dict):
            return v
        if isinstance(v, str):
            import re
            extracted: Dict[str, Any] = {}
            dur_match = re.search(r'duration(?:_seconds)?["\':=\s>]+(\d+)', v, re.IGNORECASE)
            if dur_match:
                extracted["duration_seconds"] = int(dur_match.group(1))

            aspect_match = re.search(r'aspect(?:_ratio)?["\':=\s>]+(["\']?(\d+:\d+)["\']?)', v, re.IGNORECASE)
            if aspect_match:
                extracted["aspect_ratio"] = aspect_match.group(2)

            if v.strip().startswith("{") and v.strip().endswith("}"):
                try:
                    import json
                    parsed = json.loads(v)
                    if isinstance(parsed, dict):
                        return parsed
                except Exception:
                    pass

            return extracted
        if v is None:
            return {}
        return v

    @field_validator("camera", "lighting", "composition", "visual_style", "audio", "continuity_bible", mode="before")
    @classmethod
    def sanitize_nested_spec_objects(cls, v: Any) -> Any:
        if v is None or isinstance(v, str):
            return {}
        return v

    @field_validator("characters", "locations", "products", "actions", "constraints", "reference_assets", "unresolved_items", mode="before")
    @classmethod
    def sanitize_list_fields(cls, v: Any) -> Any:
        if v is None or isinstance(v, str):
            return []
        return v
