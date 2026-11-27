import pytest
import httpx
from app.services.video_generation.storage import store_video, VideoStorageError

pytestmark = pytest.mark.asyncio


async def test_store_video_with_custom_downloader(monkeypatch):
    called_downloader = False
    fake_bytes = b"custom_downloader_video_bytes"

    async def mock_downloader(url: str) -> bytes:
        nonlocal called_downloader
        called_downloader = True
        assert url == "https://generativelanguage.googleapis.com/video1"
        return fake_bytes

    monkeypatch.setattr(
        "app.services.video_generation.storage.upload_video",
        lambda data, filename, folder: f"https://res.cloudinary.com/demo/video/{filename}.mp4"
    )

    url = await store_video(
        temporary_url="https://generativelanguage.googleapis.com/video1",
        project_id="p1",
        shot_id="s1",
        downloader=mock_downloader,
    )
    assert called_downloader is True
    assert "shot-s1" in url


async def test_store_video_downloader_exception_raises_storage_error():
    async def failing_downloader(url: str) -> bytes:
        raise RuntimeError("Network failed")

    with pytest.raises(VideoStorageError, match="Failed to download video"):
        await store_video(
            temporary_url="https://generativelanguage.googleapis.com/video1",
            project_id="p1",
            shot_id="s1",
            downloader=failing_downloader,
        )


async def test_store_video_without_downloader_regression(monkeypatch):
    # Without downloader: plain httpx path used
    fake_bytes = b"plain_httpx_bytes"

    def handler(request: httpx.Request):
        return httpx.Response(200, content=fake_bytes)

    # Mock httpx.AsyncClient to use MockTransport
    orig_client = httpx.AsyncClient

    def mock_client_factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return orig_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", mock_client_factory)
    monkeypatch.setattr(
        "app.services.video_generation.storage.upload_video",
        lambda data, filename, folder: f"https://res.cloudinary.com/demo/video/{filename}.mp4"
    )

    url = await store_video(
        temporary_url="https://example.com/video.mp4",
        project_id="p1",
        shot_id="s1",
    )
    assert "shot-s1" in url


async def test_cloudinary_upload_video_uses_chunked_for_large_and_local_fallback(monkeypatch, tmp_path):
    from app.core.config import settings
    from app.services import cloudinary_service

    monkeypatch.setattr(settings, "cloudinary_cloud_name", "real-cloud")
    monkeypatch.setattr(settings, "cloudinary_api_key", "key")
    monkeypatch.setattr(settings, "cloudinary_api_secret", "secret")
    monkeypatch.setattr(cloudinary_service, "LARGE_VIDEO_THRESHOLD_BYTES", 100)
    monkeypatch.setattr(cloudinary_service.time, "sleep", lambda _: None)

    calls = []

    def fake_upload(buf, **kwargs):
        calls.append(("upload", kwargs))
        return {"secure_url": "https://res.cloudinary.com/real-cloud/video/small.mp4"}

    def fake_upload_large(buf, **kwargs):
        calls.append(("upload_large", kwargs))
        return {"secure_url": "https://res.cloudinary.com/real-cloud/video/large.mp4"}

    monkeypatch.setattr(cloudinary_service.cloudinary.uploader, "upload", fake_upload)
    monkeypatch.setattr(cloudinary_service.cloudinary.uploader, "upload_large", fake_upload_large)

    # 1. Small payload uses upload
    url_small = cloudinary_service.upload_video(b"x" * 50, "small_vid", "video-agent/p1")
    assert url_small.endswith("small.mp4")
    assert calls[-1][0] == "upload"

    # 2. Large payload (> threshold) uses upload_large
    url_large = cloudinary_service.upload_video(b"x" * 200, "large_vid", "video-agent/p1")
    assert url_large.endswith("large.mp4")
    assert calls[-1][0] == "upload_large"
    assert calls[-1][1]["resource_type"] == "video"

    # 3. If Cloudinary fails after retries, falls back to local static/generated_videos (never ad.mp4)
    monkeypatch.chdir(tmp_path)
    def failing_upload_large(buf, **kwargs):
        raise RuntimeError("Cloudinary network timeout")

    monkeypatch.setattr(cloudinary_service.cloudinary.uploader, "upload_large", failing_upload_large)
    fallback_url = cloudinary_service.upload_video(b"mp4bytes" * 30, "final-proj1", "video-agent/proj1")
    assert "/static/generated_videos/final-proj1.mp4" in fallback_url
    assert (tmp_path / "static" / "generated_videos" / "final-proj1.mp4").exists()
