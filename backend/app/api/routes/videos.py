from fastapi import APIRouter, HTTPException
import logging

from app.db import video_jobs_repository as repo
from app.schemas.video_job import ProjectVideoStatus, VideoJobStatus

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/{project_id}/video-status", response_model=ProjectVideoStatus)
async def get_video_status(project_id: str):
    jobs = repo.get_jobs_for_project(project_id)
    
    if not jobs:
        # Check if project exists or not? For now just return 404.
        raise HTTPException(status_code=404, detail="No video generation jobs found for this project.")

    total_shots = len(jobs)
    completed_shots = sum(1 for j in jobs if j.status == VideoJobStatus.COMPLETED)
    failed_shots = sum(1 for j in jobs if j.status == VideoJobStatus.FAILED)

    final_video_url = repo.get_project_final_video_url(project_id)

    status = "IN_PROGRESS"
    if completed_shots + failed_shots == total_shots:
        if failed_shots == 0:
            status = "COMPLETED"
        else:
            status = "PARTIAL_FAILURE"

    return ProjectVideoStatus(
        project_id=project_id,
        total_shots=total_shots,
        completed_shots=completed_shots,
        failed_shots=failed_shots,
        status=status,
        final_video_url=final_video_url,
        jobs=jobs,
    )
