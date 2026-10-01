from pydantic import BaseModel, Field
from typing import Optional, List, Any
from enum import Enum

class Importance(str, Enum):
    CRITICAL = "CRITICAL"
    IMPORTANT = "IMPORTANT"
    OPTIONAL = "OPTIONAL"
    INFERABLE = "INFERABLE"

class GapStatus(str, Enum):
    OPEN = "OPEN"
    RESOLVED = "RESOLVED"
    DISMISSED = "DISMISSED"

class QuestionStatus(str, Enum):
    PENDING = "PENDING"
    ANSWERED = "ANSWERED"
    SKIPPED = "SKIPPED"
    DISMISSED = "DISMISSED"

class AnswerType(str, Enum):
    TEXT = "TEXT"
    SINGLE_CHOICE = "SINGLE_CHOICE"
    MULTI_CHOICE = "MULTI_CHOICE"
    BOOLEAN = "BOOLEAN"
    NUMBER = "NUMBER"

class GapCategory(str, Enum):
    STORY = "STORY"
    CHARACTER = "CHARACTER"
    LOCATION = "LOCATION"
    PRODUCT = "PRODUCT"
    ACTION = "ACTION"
    CAMERA = "CAMERA"
    COMPOSITION = "COMPOSITION"
    LIGHTING = "LIGHTING"
    VISUAL_STYLE = "VISUAL_STYLE"
    AUDIO = "AUDIO"
    DIALOGUE = "DIALOGUE"
    TIMING = "TIMING"
    ASPECT_RATIO = "ASPECT_RATIO"
    CONTINUITY = "CONTINUITY"
    REFERENCE_ASSET = "REFERENCE_ASSET"
    OUTPUT_REQUIREMENT = "OUTPUT_REQUIREMENT"
    CONSTRAINT = "CONSTRAINT"
    OTHER = "OTHER"

class Gap(BaseModel):
    id: str
    category: GapCategory
    importance: Importance
    title: str = Field(default="Untitled Gap")
    description: str
    why_it_matters: str = Field(default="")
    evidence: str
    current_value: Optional[Any] = None
    expected_information: Optional[str] = None
    confidence: Optional[float] = None
    source_reference: Optional[str] = None
    status: GapStatus = GapStatus.OPEN
    related_entities: List[str] = []
    related_scene: Optional[str] = None
    inferred_value: Optional[str] = None
    contradiction_details: Optional[str] = None

class GapDetectionResult(BaseModel):
    gaps: List[Gap] = []


class Question(BaseModel):
    id: str
    gap_ids: List[str] = []
    question: str
    category: str
    priority: Importance
    answer_type: AnswerType = AnswerType.TEXT
    options: Optional[List[str]] = None
    required: bool = True
    round_number: int = 0
    answer: Optional[str] = None
    status: QuestionStatus = QuestionStatus.PENDING

class QuestionGenerationResult(BaseModel):
    questions: List[Question] = []

class ReAnalysisResult(BaseModel):
    """Combined schema for the re_analyze LLM call: re-evaluated gaps +
    any new clarifying questions for gaps still open after the user's
    answers."""
    gaps: List[Gap] = []
    questions: List[Question] = []

class Answer(BaseModel):
    question_id: str
    answer: str
    answer_type: AnswerType = AnswerType.TEXT

class AgentStatus(str, Enum):
    IDLE = "IDLE"
    ANALYZING = "ANALYZING"
    WAITING_FOR_USER = "WAITING_FOR_USER"
    PLANNING = "PLANNING"
    GENERATING = "GENERATING"
    VALIDATING = "VALIDATING"
    COMPLETED = "COMPLETED"
    ERROR = "ERROR"
