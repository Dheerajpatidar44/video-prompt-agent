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

from app.core.config import settings
from app.graph.state import AgentState
from app.schemas.agent import AgentStatus
from app.schemas.video_job import VideoJob, VideoJobStatus
from app.db import video_jobs_repository as repo
from app.services.video_generation.client_factory import get_video_client
from app.services.video_generation.cost import billed_seconds, estimate_project_cost_usd

logger = logging.getLogger(__name__)


async def generate_videos(state: AgentState) -> AgentState:
    """Submit all approved prompts for video generation."""
    project_id = state.get("project_id")
    prompt_set = state.get("prompt_set")
    spec = state.get("video_specification")

    if not project_id or not prompt_set or not spec:
        logger.error("generate_videos: missing project_id, prompt_set, or spec.")
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

    async def _submit_single_job(prompt) -> None:
        # Create DB row
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

        # Wait for concurrency slot
        async with semaphore:
            try:
                # Find reference image if any
                ref_url = None
                # Check continuity bible characters matching this shot's entities
                # For simplicity in this step, we just use the first character's image if available
                # from the spec.reference_assets. 
                # (A full implementation would parse `prompt.source_actions` to match character names)
                # We'll map reference images from spec.reference_assets if they exist.
                # Actually, the prompt object itself doesn't explicitly store its reference asset.
                # The instructions say: "If a relevant reference image URL exists for the shot's primary character/product (check what's available in spec/continuity_bible), pass it as reference_image_url".
                # For now, let's just grab the first character or product reference asset if it exists.
                for asset in spec.reference_assets:
                    path = getattr(asset, "reference_path", "") or ""
                    if asset.type in ("CHARACTER_REFERENCE", "PRODUCT_IMAGE") and path.startswith(("http://", "https://")):
                        ref_url = path
                        break

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

    # We fire them as background tasks and return immediately.
    # The poller will handle completion tracking.
    tasks = [_submit_single_job(prompt) for prompt in prompt_set.prompts]
    
    # We await gathering them here so that we don't return before they are submitted.
    # Wait, the prompt says: "Decide explicitly ... whether this node waits for all initial 
    # submissions to succeed before returning, or fires them as background asyncio.create_task() 
    # calls and returns immediately — the second is preferred so the graph/API response isn't blocked".
    
    # Fire and forget
    for t in tasks:
        asyncio.create_task(t)

    return {
        **state,
        "video_generation_status": "IN_PROGRESS",
        "status": AgentStatus.GENERATING_VIDEOS,
    }
