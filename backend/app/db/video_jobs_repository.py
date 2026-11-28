"""Repository for video_jobs table.

Uses synchronous sqlite3, matching the existing pattern in app/db/database.py.
All functions accept/return VideoJob Pydantic models.
"""
import logging
from typing import Optional, List
from datetime import datetime, UTC

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
                 retry_count, submitted_at, completed_at, duration_seconds)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job.job_id, job.project_id, job.prompt_id, job.shot_id,
                job.sequence_number, job.status.value, job.external_job_id,
                job.video_url, job.error_message, job.retry_count,
                job.submitted_at.isoformat() if job.submitted_at else None,
                job.completed_at.isoformat() if job.completed_at else None,
                job.duration_seconds,
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
    retry_count, submitted_at, completed_at, duration_seconds.
    """
    allowed = {
        "external_job_id", "video_url", "error_message",
        "retry_count", "submitted_at", "completed_at", "duration_seconds",
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
            "UPDATE projects SET final_video_url = ?, status = 'COMPLETED', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (url, project_id),
        )
        conn.commit()
    except Exception:
        logger.exception(f"Failed to set final_video_url for project {project_id}")
        raise
    finally:
        conn.close()


def update_project_status(project_id: str, status: str) -> None:
    """Update project status cleanly in the projects table."""
    conn = get_db()
    try:
        conn.execute(
            "UPDATE projects SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (status, project_id),
        )
        conn.commit()
    except Exception:
        logger.exception(f"Failed to update status={status} for project {project_id}")
        raise
    finally:
        conn.close()


def try_claim_video_generation(project_id: str, allow_completed: bool = False) -> Optional[str]:
    """Atomically claim video generation lock in SQLite across workers.

    Returns:
      - 'CLAIMED' if this caller transitioned the project into GENERATING_VIDEOS.
      - Existing status string if the project is already GENERATING_VIDEOS (or COMPLETED
        unless ``allow_completed=True`` for retrying failed shots).
      - None if no row exists in the projects table.
    """
    conn = get_db()
    try:
        blocked = "('GENERATING_VIDEOS')" if allow_completed else "('GENERATING_VIDEOS', 'COMPLETED')"
        cur = conn.execute(
            f"""
            UPDATE projects
            SET status = 'GENERATING_VIDEOS', updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND status NOT IN {blocked}
            """,
            (project_id,),
        )
        conn.commit()
        if cur.rowcount == 1:
            return "CLAIMED"
        row = conn.execute(
            "SELECT status FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
        return row["status"] if row else None
    finally:
        conn.close()


def delete_failed_jobs_for_project(project_id: str) -> int:
    """Delete terminal FAILED video jobs for a project so a clean retry can start."""
    conn = get_db()
    try:
        cur = conn.execute(
            "DELETE FROM video_jobs WHERE project_id = ? AND status = ?",
            (project_id, VideoJobStatus.FAILED.value),
        )
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


def delete_jobs_by_ids(job_ids: list[str]) -> int:
    """Delete specific video_jobs rows by ID (e.g. superseded FAILED jobs on retry)."""
    if not job_ids:
        return 0
    placeholders = ",".join("?" for _ in job_ids)
    conn = get_db()
    try:
        cur = conn.execute(
            f"DELETE FROM video_jobs WHERE job_id IN ({placeholders})",
            tuple(job_ids),
        )
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


def clear_project_final_video_url(project_id: str) -> None:
    """Clear final_video_url so a project can be re-stitched after retrying failed shots."""
    conn = get_db()
    try:
        conn.execute(
            "UPDATE projects SET final_video_url = NULL, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (project_id,),
        )
        conn.commit()
    finally:
        conn.close()


def delete_jobs_for_project(project_id: str) -> int:
    """Delete all video jobs associated with a project."""
    conn = get_db()
    try:
        cur = conn.execute(
            "DELETE FROM video_jobs WHERE project_id = ?",
            (project_id,),
        )
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


def fail_orphaned_queued_jobs(
    error_message: str = "Interrupted before provider submission (server restarted). Click Retry to resume.",
) -> int:
    """Mark unsubmitted QUEUED/RETRYING jobs from prior server runs as FAILED.

    Run once on startup before background polling begins so interrupted projects
    surface a clean retryable state instead of hanging indefinitely in QUEUED.
    """
    now_iso = datetime.now(UTC).isoformat()
    conn = get_db()
    try:
        rows = conn.execute(
            """
            SELECT job_id, project_id
            FROM video_jobs
            WHERE status IN (?, ?)
              AND (external_job_id IS NULL OR external_job_id = '')
            """,
            (VideoJobStatus.QUEUED.value, VideoJobStatus.RETRYING.value),
        ).fetchall()

        if not rows:
            return 0

        affected_projects = {r["project_id"] for r in rows}
        cur = conn.execute(
            """
            UPDATE video_jobs
            SET status = ?, error_message = ?, completed_at = ?
            WHERE status IN (?, ?)
              AND (external_job_id IS NULL OR external_job_id = '')
            """,
            (
                VideoJobStatus.FAILED.value,
                error_message,
                now_iso,
                VideoJobStatus.QUEUED.value,
                VideoJobStatus.RETRYING.value,
            ),
        )

        # If an affected project now has zero remaining non-terminal jobs and no
        # final stitched video, move it out of GENERATING_VIDEOS into FAILED.
        for pid in affected_projects:
            remaining = conn.execute(
                """
                SELECT COUNT(*) AS cnt
                FROM video_jobs
                WHERE project_id = ? AND status IN (?, ?, ?, ?)
                """,
                (
                    pid,
                    VideoJobStatus.QUEUED.value,
                    VideoJobStatus.SUBMITTED.value,
                    VideoJobStatus.PROCESSING.value,
                    VideoJobStatus.RETRYING.value,
                ),
            ).fetchone()["cnt"]
            if remaining == 0:
                conn.execute(
                    """
                    UPDATE projects
                    SET status = 'FAILED', updated_at = CURRENT_TIMESTAMP
                    WHERE id = ? AND status = 'GENERATING_VIDEOS' AND final_video_url IS NULL
                    """,
                    (pid,),
                )

        conn.commit()
        return cur.rowcount
    finally:
        conn.close()
