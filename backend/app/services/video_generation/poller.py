"""Background poller for video generation jobs.

Runs continuously in the FastAPI lifespan background.
Polls incomplete jobs, updates their status, handles retries, and triggers
stitching when all jobs for a project reach a terminal state.
"""
import asyncio
import logging
from datetime import datetime, UTC

from app.core.config import settings
from app.db import video_jobs_repository as repo
from app.schemas.video_job import VideoJobStatus
from app.services.video_generation.client_factory import get_video_client
from app.services.video_generation.base_client import PermanentVideoError, TransientVideoError
from app.services.video_generation.storage import store_video, VideoStorageError
from app.services.video_generation.stitcher import stitch_project_videos

logger = logging.getLogger(__name__)

_job_error_counts: dict[str, int] = {}


async def _process_completed_job(job, result: dict) -> None:
    """Download and store video, then update job to COMPLETED."""
    temp_url = result.get("video_url")
    if not temp_url:
        logger.error(f"Job {job.job_id} marked COMPLETED but no video_url returned.")
        repo.update_job_status(
            job.job_id,
            VideoJobStatus.FAILED,
            error_message="Provider marked COMPLETED but returned no video URL."
        )
        return

    try:
        client = get_video_client()
        downloader = client.download_video if getattr(client, "requires_authenticated_download", False) else None
        if downloader:
            permanent_url = await store_video(temp_url, job.project_id, job.shot_id, downloader=downloader)
        else:
            permanent_url = await store_video(temp_url, job.project_id, job.shot_id)
        repo.update_job_status(
            job.job_id,
            VideoJobStatus.COMPLETED,
            video_url=permanent_url,
            completed_at=datetime.now(UTC)
        )
    except VideoStorageError as exc:
        logger.error(f"Failed to store video for job {job.job_id}: {exc}")
        repo.update_job_status(
            job.job_id,
            VideoJobStatus.FAILED,
            error_message=f"Storage failure: {exc}"
        )
    _job_error_counts.pop(job.job_id, None)


async def _handle_failed_job(job, result: dict, client) -> None:
    """Handle retries or terminal failure."""
    error_msg = result.get("error", "Unknown provider error")
    max_retries = getattr(settings, "video_max_retries", 2)
    
    if result.get("retryable") is False:
        logger.error(
            f"Job {job.job_id} failed with non-retryable error: {error_msg}. Terminal FAILED."
        )
        repo.update_job_status(
            job.job_id,
            VideoJobStatus.FAILED,
            error_message=error_msg,
            completed_at=datetime.now(UTC)
        )
        _job_error_counts.pop(job.job_id, None)
        return

    if job.retry_count < max_retries:
        new_count = job.retry_count + 1
        logger.warning(
            f"Job {job.job_id} failed. Retry {new_count}/{max_retries}. Error: {error_msg}"
        )
        
        # We must re-submit immediately or mark RETRYING so the loop picks it up.
        # Let's re-submit inline if possible.
        try:
            # 1. Fetch graph state to get prompt details
            from app.api.routes.scripts import _get_state_values
            state = await _get_state_values(job.project_id)
            prompt_set = state.get("prompt_set")
            prompt = next((p for p in prompt_set.prompts if p.prompt_id == job.prompt_id), None)
            spec = state.get("video_specification")
            
            if not prompt or not spec:
                raise Exception("Prompt or Spec missing from state")
                
            if not getattr(settings, "use_mock_video_api", False):
                from app.services.video_generation.cost import estimate_clip_cost_usd
                cost = estimate_clip_cost_usd(prompt.duration_seconds, getattr(settings, "veo_resolution", "720p"))
                logger.info(f"Retrying job {job.job_id} at estimated cost: ${cost:.2f}")
                
            # 2. Resubmit
            ext_job_id = await client.submit_job(
                prompt_text=prompt.prompt_text,
                duration_seconds=prompt.duration_seconds,
                aspect_ratio=spec.output_requirements.aspect_ratio or "16:9",
                negative_prompt=prompt.negative_constraints,
                # omitting reference_image_url for simplicity in retry
            )
            
            repo.update_job_status(
                job.job_id,
                VideoJobStatus.SUBMITTED,
                external_job_id=ext_job_id,
                error_message=error_msg,
                retry_count=new_count
            )
            logger.info(f"Successfully resubmitted job {job.job_id} -> {ext_job_id}")
            
        except Exception as exc:
            logger.error(f"Failed to resubmit job {job.job_id}: {exc}")
            repo.update_job_status(
                job.job_id,
                VideoJobStatus.FAILED,
                error_message=f"Failed to resubmit: {exc}",
                completed_at=datetime.now(UTC),
                retry_count=new_count
            )
    else:
        logger.error(
            f"Job {job.job_id} reached max retries ({max_retries}). Terminal FAILED. Error: {error_msg}"
        )
        repo.update_job_status(
            job.job_id,
            VideoJobStatus.FAILED,
            error_message=error_msg,
            completed_at=datetime.now(UTC)
        )
    _job_error_counts.pop(job.job_id, None)


