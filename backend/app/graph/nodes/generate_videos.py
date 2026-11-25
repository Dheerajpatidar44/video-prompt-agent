"""Generate Videos node — runs after review_prompts.

Triggered automatically after review_prompts passes. Fires off one
generation job per prompt, bounded by a concurrency limit, tracks each to
completion via the DB, and sets status to GENERATING_VIDEOS.

Returns immediately (jobs progress asynchronously in the background poller).
"""
import asyncio
import logging
import uuid
from datetime import datetime, UTC
from typing import Any

from app.core.config import settings
from app.graph.state import AgentState
from app.schemas.agent import AgentStatus
from app.schemas.video_job import VideoJob, VideoJobStatus
from app.db import video_jobs_repository as repo
from app.services.video_generation.client_factory import get_video_client
from app.services.video_generation.cost import billed_seconds, estimate_project_cost_usd

logger = logging.getLogger(__name__)

# Strong references prevent asyncio tasks from being garbage-collected mid-flight
_background_tasks: set[asyncio.Task] = set()


async def generate_videos(state: AgentState) -> AgentState:
    """Submit all approved prompts for video generation."""
    spec = state.get("video_specification")
    project_id = state.get("project_id") or (getattr(spec, "project_id", None) if spec else None)
    prompt_set = state.get("prompt_set")

    if not project_id or not prompt_set or not spec:
        logger.error(f"generate_videos: missing inputs. project_id={bool(project_id)}, prompt_set={bool(prompt_set)}, spec={bool(spec)}")
        return {**state, "status": AgentStatus.ERROR, "error": "Missing inputs for video generation."}

    if not settings.use_mock_video_api:
        durations = [prompt.duration_seconds for prompt in prompt_set.prompts]
        shots = len(durations)
        lengthened = sum(1 for d in durations if round(float(d), 3) < 4)
        exceeding = sum(1 for d in durations if round(float(d), 3) > 8)
        total_seconds = sum(billed_seconds(d, settings.veo_resolution) for d in durations)
        cost = estimate_project_cost_usd(durations, settings.veo_resolution, model=settings.veo_model)
        
        limit_hit = None
        if shots > settings.video_max_shots_per_project:
            limit_hit = f"shots ({shots} > {settings.video_max_shots_per_project}, raise VIDEO_MAX_SHOTS_PER_PROJECT)"
        elif total_seconds > settings.video_max_total_seconds_per_project:
            limit_hit = f"seconds ({total_seconds} > {settings.video_max_total_seconds_per_project}, raise VIDEO_MAX_TOTAL_SECONDS_PER_PROJECT)"
        elif cost > settings.video_max_estimated_cost_usd:
            limit_hit = f"cost (${cost:.2f} > ${settings.video_max_estimated_cost_usd:.2f}, raise VIDEO_MAX_ESTIMATED_COST_USD)"
            
        if limit_hit:
            logger.warning(
                f"Cost guard blocked video generation: exceeded {limit_hit}. "
                f"({lengthened} shots lengthened to 4s, {exceeding} exceed 8s)."
            )
            return {
                **state,
                "video_generation_status": "BLOCKED_COST_GUARD",
            }
        logger.info(
            f"Video generation project estimated cost: ${cost:.2f} for {shots} shots "
            f"({total_seconds} billed seconds, {lengthened} lengthened to 4s, {exceeding} exceed 8s)."
        )

    logger.info(f"Generating videos for project {project_id} ({len(prompt_set.prompts)} prompts).")

    client = get_video_client()
    concurrency_limit = getattr(settings, "video_generation_concurrency_limit", 3)
    semaphore = asyncio.Semaphore(concurrency_limit)

    # Synchronously persist all QUEUED job rows BEFORE returning so immediate
    # frontend polls never observe an empty video_jobs table.
    jobs_and_prompts: list[tuple[VideoJob, Any]] = []
    for prompt in prompt_set.prompts:
        job = VideoJob(
            job_id=f"vjob_{uuid.uuid4().hex[:12]}",
            project_id=project_id,
            prompt_id=prompt.prompt_id,
            shot_id=prompt.shot_id,
            sequence_number=prompt.sequence_number,
            status=VideoJobStatus.QUEUED,
            submitted_at=datetime.now(UTC),
            duration_seconds=prompt.duration_seconds,
        )
        repo.create_job(job)
        jobs_and_prompts.append((job, prompt))

    async def _submit_single_job(job: VideoJob, prompt) -> None:
        # Wait for concurrency slot
        async with semaphore:
            try:
                # Find reference image if any
                ref_url = None
                for asset in spec.reference_assets:
                    path = getattr(asset, "reference_path", "") or ""
                    if asset.type in ("CHARACTER_REFERENCE", "PRODUCT_IMAGE") and path.startswith(("http://", "https://")):
                        ref_url = path
                        break

                shot_manifest = state.get("shot_image_manifest") or {}
                shot_items = shot_manifest.get(prompt.shot_id) or []
                ref_urls = [item["path"] for item in shot_items if item.get("path")]
                if ref_urls:
                    ref_url = ref_urls[0]

                if not ref_url:
                    ref_dict = state.get("reference_images") or {}
                    chars = ref_dict.get("character") or []
                    prods = ref_dict.get("product") or []
                    brands = ref_dict.get("brand") or []
                    for candidate in (chars + prods + brands):
                        if candidate and candidate.startswith(("http://", "https://")):
                            ref_url = candidate
                            break

                ext_job_id = await client.submit_job(
                    prompt_text=prompt.prompt_text,
                    duration_seconds=prompt.duration_seconds,
                    aspect_ratio=spec.output_requirements.aspect_ratio or "16:9",
                    negative_prompt=prompt.negative_constraints,
                    reference_image_url=ref_url,
                    reference_image_urls=ref_urls if ref_urls else ([ref_url] if ref_url else None),
                    reference_assets=shot_items[:3] if shot_items else None,
                )

                # Update DB
                repo.update_job_status(
                    job.job_id,
                    VideoJobStatus.SUBMITTED,
                    external_job_id=ext_job_id
                )
                logger.info(f"Submitted video job {job.job_id} -> {ext_job_id}")

            except Exception as exc:
                logger.error(f"Failed to submit video job {job.job_id}: {exc}")
                repo.update_job_status(
                    job.job_id,
                    VideoJobStatus.FAILED,
                    error_message=str(exc)
                )

    # Fire background submissions with strong references so GC cannot cancel them.
    for job, prompt in jobs_and_prompts:
        task = asyncio.create_task(_submit_single_job(job, prompt))
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)

    return {
        **state,
        "video_generation_status": "IN_PROGRESS",
        "status": AgentStatus.GENERATING_VIDEOS,
    }
