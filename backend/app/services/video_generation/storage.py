"""Video storage — download from a temporary URL and upload to Cloudinary.

NOTE: This implementation downloads the full video into memory before uploading.
For very large files (multi-GB), a streaming approach would be preferred.  This
is a known limitation acceptable for this phase given typical AI-generated clip
sizes (a few MB each).
"""
import logging
from typing import Optional

import httpx

from app.services.cloudinary_service import upload_video

logger = logging.getLogger(__name__)


class VideoStorageError(Exception):
    """Raised when downloading or storing a video fails."""
    pass


async def store_video(
    temporary_url: str,
    project_id: str,
    shot_id: str,
) -> str:
    """Download video from ``temporary_url`` and persist to Cloudinary.

    Returns the permanent Cloudinary ``secure_url``.
    """
    logger.info(f"Downloading video for shot {shot_id} from: {temporary_url}")
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.get(temporary_url)
            resp.raise_for_status()
            video_bytes = resp.content
    except httpx.HTTPError as exc:
        raise VideoStorageError(
            f"Failed to download video from {temporary_url}: {exc}"
        ) from exc

    logger.info(
        f"Downloaded {len(video_bytes)} bytes for shot {shot_id}. "
        f"Uploading to Cloudinary..."
    )

    folder = f"video-agent/{project_id}"
    filename = f"shot-{shot_id}"
    try:
        permanent_url = upload_video(video_bytes, filename, folder)
    except Exception as exc:
        raise VideoStorageError(
            f"Failed to upload video to Cloudinary for shot {shot_id}: {exc}"
        ) from exc

    logger.info(f"Stored video for shot {shot_id}: {permanent_url}")
    return permanent_url
