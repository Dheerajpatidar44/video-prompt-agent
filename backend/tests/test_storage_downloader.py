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
