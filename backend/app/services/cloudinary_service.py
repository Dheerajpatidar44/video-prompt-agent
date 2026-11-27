import io
import logging
import os
import time
import cloudinary
import cloudinary.uploader
from app.core.config import settings

logger = logging.getLogger(__name__)

# Cloudinary single-request upload limit is typically ~100MB; use chunked upload
# above 20MB so 2-minute 1080p MP4 files upload reliably without timeouts.
LARGE_VIDEO_THRESHOLD_BYTES = 20 * 1024 * 1024
UPLOAD_CHUNK_SIZE_BYTES = 6 * 1024 * 1024


def configure_cloudinary():
    if settings.cloudinary_cloud_name != "default":
        cloudinary.config(
            cloud_name=settings.cloudinary_cloud_name,
            api_key=settings.cloudinary_api_key,
            api_secret=settings.cloudinary_api_secret,
            secure=True,
        )


def upload_image(file_bytes: bytes, filename: str, folder: str = "video-agent") -> str:
    """Upload image to Cloudinary, return secure URL. Mock for development if defaults are set."""
    if settings.cloudinary_cloud_name == "default":
        return f"https://mock-image-url.com/{folder}/{filename}"

    configure_cloudinary()
    try:
        result = cloudinary.uploader.upload(
            io.BytesIO(file_bytes),
            folder=folder,
            public_id=filename.split(".")[0] if "." in filename else filename,
            resource_type="image",
            overwrite=True,
        )
        return result["secure_url"]
    except Exception as e:
        logger.warning(f"Cloudinary image upload error: {e}")
        return f"https://mock-image-url.com/{folder}/{filename}-fallback"


def _save_local_video_fallback(file_bytes: bytes, public_id: str) -> str:
    """Persist video locally under static/generated_videos/ if Cloudinary fails in production."""
    os.makedirs(os.path.join("static", "generated_videos"), exist_ok=True)
    safe_name = f"{public_id}.mp4"
    local_path = os.path.join("static", "generated_videos", safe_name)
    with open(local_path, "wb") as f:
        f.write(file_bytes)
    url = f"http://{settings.app_host}:{settings.app_port}/static/generated_videos/{safe_name}"
    logger.warning(f"Saved video locally as fallback after Cloudinary error: {url}")
    return url


def upload_video(file_bytes: bytes, filename: str, folder: str = "video-agent") -> str:
    """Upload video to Cloudinary (chunked for >20MB), with retry & local static fallback."""
    if settings.cloudinary_cloud_name == "default":
        return "http://127.0.0.1:3000/ad.mp4"

    configure_cloudinary()
    public_id = filename.split(".")[0] if "." in filename else filename
    size_bytes = len(file_bytes)
    use_chunked = size_bytes > LARGE_VIDEO_THRESHOLD_BYTES

    last_exc: Exception | None = None
    for attempt in range(1, 3):
        try:
            buf = io.BytesIO(file_bytes)
            if use_chunked:
                logger.info(
                    f"Uploading large video ({size_bytes / (1024 * 1024):.1f} MB) via chunked upload_large (attempt {attempt}/2)..."
                )
                result = cloudinary.uploader.upload_large(
                    buf,
                    filename=f"{public_id}.mp4",
                    folder=folder,
                    public_id=public_id,
                    resource_type="video",
                    overwrite=True,
                    chunk_size=UPLOAD_CHUNK_SIZE_BYTES,
                    timeout=300,
                )
            else:
                result = cloudinary.uploader.upload(
                    buf,
                    folder=folder,
                    public_id=public_id,
                    resource_type="video",
                    overwrite=True,
                    timeout=180,
                )
            secure_url = result["secure_url"]
            logger.info(f"Uploaded video to Cloudinary: {secure_url}")
            return secure_url
        except Exception as exc:
            last_exc = exc
            logger.warning(f"Cloudinary video upload attempt {attempt}/2 failed: {exc}")
            if attempt < 2:
                time.sleep(2.0)

    logger.error(f"Cloudinary video upload failed after retries ({last_exc}). Using local static fallback.")
    return _save_local_video_fallback(file_bytes, public_id)
