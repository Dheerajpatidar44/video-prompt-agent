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
from app.services.video_generation.rate_limiter import compute_submit_backoff, get_video_submit_limiter
from app.services.video_generation.storage import store_video, VideoStorageError
from app.services.video_generation.stitcher import stitch_project_videos
from app.utils.aspect_ratio import VEO_SUPPORTED_ASPECT_RATIOS, get_spec_aspect_ratio

logger = logging.getLogger(__name__)

_job_error_counts: dict[str, int] = {}

# Tracks how many image-regen retries have been spent per job_id.
_image_regen_counts: dict[str, int] = {}

# In-process lock preventing duplicate concurrent stitch runs per project.
_stitching_projects: set[str] = set()

# Error substrings that indicate Veo rejected the image due to safety or policy
# (e.g. Code 15236754 - celebrity likeness / usage guidelines).
_IMAGE_SAFETY_TERMS = (
    "15236754",
    "usage guidelines",
    "violates",
    "input image",
    "image violates",
    "image not supported",
    "celebrity",
    "likeness",
)


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
    _image_regen_counts.pop(job.job_id, None)


async def _handle_failed_job(job, result: dict, client) -> None:
    """Handle retries or terminal failure."""
    error_msg = result.get("error", "Unknown provider error")
    err_str = str(error_msg).lower()
    max_retries = getattr(settings, "video_max_retries", 2)
    max_img_retries = getattr(settings, "video_image_regen_max_retries", 1)
    
    # Check if failure is due to Veo image-safety policy rejection (e.g. 15236754 or celebrity likeness)
    # Check this BEFORE retryable=False so image regeneration retry still runs.
    is_image_rejection = bool(result.get("image_safety_rejected")) or any(
        term in err_str for term in _IMAGE_SAFETY_TERMS
    )
    img_regen_used = _image_regen_counts.get(job.job_id, 0)

    if is_image_rejection:
        if img_regen_used < max_img_retries:
            new_img_count = img_regen_used + 1
            logger.warning(
                f"Job {job.job_id} rejected by Veo (image safety/policy error: {error_msg}). "
                f"Regenerating keyframe image (attempt {new_img_count}/{max_img_retries})."
            )
            await _regenerate_image_and_resubmit(job, error_msg, client, new_img_count)
            return
        else:
            logger.error(
                f"Job {job.job_id} failed again with Veo safety policy error after "
                f"{img_regen_used} image regeneration attempt(s). Terminal FAILED. Error: {error_msg}"
            )
            repo.update_job_status(
                job.job_id,
                VideoJobStatus.FAILED,
                error_message=f"Veo safety policy rejection persisted after {img_regen_used} image regeneration attempt(s): {error_msg}",
                completed_at=datetime.now(UTC)
            )
            _job_error_counts.pop(job.job_id, None)
            _image_regen_counts.pop(job.job_id, None)
            return

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
        _image_regen_counts.pop(job.job_id, None)
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
                cost = estimate_clip_cost_usd(prompt.duration_seconds, getattr(settings, "veo_resolution", "720p"), model=getattr(settings, "veo_model", ""))
                logger.info(f"Retrying job {job.job_id} at estimated cost: ${cost:.2f}")
                
            # 2. Resubmit with reference assets
            shot_manifest = state.get("shot_image_manifest") or {}
            shot_id_val = getattr(prompt, "shot_id", getattr(job, "shot_id", ""))
            shot_items = shot_manifest.get(shot_id_val) or []
            structured_assets = [
                {
                    "path": item["path"],
                    "role": item.get("role", "ENVIRONMENT"),
                    "asset_id": item.get("asset_id", ""),
                    "reused": item.get("reused", False),
                }
                for item in shot_items if item.get("path")
            ][:3]

            limiter = get_video_submit_limiter()
            if not getattr(settings, "use_mock_video_api", False):
                await limiter.wait_for_slot(
                    getattr(settings, "video_submit_min_interval_seconds", 2.5)
                )

            try:
                ext_job_id = await client.submit_job(
                    prompt_text=prompt.prompt_text,
                    duration_seconds=prompt.duration_seconds,
                    aspect_ratio=get_spec_aspect_ratio(
                        spec,
                        prompt_set,
                        fallback=settings.default_aspect_ratio,
                        allowed=VEO_SUPPORTED_ASPECT_RATIOS,
                    ),
                    negative_prompt=prompt.negative_constraints,
                    reference_assets=structured_assets if structured_assets else None,
                )
            except TransientVideoError as transient_exc:
                _, is_quota, delay = compute_submit_backoff(
                    transient_exc,
                    new_count - 1,
                    base_seconds=getattr(settings, "video_submit_backoff_base_seconds", 15.0),
                    max_seconds=getattr(settings, "video_submit_backoff_max_seconds", 60.0),
                )
                if is_quota and delay > 0.0:
                    limiter.extend_cooldown(delay)
                raise
            
            repo.update_job_status(
                job.job_id,
                VideoJobStatus.SUBMITTED,
                external_job_id=ext_job_id,
                error_message=error_msg,
                retry_count=new_count,
                submitted_at=datetime.now(UTC),
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
            _image_regen_counts.pop(job.job_id, None)
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
        _image_regen_counts.pop(job.job_id, None)
    _job_error_counts.pop(job.job_id, None)


async def _regenerate_image_and_resubmit(job, error_msg: str, client, new_img_count: int) -> None:
    """Regenerate keyframe image for this shot and resubmit to Veo."""
    _image_regen_counts[job.job_id] = new_img_count
    try:
        from app.api.routes.scripts import _get_state_values
        state = await _get_state_values(job.project_id)
        prompt_set = state.get("prompt_set")
        spec = state.get("video_specification")

        prompt = next(
            (p for p in prompt_set.prompts if p.prompt_id == job.prompt_id), None
        ) if prompt_set and getattr(prompt_set, "prompts", None) else None

        if not prompt or not spec:
            raise Exception("Prompt or Spec missing from state — cannot regenerate image.")

        # Determine keyframe image prompt (same field used by generate_images node)
        raw_kf_prompt = getattr(prompt, "keyframe_image_prompt", None)
        base_prompt = (
            raw_kf_prompt if (raw_kf_prompt and raw_kf_prompt.strip())
            else prompt.prompt_text
        )
        # Add subtle facial/framing variation so regenerated keyframe avoids identical celebrity/safety false positive
        effective_prompt = (
            f"Create an original fictional non-celebrity character appearance with subtle variation in "
            f"facial features, framing, and lighting while preserving the exact scene composition: {base_prompt}"
        )

        # Collect user reference images so the regenerated image
        # still uses character/product references for visual consistency.
        user_refs = state.get("reference_images") or {}
        char_refs = user_refs.get("character") or []
        prod_refs = user_refs.get("product") or []
        brand_refs = user_refs.get("brand") or []
        all_user_refs = (char_refs + prod_refs + brand_refs)[:3]

        from app.services.image_generation.gemini_image_service import get_gemini_image_service
        image_service = get_gemini_image_service()

        project_id = job.project_id
        shot_id = getattr(prompt, "shot_id", getattr(job, "shot_id", "unknown"))
        filename = f"{project_id}_{shot_id}_keyframe_regen{new_img_count}.png"

        logger.info(
            f"[ImageRegen] Job {job.job_id}: generating fresh keyframe for shot '{shot_id}' "
            f"(regen #{new_img_count}). Prompt: {effective_prompt[:80]}..."
        )

        target_aspect = get_spec_aspect_ratio(
            spec,
            prompt_set,
            fallback=settings.default_aspect_ratio,
        )
        video_aspect = get_spec_aspect_ratio(
            spec,
            prompt_set,
            fallback=settings.default_aspect_ratio,
            allowed=VEO_SUPPORTED_ASPECT_RATIOS,
        )

        new_image_path = await image_service.generate_image(
            prompt=effective_prompt,
            aspect_ratio=target_aspect,
            ref_images=all_user_refs if all_user_refs else None,
            custom_filename=filename,
        )

        if not new_image_path:
            raise Exception("Image service returned None — fresh keyframe could not be generated.")

        logger.info(
            f"[ImageRegen] Job {job.job_id}: new keyframe saved at '{new_image_path}'. "
            "Resubmitting to Veo..."
        )

        # Build structured_assets with the newly generated image
        structured_assets = [{
            "path": new_image_path,
            "role": "MASTER_KEYFRAME",
            "asset_id": f"{shot_id}_keyframe_regen{new_img_count}",
            "reused": False,
        }]

        limiter = get_video_submit_limiter()
        if not getattr(settings, "use_mock_video_api", False):
            await limiter.wait_for_slot(
                getattr(settings, "video_submit_min_interval_seconds", 2.5)
            )

        ext_job_id = await client.submit_job(
            prompt_text=prompt.prompt_text,
            duration_seconds=prompt.duration_seconds,
            aspect_ratio=video_aspect,
            negative_prompt=prompt.negative_constraints,
            reference_assets=structured_assets,
        )

        repo.update_job_status(
            job.job_id,
            VideoJobStatus.SUBMITTED,
            external_job_id=ext_job_id,
            error_message=f"[image_regen #{new_img_count}] {error_msg}",
            submitted_at=datetime.now(UTC),
        )
        logger.info(
            f"[ImageRegen] Job {job.job_id} successfully resubmitted with fresh keyframe -> {ext_job_id}"
        )

    except Exception as exc:
        logger.error(
            f"[ImageRegen] Job {job.job_id}: image regeneration / resubmit failed: {exc}."
        )
        repo.update_job_status(
            job.job_id,
            VideoJobStatus.FAILED,
            error_message=f"Image regeneration retry failed: {exc}",
            completed_at=datetime.now(UTC),
        )
        _image_regen_counts.pop(job.job_id, None)
        _job_error_counts.pop(job.job_id, None)


async def _check_and_trigger_stitching(project_id: str) -> None:
    """Check if all jobs are terminal. If so, trigger stitching."""
    if project_id in _stitching_projects:
        return
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

    # If every single job failed, mark project FAILED so it doesn't stay stuck on GENERATING_VIDEOS
    if all(job.status == VideoJobStatus.FAILED for job in jobs):
        logger.warning(f"All {len(jobs)} video jobs failed for project {project_id}. Marking project FAILED.")
        if hasattr(repo, "update_project_status"):
            try:
                repo.update_project_status(project_id, "FAILED")
            except Exception as exc:
                logger.warning(f"Could not update project {project_id} status to FAILED: {exc}")
        return

    logger.info(f"All jobs for project {project_id} reached terminal state. Triggering stitch.")
    _stitching_projects.add(project_id)

    try:
        final_url = await stitch_project_videos(project_id)
        if not final_url and not repo.get_project_final_video_url(project_id):
            logger.error(f"Stitching produced no final video URL for project {project_id}. Marking FAILED.")
            if hasattr(repo, "update_project_status"):
                try:
                    repo.update_project_status(project_id, "FAILED")
                except Exception:
                    pass
    except Exception as exc:
        logger.exception(f"Stitching failed for project {project_id}: {exc}")
        if hasattr(repo, "update_project_status"):
            try:
                repo.update_project_status(project_id, "FAILED")
            except Exception:
                pass
    finally:
        _stitching_projects.discard(project_id)


async def run_poller_loop() -> None:
    """Main background loop."""
    interval = getattr(settings, "video_poll_interval_seconds", 10)
    logger.info(f"Starting video generation poller loop (interval={interval}s)")

    while True:
        try:
            jobs = repo.get_incomplete_jobs()
            if not jobs:
                await asyncio.sleep(interval)
                continue

            try:
                client = get_video_client()
            except Exception as client_err:
                logger.error(f"Cannot poll video jobs - video client initialization failed: {client_err}")
                await asyncio.sleep(interval)
                continue

            # Group jobs by project so we can check stitching later
            active_projects = set()
            limiter = get_video_submit_limiter()

            for job in jobs:
                active_projects.add(job.project_id)

                # In-process queued submissions actively waiting through rate pacing / 429
                # backoff are skipped from premature timeout until submitted or failed.
                is_active_submission = (
                    job.status == VideoJobStatus.QUEUED
                    and job.job_id in limiter.active_job_ids
                )

                if job.submitted_at and not is_active_submission:
                    now = datetime.now(UTC)
                    sub_at = job.submitted_at
                    if sub_at.tzinfo is None:
                        sub_at = sub_at.replace(tzinfo=UTC)

                    if (now - sub_at).total_seconds() > getattr(settings, "video_job_max_wait_seconds", 900):
                        logger.error(f"Job {job.job_id} ({job.status.value}) timed out waiting for completion.")
                        repo.update_job_status(
                            job.job_id,
                            VideoJobStatus.FAILED,
                            error_message="timed out waiting for provider",
                            completed_at=now
                        )
                        _job_error_counts.pop(job.job_id, None)
                        continue

                # QUEUED and RETRYING jobs are submitted by generate_videos (or marked failed on startup recovery).
                if job.status in (VideoJobStatus.QUEUED, VideoJobStatus.RETRYING):
                    continue

                if job.status not in (VideoJobStatus.SUBMITTED, VideoJobStatus.PROCESSING):
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
