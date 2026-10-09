"""Abstract base class for video generation clients.

All model-specific clients (Veo, Runway, Kling, etc.) must implement this
interface.  The system is designed to be model-agnostic: orchestration,
polling, storage, and stitching work identically regardless of which
concrete client is plugged in.
"""
from abc import ABC, abstractmethod
from typing import Optional


class VideoGenerationError(Exception):
    """Raised when a video generation operation fails."""
    pass


class VideoGenerationClient(ABC):

    @abstractmethod
    async def submit_job(
        self,
        prompt_text: str,
        duration_seconds: float,
        aspect_ratio: str,
        negative_prompt: Optional[str] = None,
        reference_image_url: Optional[str] = None,
    ) -> str:
        """Submit a generation job and return an external_job_id.

        This call should be non-blocking (or at most wait for the provider
        to acknowledge the job) — it must NOT wait for the video to finish
        rendering.
        """

    @abstractmethod
    async def check_status(self, external_job_id: str) -> dict:
        """Poll the status of a previously submitted job.

        Returns a dict with:
            - "status": one of "PROCESSING", "COMPLETED", "FAILED"
            - "video_url": str | None  (set when COMPLETED)
            - "error": str | None      (set when FAILED)
        """
