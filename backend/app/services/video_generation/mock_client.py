"""Mock video generation client for development and testing.

Simulates realistic asynchronous job behaviour:
  - submit_job: returns a fake external id after a short delay (network latency).
  - check_status: returns PROCESSING for the first N polls, then COMPLETED with
    a real, publicly-accessible sample MP4 URL that downstream code can actually
    fetch without 404-ing.

A ``simulate_failure`` constructor flag (or the ``MOCK_VIDEO_SIMULATE_FAILURE``
env var) causes every Nth job to fail, so failure-handling code paths can be
exercised in tests without a real API.
"""
import asyncio
import logging
import os
import uuid
from typing import Optional

from app.services.video_generation.base_client import (
    VideoGenerationClient,
    VideoGenerationError,
    PermanentVideoError,
)

logger = logging.getLogger(__name__)

# A small, real, freely-usable sample MP4 hosted by W3Schools.
_SAMPLE_VIDEO_URL = "http://127.0.0.1:3000/ad.mp4"


class MockVideoClient(VideoGenerationClient):
    """In-memory mock that simulates an async video generation provider.

    Attributes:
        submit_delay:  seconds to sleep in submit_job (simulates network RTT).
        polls_before_done:  how many check_status calls return PROCESSING before
                            the job transitions to COMPLETED (or FAILED).
        simulate_failure:  if True, every ``fail_every_nth`` job will fail.
        fail_every_nth:  controls which jobs fail (1-indexed counter).

    The mock keeps an internal dict of {external_job_id: poll_count} so each
    job progresses independently.
    """

    def __init__(
        self,
        *,
        submit_delay: float = 0.3,
        polls_before_done: int = 3,
        simulate_failure: bool | None = None,
        fail_every_nth: int = 3,
    ):
        self.submit_delay = submit_delay
        self.polls_before_done = polls_before_done

        # Allow env-var override for test convenience.
        if simulate_failure is None:
            simulate_failure = os.getenv("MOCK_VIDEO_SIMULATE_FAILURE", "").lower() in (
                "1", "true", "yes",
            )
        self.simulate_failure = simulate_failure
        self.fail_every_nth = fail_every_nth

        # Internal state
        self._jobs: dict[str, int] = {}          # external_id → poll_count
        self._submit_counter: int = 0            # total jobs submitted (for failure pattern)
        self._in_flight: int = 0                 # currently active jobs (for concurrency tests)
        self._peak_in_flight: int = 0            # high-water mark

    # -- Public hooks for tests -------------------------------------------------

    @property
    def in_flight(self) -> int:
        return self._in_flight

    @property
    def peak_in_flight(self) -> int:
        return self._peak_in_flight

    # -- Interface implementation -----------------------------------------------

    async def submit_job(
        self,
        prompt_text: str,
        duration_seconds: float,
        aspect_ratio: str,
        negative_prompt: Optional[str] = None,
        reference_image_url: Optional[str] = None,
    ) -> str:
        await asyncio.sleep(self.submit_delay)

        external_id = f"mock-{uuid.uuid4().hex[:12]}"
        self._jobs[external_id] = 0
        self._submit_counter += 1
        self._in_flight += 1
        self._peak_in_flight = max(self._peak_in_flight, self._in_flight)

        ref_log = f", ref_image={reference_image_url}" if reference_image_url else ""
        from app.services.video_generation.cost import billed_seconds
        billed = billed_seconds(duration_seconds)
        if billed != round(duration_seconds):
            logger.info(
                f"MockVideoClient.submit_job: id={external_id}, "
                f"planned={duration_seconds}s (snapped to {billed}s for Veo), aspect={aspect_ratio}{ref_log}, "
                f"submit_counter={self._submit_counter}"
            )
        else:
            logger.info(
                f"MockVideoClient.submit_job: id={external_id}, "
                f"duration={duration_seconds}s, aspect={aspect_ratio}{ref_log}, "
                f"submit_counter={self._submit_counter}"
            )
        return external_id

    async def check_status(self, external_job_id: str) -> dict:
        if external_job_id not in self._jobs:
            raise PermanentVideoError(
                f"Unknown external job id: {external_job_id}"
            )

        self._jobs[external_job_id] += 1
        poll_count = self._jobs[external_job_id]

        # Simulate failure on every Nth submitted job.
        if (
            self.simulate_failure
            and self._submit_counter > 0
            and self._submit_counter % self.fail_every_nth == 0
            and poll_count >= self.polls_before_done
        ):
            # Only count as no longer in-flight when it reaches terminal state
            if poll_count == self.polls_before_done:
                self._in_flight = max(0, self._in_flight - 1)
            logger.info(f"MockVideoClient: job {external_job_id} → FAILED (simulated)")
            return {
                "status": "FAILED",
                "video_url": None,
                "error": "Simulated failure for testing",
            }

        if poll_count < self.polls_before_done:
            logger.debug(
                f"MockVideoClient: job {external_job_id} → PROCESSING "
                f"(poll {poll_count}/{self.polls_before_done})"
            )
            return {"status": "PROCESSING", "video_url": None, "error": None}

        # Reached completion
        if poll_count == self.polls_before_done:
            self._in_flight = max(0, self._in_flight - 1)
        logger.info(f"MockVideoClient: job {external_job_id} → COMPLETED")
        return {
            "status": "COMPLETED",
            "video_url": _SAMPLE_VIDEO_URL,
            "error": None,
        }
