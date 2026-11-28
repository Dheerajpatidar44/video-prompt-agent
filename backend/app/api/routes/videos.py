from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import asyncio
import logging

from app.db import video_jobs_repository as repo
from app.db.database import get_db
from app.schemas.agent import AgentStatus
from app.schemas.video_job import ProjectVideoStatus, VideoJobStatus

logger = logging.getLogger(__name__)

router = APIRouter()

# In-process fallback guard for projects without a DB row (e.g. direct tests)
_starting_projects: set[str] = set()
_stitch_retry_tasks: set[asyncio.Task] = set()


class TriggerVideoResponse(BaseModel):
    project_id: str
    status: str
    message: str
    already_started: bool = False


def _get_project_row(project_id: str):
    """Fetch project row from projects table if it exists."""
    conn = get_db()
    try:
        return conn.execute(
            "SELECT id, status, final_video_url FROM projects WHERE id = ?",
            (project_id,),
        ).fetchone()
    finally:
        conn.close()


@router.get("/{project_id}/video-status", response_model=ProjectVideoStatus)
async def get_video_status(project_id: str):
    jobs = repo.get_jobs_for_project(project_id)

    if not jobs:
        row = _get_project_row(project_id)
        if not row:
            # Also check checkpoint in case project exists in memory without a DB row
            try:
                from app.api.routes.scripts import _get_state_values
                await _get_state_values(project_id)
            except HTTPException:
                raise HTTPException(
                    status_code=404,
                    detail="No video generation jobs found for this project.",
                )

        final_video_url = row["final_video_url"] if row else None
        # If the project already claimed GENERATING_VIDEOS, never downgrade to NOT_STARTED
        effective_status = (
            "IN_PROGRESS"
            if (row and row["status"] == AgentStatus.GENERATING_VIDEOS.value)
            else "NOT_STARTED"
        )
        return ProjectVideoStatus(
            project_id=project_id,
            total_shots=0,
            completed_shots=0,
            failed_shots=0,
            status=effective_status,
            final_video_url=final_video_url,
            jobs=[],
        )

    total_shots = len(jobs)
    completed_shots = sum(1 for j in jobs if j.status == VideoJobStatus.COMPLETED)
    failed_shots = sum(1 for j in jobs if j.status == VideoJobStatus.FAILED)

    row = _get_project_row(project_id)
    final_video_url = repo.get_project_final_video_url(project_id)
    first_job_error = next(
        (j.error_message for j in jobs if j.status == VideoJobStatus.FAILED and j.error_message),
        None,
    )
    error_message: str | None = first_job_error

    status = "IN_PROGRESS"
    if completed_shots + failed_shots == total_shots:
        if final_video_url:
            if failed_shots == 0:
                status = "COMPLETED"
                error_message = None
            else:
                status = "PARTIAL_FAILURE"
        elif completed_shots == 0:
            status = "FAILED"
            error_message = error_message or "All video generation shots failed."
        elif row and row["status"] == "FAILED":
            status = "FAILED"
            error_message = error_message or (
                "Video stitching failed. Completed shots are preserved — click Retry to re-stitch."
            )
        else:
            status = "IN_PROGRESS"

    return ProjectVideoStatus(
        project_id=project_id,
        total_shots=total_shots,
        completed_shots=completed_shots,
        failed_shots=failed_shots,
        status=status,
        final_video_url=final_video_url,
        error_message=error_message,
        jobs=jobs,
    )


