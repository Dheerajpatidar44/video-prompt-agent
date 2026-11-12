from typing import Optional, List
from pydantic import BaseModel, Field
from app.schemas.agent import Gap, Question


class ScriptDocument(BaseModel):
    document_id: str
    source_type: str
    filename: str
    original_text: str
    normalized_text: str
    page_count: Optional[int] = None
    metadata: dict = {}


class CharacterAnalysisItem(BaseModel):
    name: str = Field(description="Character name or descriptive identifier")
    description: str = Field(default="", description="Appearance, age, wardrobe, casting and personality traits")
    role: Optional[str] = Field(default=None, description="Narrative role (e.g. Protagonist, Antagonist, Supporting)")


class LocationAnalysisItem(BaseModel):
    name: str = Field(description="Location name or slugline")
    description: str = Field(default="", description="Setting details, interior/exterior, architecture, spatial depth")
    setting_type: Optional[str] = Field(default=None, description="Interior, Exterior, Studio, or Mixed")


class ProductAnalysisItem(BaseModel):
    name: str = Field(description="Product name or brand item")
    description: str = Field(default="", description="Physical shape, material, finish, packaging, and hero interaction")


class ActionAnalysisItem(BaseModel):
    description: str = Field(description="Narrative action or physical movement described in the script")
    character_name: Optional[str] = Field(default=None, description="Character performing this action")


class CameraAnalysisItem(BaseModel):
    description: str = Field(description="Cinematography specification: framing, angle, and camera motion")


class LightingAnalysisItem(BaseModel):
    description: str = Field(description="Lighting setup, color temperature, atmospheric mood, and shadows")


class AudioAnalysisItem(BaseModel):
    description: str = Field(description="Spoken dialogue, sound effect, ambient sound, or musical tone")
    audio_type: Optional[str] = Field(default="dialogue", description="dialogue, sfx, ambient, or music")


class TimingAnalysis(BaseModel):
    pacing: Optional[str] = Field(default=None, description="Overall pacing: fast, moderate, slow, contemplative")
    estimated_duration_seconds: Optional[float] = Field(default=None, description="Estimated script duration in seconds")
    notes: Optional[str] = Field(default=None, description="Timing feasibility, dialogue rate, or pacing considerations")


class ScriptAnalysis(BaseModel):
    story_objective: Optional[str] = None
    story_summary: Optional[str] = None
    characters: List[CharacterAnalysisItem] = []
    locations: List[LocationAnalysisItem] = []
    products: List[ProductAnalysisItem] = []
    actions: List[ActionAnalysisItem] = []
    camera_requirements: List[CameraAnalysisItem] = []
    lighting_requirements: List[LightingAnalysisItem] = []
    visual_style: List[str] = []
    audio: List[AudioAnalysisItem] = []
    timing: Optional[TimingAnalysis] = None
    aspect_ratio: Optional[str] = None
    orientation: Optional[str] = None
    constraints: List[str] = []
    explicit_requirements: List[str] = []
    unknown_or_unspecified: List[str] = []


class InitialAnalysisResult(BaseModel):
    """Combined schema for ONE initial LLM call: analysis + gaps + questions."""
    # Analysis fields
    story_objective: Optional[str] = None   
    story_summary: Optional[str] = None
    characters: List[CharacterAnalysisItem] = []
    locations: List[LocationAnalysisItem] = []
    products: List[ProductAnalysisItem] = []
    actions: List[ActionAnalysisItem] = []
    camera_requirements: List[CameraAnalysisItem] = []
    lighting_requirements: List[LightingAnalysisItem] = []
    visual_style: List[str] = []
    audio: List[AudioAnalysisItem] = []
    timing: Optional[TimingAnalysis] = None
    aspect_ratio: Optional[str] = None
    orientation: Optional[str] = None
    constraints: List[str] = []
    explicit_requirements: List[str] = []
    unknown_or_unspecified: List[str] = []

    # Gaps
    gaps: List[Gap] = []

    # Questions (pre-generated so we skip the separate ask_questions LLM call)
    questions: List[Question] = []
