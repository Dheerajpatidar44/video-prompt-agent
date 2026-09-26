from typing import Optional, List
from pydantic import BaseModel
from app.schemas.agent import Gap, Question


class ScriptDocument(BaseModel):
    document_id: str
    source_type: str
    filename: str
    original_text: str
    normalized_text: str
    page_count: Optional[int] = None
    metadata: dict = {}


class ScriptAnalysis(BaseModel):
    story_objective: Optional[str] = None
    story_summary: Optional[str] = None
    characters: List[dict] = []
    locations: List[dict] = []
    products: List[dict] = []
    actions: List[dict] = []
    camera_requirements: List[dict] = []
    lighting_requirements: List[dict] = []
    visual_style: List[str] = []
    audio: List[dict] = []
    timing: dict = {}
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
    characters: List[dict] = []
    locations: List[dict] = []
    products: List[dict] = []
    actions: List[dict] = []
    camera_requirements: List[dict] = []
    lighting_requirements: List[dict] = []
    visual_style: List[str] = []
    audio: List[dict] = []
    timing: dict = {}
    aspect_ratio: Optional[str] = None
    orientation: Optional[str] = None
    constraints: List[str] = []
    explicit_requirements: List[str] = []
    unknown_or_unspecified: List[str] = []

    # Gaps
    gaps: List[Gap] = []

    # Questions (pre-generated so we skip the separate ask_questions LLM call)
    questions: List[Question] = []
