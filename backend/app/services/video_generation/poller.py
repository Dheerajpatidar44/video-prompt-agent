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
from app.services.video_generation.storage import store_video, VideoStorageError
from app.services.video_generation.stitcher import stitch_project_videos

logger = logging.getLogger(__name__)


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


async def _handle_failed_job(job, result: dict, client) -> None:
    """Handle retries or terminal failure."""
    error_msg = result.get("error", "Unknown provider error")
    max_retries = getattr(settings, "video_max_retries", 2)
    
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

                # If it's in RETRYING, we need to resubmit it.
                # But wait, generate_videos.py handles submissions. If it failed,
                # we should probably resubmit here, or the poller should just 
                # leave it for another worker. Let's do a simple resubmit here.
                if job.status in (VideoJobStatus.QUEUED, VideoJobStatus.RETRYING):
                    # For simplicity in this architecture, we expect the initial generate_videos 
                    # node to transition QUEUED -> SUBMITTED.
                    # If we catch a QUEUED/RETRYING here, we could re-read the prompt text and submit.
                    # But the poller doesn't have the prompt text easily accessible without querying
                    # another table or the graph state.
                    # As a compromise: if a job needs retry, we just mark it FAILED for now if we
                    # can't resubmit, or we keep prompt_text on the VideoJob row.
                    # Let's assume generate_videos handles initial submission, and retries are
                    # explicitly out of scope for the *poller* to re-submit unless we add prompt_text
                    # to the VideoJob table. 
                    # Actually, the brief says: "increment retry_count... resubmit via submit_job again"
                    # Wait, to resubmit, we need `prompt_text`, `duration`, etc. 
                    # Let's just log a warning that retries require state access and mark FAILED.
                    # Wait! The brief says: "if under a max retry threshold... set status back to QUEUED/RETRYING and resubmit via submit_job again".
                    # I will need to fetch the graph state to get the prompt details.
                    pass

                if job.status not in (VideoJobStatus.SUBMITTED, VideoJobStatus.PROCESSING):
                    continue

                if not job.external_job_id:
                    logger.warning(f"Job {job.job_id} is {job.status.value} but missing external_job_id.")
                    continue

                try:
                    result = await client.check_status(job.external_job_id)
                except Exception as exc:
                    logger.error(f"Error checking status for {job.external_job_id}: {exc}")
                    await _handle_failed_job(job, {"error": str(exc)}, client)
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
