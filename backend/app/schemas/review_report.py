"""Review Report schema for the deterministic Prompt Reviewer Agent.

The reviewer produces a ReviewReport containing zero or more ReviewIssue
objects.  The report's ``status`` is always one of three passing values —
the reviewer never blocks the pipeline; it either passes cleanly, passes
after applying auto-fixes, or passes with advisory warnings attached.
"""
from pydantic import BaseModel, Field
from typing import Literal, Optional
from enum import Enum


class IssueSeverity(str, Enum):
    BLOCKER = "BLOCKER"
    WARNING = "WARNING"
    INFO = "INFO"


class IssueCategory(str, Enum):
    STRUCTURAL = "STRUCTURAL"
    CONTENT_QUALITY = "CONTENT_QUALITY"
    CONTINUITY_DRIFT = "CONTINUITY_DRIFT"
    DIALOGUE_TIMING = "DIALOGUE_TIMING"
    TOOL_COMPATIBILITY = "TOOL_COMPATIBILITY"
    SAFETY = "SAFETY"


class ReviewStatus(str, Enum):
    PASSED = "PASSED"
    PASSED_WITH_FIXES = "PASSED_WITH_FIXES"
    PASSED_WITH_WARNINGS = "PASSED_WITH_WARNINGS"


class ReviewIssue(BaseModel):
    issue_id: str
    severity: IssueSeverity
    category: IssueCategory
    prompt_id: Optional[str] = None
    shot_id: Optional[str] = None
    scene_id: Optional[str] = None
    field: Optional[str] = None          # e.g. "prompt_text", "negative_constraints"
    message: str
    detected_value: Optional[str] = None
    expected_value: Optional[str] = None
    auto_fixable: bool = False


class ReviewReport(BaseModel):
    status: ReviewStatus = ReviewStatus.PASSED
    issues: list[ReviewIssue] = []
    fixes_applied: list[str] = []      # human-readable log of what was auto-fixed
    retries_used: int = 0
    stats: dict = Field(default_factory=dict)