async def _check_and_trigger_stitching(project_id: str) -> None:
    """Check if all jobs are terminal. If so, trigger stitching."""
    # We rely on the project's final_video_url as our "already stitched" flag.
    if repo.get_project_final_video_url(project_id):
        return

    jobs = repo.get_jobs_for_project(project_id)
    if not jobs:
        return

    # Check if all jobs are terminal
    terminal_states = {VideoJobStatus.COMPLETED, VideoJobStatus.FAILED}
    if not all(job.status in terminal_states for job in jobs):
        return  # still waiting for some jobs

    # All jobs terminal. Trigger stitch.
    # To prevent multiple concurrent stitches for the same project if polls race,
    # we synchronously mark a dummy URL (or we just let the DB handle it cleanly).
    # Since this poller runs sequentially in one task loop, races are minimized.
    
    # We'll mark it as IN_PROGRESS_STITCHING implicitly by firing the stitcher task.
    logger.info(f"All jobs for project {project_id} reached terminal state. Triggering stitch.")
    
    try:
        # We await it directly here because the poller loop is okay to block on stitching
        # (or we could fire and forget, but awaiting prevents race conditions nicely)
        # Note: In a heavy production system, stitching should be a background task.
        # Since this phase avoids Celery, we'll await it but ensure it doesn't crash the poller.
        await stitch_project_videos(project_id)
    except Exception as exc:
        logger.exception(f"Stitching failed for project {project_id}: {exc}")
        # The project stays with final_video_url = None, and API routes will
        # report PARTIAL_FAILURE with no video.


async def run_poller_loop() -> None:
    """Main background loop."""
    interval = getattr(settings, "video_poll_interval_seconds", 10)
    logger.info(f"Starting video generation poller loop (interval={interval}s)")

    client = get_video_client()

    while True:
        try:
            jobs = repo.get_incomplete_jobs()
            if not jobs:
                await asyncio.sleep(interval)
                continue

            # Group jobs by project so we can check stitching later
            active_projects = set()

            for job in jobs:
                active_projects.add(job.project_id)

                # QUEUED and RETRYING jobs are intentionally not resubmitted by the poller.
                # Initial submissions are handled by the generate_videos node.
                if job.status in (VideoJobStatus.QUEUED, VideoJobStatus.RETRYING):
                    continue

                if job.status not in (VideoJobStatus.SUBMITTED, VideoJobStatus.PROCESSING):
                    continue
                    
                if job.submitted_at:
                    now = datetime.now(UTC)
                    sub_at = job.submitted_at
                    if sub_at.tzinfo is None:
                        sub_at = sub_at.replace(tzinfo=UTC)
                    
                    if (now - sub_at).total_seconds() > getattr(settings, "video_job_max_wait_seconds", 900):
                        logger.error(f"Job {job.job_id} timed out waiting for provider.")
                        repo.update_job_status(
                            job.job_id,
                            VideoJobStatus.FAILED,
                            error_message="timed out waiting for provider",
                            completed_at=now
                        )
                        _job_error_counts.pop(job.job_id, None)
                        continue

                if not job.external_job_id:
                    logger.warning(f"Job {job.job_id} is {job.status.value} but missing external_job_id.")
                    continue

                try:
                    result = await client.check_status(job.external_job_id)
                    _job_error_counts.pop(job.job_id, None)
                except PermanentVideoError as exc:
                    logger.error(f"Permanent error checking status for {job.external_job_id}: {exc}")
                    await _handle_failed_job(job, {"error": str(exc)}, client)
                    continue
                except Exception as exc:
                    _job_error_counts[job.job_id] = _job_error_counts.get(job.job_id, 0) + 1
                    err_count = _job_error_counts[job.job_id]
                    max_errs = getattr(settings, "video_status_max_consecutive_errors", 20)
                    
                    if err_count >= max_errs:
                        logger.error(f"Job {job.job_id} status check unreachable {err_count} times. Marking FAILED.")
                        repo.update_job_status(
                            job.job_id,
                            VideoJobStatus.FAILED,
                            error_message=f"status check unreachable {err_count} times",
                            completed_at=datetime.now(UTC)
                        )
                        _job_error_counts.pop(job.job_id, None)
                    else:
                        logger.warning(f"Transient error checking status for {job.external_job_id} ({err_count}/{max_errs}): {exc}")
                    continue

                new_status_str = result.get("status")
                if new_status_str == "PROCESSING":
                    if job.status != VideoJobStatus.PROCESSING:
                        repo.update_job_status(job.job_id, VideoJobStatus.PROCESSING)
                elif new_status_str == "COMPLETED":
                    await _process_completed_job(job, result)
                elif new_status_str == "FAILED":
                    await _handle_failed_job(job, result, client)

            # Check if any active projects are now fully complete
            for pid in active_projects:
                await _check_and_trigger_stitching(pid)
                
            await asyncio.sleep(interval)

        except asyncio.CancelledError:
            logger.info("Video poller loop cancelled.")
            break
        except Exception as exc:
            logger.exception(f"Unexpected error in video poller loop: {exc}")
        
        await asyncio.sleep(interval)
