"""Video Job schemas for the video generation phase.

Tracks per-shot generation jobs and overall project video status.
"""
from pydantic import BaseModel, Field
from typing import Optional, Literal, List
from enum import Enum
from datetime import datetime


class VideoJobStatus(str, Enum):
    QUEUED = "QUEUED"
    SUBMITTED = "SUBMITTED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    RETRYING = "RETRYING"


class VideoJob(BaseModel):
    job_id: str
    project_id: str
    prompt_id: str
    shot_id: str
    sequence_number: int
    status: VideoJobStatus = VideoJobStatus.QUEUED
    external_job_id: Optional[str] = None
    video_url: Optional[str] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    submitted_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None


class ProjectVideoStatus(BaseModel):
    project_id: str
    total_shots: int
    completed_shots: int
    failed_shots: int
    status: Literal["IN_PROGRESS", "COMPLETED", "PARTIAL_FAILURE"]
    final_video_url: Optional[str] = None
    jobs: List[VideoJob] = []
