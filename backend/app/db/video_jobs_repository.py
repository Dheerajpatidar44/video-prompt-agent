"""Repository for video_jobs table.

Uses synchronous sqlite3, matching the existing pattern in app/db/database.py.
All functions accept/return VideoJob Pydantic models.
"""
import logging
from typing import Optional, List
from datetime import datetime

from app.db.database import get_db
from app.schemas.video_job import VideoJob, VideoJobStatus

logger = logging.getLogger(__name__)


def create_job(job: VideoJob) -> None:
    """Insert a new VideoJob row."""
    conn = get_db()
    try:
        conn.execute(
            """
            INSERT INTO video_jobs
                (job_id, project_id, prompt_id, shot_id, sequence_number,
                 status, external_job_id, video_url, error_message,
                 retry_count, submitted_at, completed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job.job_id, job.project_id, job.prompt_id, job.shot_id,
                job.sequence_number, job.status.value, job.external_job_id,
                job.video_url, job.error_message, job.retry_count,
                job.submitted_at.isoformat() if job.submitted_at else None,
                job.completed_at.isoformat() if job.completed_at else None,
            ),
        )
        conn.commit()
    except Exception:
        logger.exception(f"Failed to create video job {job.job_id}")
        raise
    finally:
        conn.close()


def update_job_status(job_id: str, status: VideoJobStatus, **fields) -> None:
    """Update a job's status and any additional fields.

    Accepted keyword fields: external_job_id, video_url, error_message,
    retry_count, submitted_at, completed_at.
    """
    allowed = {
        "external_job_id", "video_url", "error_message",
        "retry_count", "submitted_at", "completed_at",
    }
    sets = ["status = ?"]
    params: list = [status.value]

    for key, val in fields.items():
        if key not in allowed:
            continue
        if isinstance(val, datetime):
            val = val.isoformat()
        sets.append(f"{key} = ?")
        params.append(val)

    params.append(job_id)
    sql = f"UPDATE video_jobs SET {', '.join(sets)} WHERE job_id = ?"

    conn = get_db()
    try:
        conn.execute(sql, params)
        conn.commit()
    except Exception:
        logger.exception(f"Failed to update video job {job_id}")
        raise
    finally:
        conn.close()


def _row_to_job(row) -> VideoJob:
    """Convert a sqlite3.Row to a VideoJob model."""
    d = dict(row)
    d["status"] = VideoJobStatus(d["status"])
    for dt_field in ("submitted_at", "completed_at"):
        if d.get(dt_field):
            d[dt_field] = datetime.fromisoformat(d[dt_field])
    return VideoJob(**d)


def get_job(job_id: str) -> Optional[VideoJob]:
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT * FROM video_jobs WHERE job_id = ?", (job_id,)
        ).fetchone()
        return _row_to_job(row) if row else None
    finally:
        conn.close()


def get_jobs_for_project(project_id: str) -> List[VideoJob]:
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT * FROM video_jobs WHERE project_id = ? ORDER BY sequence_number",
            (project_id,),
        ).fetchall()
        return [_row_to_job(r) for r in rows]
    finally:
        conn.close()


def get_incomplete_jobs() -> List[VideoJob]:
    """Return jobs in non-terminal states (for poller recovery on startup).

    A SUBMITTED or PROCESSING job from a previous server run is assumed still
    valid and pollable.  A fully robust 'resume after crash' story (e.g.
    distinguishing a truly lost job from one still processing on the provider's
    side) is out of scope for this phase but these rows are NOT ignored.
    """
    conn = get_db()
    try:
        rows = conn.execute(
            """SELECT * FROM video_jobs
               WHERE status IN (?, ?, ?, ?)
               ORDER BY sequence_number""",
            (
                VideoJobStatus.QUEUED.value,
                VideoJobStatus.SUBMITTED.value,
                VideoJobStatus.PROCESSING.value,
                VideoJobStatus.RETRYING.value,
            ),
        ).fetchall()
        return [_row_to_job(r) for r in rows]
    finally:
        conn.close()


def get_project_final_video_url(project_id: str) -> Optional[str]:
    """Read the final_video_url from the projects table, if set."""
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT final_video_url FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
        return row["final_video_url"] if row else None
    except Exception:
        # Column may not exist yet on older DBs; degrade gracefully.
        return None
    finally:
        conn.close()


def set_project_final_video_url(project_id: str, url: str) -> None:
    """Store the stitched final video URL on the project row."""
    conn = get_db()
    try:
        conn.execute(
            "UPDATE projects SET final_video_url = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (url, project_id),
        )
        conn.commit()
    except Exception:
        logger.exception(f"Failed to set final_video_url for project {project_id}")
        raise
    finally:
        conn.close()
