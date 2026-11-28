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
from app.utils.aspect_ratio import VEO_SUPPORTED_ASPECT_RATIOS, get_spec_aspect_ratio
from app.schemas.video_job import VideoJob, VideoJobStatus
from app.db import video_jobs_repository as repo
from app.services.video_generation.client_factory import get_video_client
from app.services.video_generation.cost import billed_seconds, estimate_project_cost_usd
from app.services.video_generation.rate_limiter import (
    compute_submit_backoff,
    get_video_submit_limiter,
)

logger = logging.getLogger(__name__)

# Strong references prevent asyncio tasks from being garbage-collected mid-flight
_background_tasks: set[asyncio.Task] = set()


def _resolve_shot_reference_context(
    state: AgentState,
    spec: Any,
    prompt: Any,
) -> tuple[str | None, list[str] | None, list[dict] | None]:
    """Resolve primary reference URL and manifest assets for a single shot."""
    ref_url: str | None = None
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

    effective_urls = ref_urls if ref_urls else ([ref_url] if ref_url else None)
    effective_assets = shot_items[:3] if shot_items else None
    return ref_url, effective_urls, effective_assets


async def _submit_with_backoff(
    client: Any,
    *,
    job_id: str,
    submit_kwargs: dict[str, Any],
    min_interval: float,
    max_retries: int,
    base_backoff: float,
    max_backoff: float,
) -> str:
    """Submit a single provider job using paced spacing and shared 429 cooldown backoff."""
    limiter = get_video_submit_limiter()
    for attempt in range(max_retries + 1):
        await limiter.wait_for_slot(min_interval)
        try:
            return await client.submit_job(**submit_kwargs)
        except Exception as exc:
            should_retry, is_quota, delay = compute_submit_backoff(
                exc,
                attempt,
                base_seconds=base_backoff,
                max_seconds=max_backoff,
            )
            if not should_retry or attempt >= max_retries:
                raise
            if is_quota and delay > 0.0:
                limiter.extend_cooldown(delay)
            logger.warning(
                f"Video job {job_id} submission attempt {attempt + 1}/{max_retries + 1} hit transient error ({exc}). "
                f"Retrying in {delay:.1f}s..."
            )
            if delay > 0.0:
                await asyncio.sleep(delay)

    raise RuntimeError(f"Exhausted submit retries for job {job_id}")


async def _maybe_trigger_stitching_after_submit_failure(project_id: str) -> None:
    """Trigger stitching/project-FAILED check if a submit failure made all jobs terminal."""
    if not hasattr(repo, "get_jobs_for_project"):
        return
    try:
        proj_jobs = repo.get_jobs_for_project(project_id)
        if not proj_jobs:
            return
        terminal = (VideoJobStatus.COMPLETED, VideoJobStatus.FAILED)
        if all(j.status in terminal for j in proj_jobs):
            from app.services.video_generation.poller import _check_and_trigger_stitching
            await _check_and_trigger_stitching(project_id)
    except Exception as exc:
        logger.warning(f"Post-submit failure terminal check skipped for project {project_id}: {exc}")


async def generate_videos(
    state: AgentState,
    *,
    target_shot_ids: set[str] | None = None,
) -> AgentState:
    """Submit approved prompts (or a targeted subset on partial retry) for video generation."""
    spec = state.get("video_specification")
    project_id = state.get("project_id") or (getattr(spec, "project_id", None) if spec else None)
    prompt_set = state.get("prompt_set")

    if not project_id or not prompt_set or not spec:
        logger.error(f"generate_videos: missing inputs. project_id={bool(project_id)}, prompt_set={bool(prompt_set)}, spec={bool(spec)}")
        return {**state, "status": AgentStatus.ERROR, "error": "Missing inputs for video generation."}

    prompts_to_submit = (
        [p for p in prompt_set.prompts if p.shot_id in target_shot_ids]
        if target_shot_ids is not None
        else list(prompt_set.prompts)
    )
    if not prompts_to_submit:
        logger.error(f"generate_videos: no matching prompts to submit for project {project_id}.")
        return {**state, "status": AgentStatus.ERROR, "error": "No matching prompts found to generate."}

    if not settings.use_mock_video_api:
        durations = [prompt.duration_seconds for prompt in prompts_to_submit]
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

    logger.info(f"Generating videos for project {project_id} ({len(prompts_to_submit)} prompts).")

    client = get_video_client()
    limiter = get_video_submit_limiter()
    concurrency_limit = max(1, int(getattr(settings, "video_generation_concurrency_limit", 3) or 1))
    semaphore = asyncio.Semaphore(concurrency_limit)

    is_mock = bool(getattr(settings, "use_mock_video_api", False))
    min_interval = 0.0 if is_mock else float(getattr(settings, "video_submit_min_interval_seconds", 2.5))
    max_submit_retries = int(getattr(settings, "video_submit_max_retries", 4))
    base_backoff = 0.0 if is_mock else float(getattr(settings, "video_submit_backoff_base_seconds", 15.0))
    max_backoff = 0.0 if is_mock else float(getattr(settings, "video_submit_backoff_max_seconds", 60.0))

    # Synchronously persist all QUEUED job rows BEFORE returning so immediate
    # frontend polls never observe an empty video_jobs table.
    jobs_and_prompts: list[tuple[VideoJob, Any]] = []
    for prompt in prompts_to_submit:
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
        limiter.active_job_ids.add(job.job_id)
        jobs_and_prompts.append((job, prompt))

    async def _submit_single_job(job: VideoJob, prompt) -> None:
        try:
            async with semaphore:
                ref_url, effective_urls, effective_assets = _resolve_shot_reference_context(state, spec, prompt)
                target_aspect = get_spec_aspect_ratio(
                    spec,
                    prompt_set,
                    fallback=settings.default_aspect_ratio,
                    allowed=VEO_SUPPORTED_ASPECT_RATIOS,
                )
                submit_kwargs = {
                    "prompt_text": prompt.prompt_text,
                    "duration_seconds": prompt.duration_seconds,
                    "aspect_ratio": target_aspect,
                    "negative_prompt": prompt.negative_constraints,
                    "reference_image_url": ref_url,
                    "reference_image_urls": effective_urls,
                    "reference_assets": effective_assets,
                }
                ext_job_id = await _submit_with_backoff(
                    client,
                    job_id=job.job_id,
                    submit_kwargs=submit_kwargs,
                    min_interval=min_interval,
                    max_retries=max_submit_retries,
                    base_backoff=base_backoff,
                    max_backoff=max_backoff,
                )

                # Refresh submission timestamp so provider wait timer tracks actual
                # upstream acceptance time rather than local queue/backoff wait.
                repo.update_job_status(
                    job.job_id,
                    VideoJobStatus.SUBMITTED,
                    external_job_id=ext_job_id,
                    submitted_at=datetime.now(UTC),
                )
                logger.info(f"Submitted video job {job.job_id} -> {ext_job_id}")
        except Exception as exc:
            logger.error(f"Failed to submit video job {job.job_id}: {exc}")
            repo.update_job_status(
                job.job_id,
                VideoJobStatus.FAILED,
                error_message=str(exc),
                completed_at=datetime.now(UTC),
            )
            limiter.active_job_ids.discard(job.job_id)
            await _maybe_trigger_stitching_after_submit_failure(project_id)
        finally:
            limiter.active_job_ids.discard(job.job_id)

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