@router.post("/{project_id}/generate-video", response_model=TriggerVideoResponse)
async def trigger_video_generation(project_id: str):
    """Explicitly trigger Phase 2 video generation (or retry failed shots/stitch) from saved Phase 1 state."""
    if project_id in _starting_projects:
        return TriggerVideoResponse(
            project_id=project_id,
            status=AgentStatus.GENERATING_VIDEOS.value,
            message="Video generation is already starting for this project.",
            already_started=True,
        )

    _starting_projects.add(project_id)
    claimed_db_lock = False
    previous_status = AgentStatus.PROMPTS_READY.value

    try:
        existing_final_url = repo.get_project_final_video_url(project_id)
        existing_jobs = repo.get_jobs_for_project(project_id)

        active_statuses = {
            VideoJobStatus.QUEUED,
            VideoJobStatus.SUBMITTED,
            VideoJobStatus.PROCESSING,
            VideoJobStatus.RETRYING,
        }
        if any(j.status in active_statuses for j in existing_jobs):
            return TriggerVideoResponse(
                project_id=project_id,
                status=AgentStatus.GENERATING_VIDEOS.value,
                message="Video generation has already been started for this project.",
                already_started=True,
            )

        failed_jobs = [j for j in existing_jobs if j.status == VideoJobStatus.FAILED]
        completed_jobs = [j for j in existing_jobs if j.status == VideoJobStatus.COMPLETED]

        if existing_final_url and not failed_jobs:
            return TriggerVideoResponse(
                project_id=project_id,
                status=AgentStatus.COMPLETED.value,
                message="Final video is already generated for this project.",
                already_started=True,
            )

        existing_row = _get_project_row(project_id)
        if existing_row and existing_row["status"]:
            previous_status = existing_row["status"]

        # Case 1: All shots completed, only stitching had failed -> re-stitch without re-billing Veo
        if existing_jobs and completed_jobs and not failed_jobs and not existing_final_url:
            claim_res = repo.try_claim_video_generation(project_id, allow_completed=True)
            if claim_res not in ("CLAIMED", None):
                return TriggerVideoResponse(
                    project_id=project_id,
                    status=claim_res,
                    message="Video generation has already been started for this project.",
                    already_started=True,
                )

            from app.services.video_generation.poller import _check_and_trigger_stitching
            task = asyncio.create_task(_check_and_trigger_stitching(project_id))
            _stitch_retry_tasks.add(task)
            task.add_done_callback(_stitch_retry_tasks.discard)

            return TriggerVideoResponse(
                project_id=project_id,
                status=AgentStatus.GENERATING_VIDEOS.value,
                message="Retrying final video stitching.",
                already_started=False,
            )

        has_failed_retry = bool(existing_jobs) and bool(failed_jobs)
        if existing_jobs and not has_failed_retry:
            return TriggerVideoResponse(
                project_id=project_id,
                status=AgentStatus.GENERATING_VIDEOS.value,
                message="Video generation has already been started for this project.",
                already_started=True,
            )

        from app.api.routes.scripts import _get_state_values, _update_state
        from app.graph.nodes.generate_videos import generate_videos

        state = await _get_state_values(project_id)
        prompt_set = state.get("prompt_set")
        spec = state.get("video_specification")
        if not prompt_set or not getattr(prompt_set, "prompts", None) or not spec:
            raise HTTPException(
                status_code=400,
                detail="Prompts or video specification are not ready yet for this project.",
            )

        # Atomic DB CAS lock prevents concurrent double-clicks even across workers
        claim_res = repo.try_claim_video_generation(
            project_id,
            allow_completed=has_failed_retry,
        )
        if claim_res == "CLAIMED":
            claimed_db_lock = True
        elif claim_res is not None:
            return TriggerVideoResponse(
                project_id=project_id,
                status=claim_res,
                message="Video generation has already been started for this project.",
                already_started=True,
            )

        target_shot_ids: set[str] | None = None
        old_failed_ids = [j.job_id for j in failed_jobs] if has_failed_retry else []
        if has_failed_retry and completed_jobs:
            target_shot_ids = {j.shot_id for j in failed_jobs}

        updated_state = await generate_videos(state, target_shot_ids=target_shot_ids)

        if updated_state.get("video_generation_status") == "BLOCKED_COST_GUARD":
            if claimed_db_lock:
                repo.update_project_status(project_id, previous_status)
            return TriggerVideoResponse(
                project_id=project_id,
                status="BLOCKED_COST_GUARD",
                message="Video generation blocked by project cost, shot count, or duration limits.",
                already_started=False,
            )

        if updated_state.get("status") == AgentStatus.ERROR:
            if claimed_db_lock:
                repo.update_project_status(project_id, previous_status)
            raise HTTPException(
                status_code=500,
                detail=updated_state.get("error") or "Failed to initiate video generation.",
            )

        if has_failed_retry:
            if existing_final_url:
                repo.clear_project_final_video_url(project_id)
            deleted = repo.delete_jobs_by_ids(old_failed_ids)
            logger.info(
                f"Retrying video generation for project {project_id}: cleared {deleted} prior failed jobs "
                f"(partial={bool(completed_jobs)})."
            )

        # Best-effort sync of LangGraph checkpointer; DB jobs are already created and active
        config = {"configurable": {"thread_id": project_id}}
        try:
            await _update_state(
                config,
                {
                    "status": AgentStatus.GENERATING_VIDEOS,
                    "video_generation_status": updated_state.get("video_generation_status", "IN_PROGRESS"),
                },
            )
        except Exception as exc:
            logger.warning(
                f"Video jobs created for {project_id}, but checkpoint status sync failed: {exc}"
            )

        return TriggerVideoResponse(
            project_id=project_id,
            status=AgentStatus.GENERATING_VIDEOS.value,
            message="Video generation started successfully.",
            already_started=False,
        )
    except HTTPException:
        raise
    except Exception:
        if claimed_db_lock and not repo.get_jobs_for_project(project_id):
            try:
                repo.update_project_status(project_id, previous_status)
            except Exception:
                pass
        raise
    finally:
        _starting_projects.discard(project_id)
