import logging
import pytest
from unittest.mock import MagicMock, AsyncMock

from app.services.video_generation.veo_client import VeoClient
from app.services.video_generation.base_client import PermanentVideoError, TransientVideoError

pytestmark = pytest.mark.asyncio


@pytest.fixture
def default_client_kwargs():
    return {
        "api_key": "test_secret_key_123",
        "model": "veo-3.1-lite-generate-001",
        "resolution": "720p",
        "person_generation": "",
        "negative_prompt_mode": "drop",
        "max_prompt_tokens": 1000,
        "project": "test-project",
        "location": "us-central1",
    }


def _make_mock_genai_client():
    mock = MagicMock()
    # Ensure neither aio nor operations raises unexpected AttributeError
    mock.models = MagicMock()
    mock.operations = MagicMock()
    mock.aio = None
    return mock


async def test_blank_key_raises():
    with pytest.raises(PermanentVideoError, match="GOOGLE_API_KEY is not set"):
        VeoClient(
            api_key="",
            model="veo-3.1-lite-generate-001",
            resolution="720p",
            person_generation="",
            negative_prompt_mode="drop",
            max_prompt_tokens=1000,
        )


async def test_submit_success(default_client_kwargs):
    mock_genai = _make_mock_genai_client()
    mock_op = MagicMock()
    mock_op.name = "models/veo-3.1-lite-generate-001/operations/op_12345"
    mock_genai.models.generate_videos.return_value = mock_op

    client = VeoClient(**default_client_kwargs, client=mock_genai)
    op_name = await client.submit_job(
        prompt_text="a golden retriever running on grass",
        duration_seconds=4.0,
        aspect_ratio="16:9",
    )
    assert op_name == "models/veo-3.1-lite-generate-001/operations/op_12345"
    mock_genai.models.generate_videos.assert_called_once()
    kwargs = mock_genai.models.generate_videos.call_args[1]
    assert kwargs["model"] == "veo-3.1-lite-generate-001"
    assert kwargs["prompt"] == "a golden retriever running on grass"
    cfg = kwargs["config"]
    assert cfg.duration_seconds == 4
    assert cfg.aspect_ratio == "16:9"
    assert cfg.resolution == "720p"


async def test_submit_with_reference_image(default_client_kwargs, monkeypatch):
    from unittest.mock import AsyncMock
    from google.genai import types

    mock_genai = _make_mock_genai_client()
    mock_op = MagicMock()
    mock_op.name = "models/veo-3.1-lite-generate-001/operations/op_img_test"
    mock_genai.models.generate_videos.return_value = mock_op

    client = VeoClient(**default_client_kwargs, client=mock_genai)
    dummy_img = types.Image(image_bytes=b"dummy_bytes", mime_type="image/jpeg")
    monkeypatch.setattr(client, "_load_reference_image", AsyncMock(return_value=dummy_img))

    op_name = await client.submit_job(
        prompt_text="a golden retriever running on grass",
        duration_seconds=4.0,
        aspect_ratio="16:9",
        reference_image_url="https://res.cloudinary.com/dummy/image.jpg",
    )
    assert op_name == "models/veo-3.1-lite-generate-001/operations/op_img_test"
    kwargs = mock_genai.models.generate_videos.call_args[1]
    assert "image" in kwargs
    assert kwargs["image"] == dummy_img


async def test_submit_with_reference_image_fallback_to_text(default_client_kwargs, monkeypatch):
    from unittest.mock import AsyncMock
    from google.genai import types

    mock_genai = _make_mock_genai_client()
    mock_op = MagicMock()
    mock_op.name = "models/veo-3.1-lite-generate-001/operations/op_fallback"
    
    # First call with image fails, second call without image succeeds
    mock_genai.models.generate_videos.side_effect = [
        Exception("Model does not support image input"),
        mock_op,
    ]

    client = VeoClient(**default_client_kwargs, client=mock_genai)
    dummy_img = types.Image(image_bytes=b"dummy_bytes", mime_type="image/jpeg")
    monkeypatch.setattr(client, "_load_reference_image", AsyncMock(return_value=dummy_img))

    op_name = await client.submit_job(
        prompt_text="a golden retriever running on grass",
        duration_seconds=4.0,
        aspect_ratio="16:9",
        reference_image_url="https://res.cloudinary.com/dummy/image.jpg",
    )
    assert op_name == "models/veo-3.1-lite-generate-001/operations/op_fallback"
    assert mock_genai.models.generate_videos.call_count == 2


async def test_submit_missing_name_raises(default_client_kwargs):
    mock_genai = _make_mock_genai_client()
    mock_op = MagicMock()
    mock_op.name = None
    mock_genai.models.generate_videos.return_value = mock_op

    client = VeoClient(**default_client_kwargs, client=mock_genai)
    with pytest.raises(PermanentVideoError, match="Missing 'name' in response"):
        await client.submit_job("prompt", 4.0, "16:9")


async def test_duration_snapping_table(default_client_kwargs, caplog):
    mock_genai = _make_mock_genai_client()
    mock_op = MagicMock()
    mock_op.name = "op_test"
    mock_genai.models.generate_videos.return_value = mock_op

    client = VeoClient(**default_client_kwargs, client=mock_genai)

    cases = [
        (1.0, 4),
        (2.0, 4),
        (3.0, 4),
        (4.0, 4),
        (4.2, 6),
        (5.0, 6),
        (6.0, 6),
        (6.0000000001, 6),
        (6.01, 8),
        (7.0, 8),
        (8.0, 8),
        (9.0, 8),
    ]
    for planned, expected in cases:
        mock_genai.models.generate_videos.reset_mock()
        with caplog.at_level(logging.WARNING):
            await client.submit_job("prompt", planned, "16:9")
        cfg = mock_genai.models.generate_videos.call_args[1]["config"]
        assert cfg.duration_seconds == expected
        if planned > 8:
            assert "shot is longer than Veo's 8 s maximum" in caplog.text


async def test_aspect_ratio_mapping(default_client_kwargs):
    mock_genai = _make_mock_genai_client()
    mock_op = MagicMock()
    mock_op.name = "op_test"
    mock_genai.models.generate_videos.return_value = mock_op

    client = VeoClient(**default_client_kwargs, client=mock_genai)

    mapping_cases = [
        ("16:9", "16:9"),
        ("9:16", "9:16"),
        ("1:1", "1:1"),
        ("garbage", "16:9"),
    ]
    for in_aspect, expected in mapping_cases:
        mock_genai.models.generate_videos.reset_mock()
        await client.submit_job("prompt", 4.0, in_aspect)
        cfg = mock_genai.models.generate_videos.call_args[1]["config"]
        assert cfg.aspect_ratio == expected


async def test_prompt_token_guard(default_client_kwargs):
    mock_genai = _make_mock_genai_client()
    mock_op = MagicMock()
    mock_op.name = "op_test"
    mock_genai.models.generate_videos.return_value = mock_op

    client = VeoClient(**{**default_client_kwargs, "max_prompt_tokens": 100}, client=mock_genai)

    # Under limit: 200 chars (~50 tokens) -> succeeds
    await client.submit_job("a" * 200, 4.0, "16:9")

    # Over limit: 500 chars (~125 tokens) -> raises PermanentVideoError
    with pytest.raises(PermanentVideoError, match="Veo accepts at most 1,024. Shorten the prompt."):
        await client.submit_job("a" * 500, 4.0, "16:9")


async def test_negative_prompt_and_person_generation(default_client_kwargs):
    mock_genai = _make_mock_genai_client()
    mock_op = MagicMock()
    mock_op.name = "op_test"
    mock_genai.models.generate_videos.return_value = mock_op

    # 1. Mode 'drop': negative prompt is dropped
    client_drop = VeoClient(**{**default_client_kwargs, "negative_prompt_mode": "drop"}, client=mock_genai)
    await client_drop.submit_job("main prompt", 4.0, "16:9", negative_prompt="blurry")
    cfg = mock_genai.models.generate_videos.call_args[1]["config"]
    assert cfg.negative_prompt is None

    # 2. Mode 'append': negative prompt sent
    client_append = VeoClient(
        **{**default_client_kwargs, "negative_prompt_mode": "append", "person_generation": "allow_all"},
        client=mock_genai,
    )
    await client_append.submit_job("main prompt", 4.0, "16:9", negative_prompt="blurry")
    cfg2 = mock_genai.models.generate_videos.call_args[1]["config"]
    assert cfg2.negative_prompt == "blurry"
    assert cfg2.person_generation == "allow_all"


async def test_check_status_mappings(default_client_kwargs):
    mock_genai = _make_mock_genai_client()
    client = VeoClient(**default_client_kwargs, client=mock_genai)

    # 1. PROCESSING
    op_proc = MagicMock()
    op_proc.done = False
    mock_genai.operations.get.return_value = op_proc
    r1 = await client.check_status("op1")
    assert r1["status"] == "PROCESSING"

    # 2. COMPLETED with video bytes
    op_comp = MagicMock()
    op_comp.done = True
    op_comp.error = None
    mock_vid = MagicMock()
    mock_vid.video.video_bytes = b"fake_bytes"
    mock_vid.video.uri = None
    op_comp.response.generated_videos = [mock_vid]
    mock_genai.operations.get.return_value = op_comp
    r2 = await client.check_status("op2")
    assert r2["status"] == "COMPLETED"
    assert r2["video_url"] == "op2"

    # 3. FAILED with error
    op_err = MagicMock()
    op_comp.done = True
    op_err.error = "400 INVALID_ARGUMENT: Invalid input"
    mock_genai.operations.get.return_value = op_err
    r3 = await client.check_status("op3")
    assert r3["status"] == "FAILED"
    assert "Invalid input" in r3["error"]

    # 4. FAILED without video (safety filter)
    op_safe = MagicMock()
    op_safe.done = True
    op_safe.error = None
    op_safe.response.generated_videos = []
    mock_genai.operations.get.return_value = op_safe
    r4 = await client.check_status("op4")
    assert r4["status"] == "FAILED"
    assert "blocked by safety filters" in r4["error"]
    assert r4.get("retryable") is False


async def test_check_status_operation_id_validation(default_client_kwargs):
    mock_genai = _make_mock_genai_client()
    client = VeoClient(**default_client_kwargs, client=mock_genai)
    with pytest.raises(PermanentVideoError, match="Invalid operation id"):
        await client.check_status("")


async def test_http_permanent_errors(default_client_kwargs):
    mock_genai = _make_mock_genai_client()
    mock_genai.models.generate_videos.side_effect = Exception("403 PERMISSION_DENIED: User not allowed")
    client = VeoClient(**default_client_kwargs, client=mock_genai)
    with pytest.raises(PermanentVideoError, match="Authentication/permission error"):
        await client.submit_job("prompt", 4.0, "16:9")


async def test_429_rate_limit(default_client_kwargs):
    mock_genai = _make_mock_genai_client()
    mock_genai.models.generate_videos.side_effect = Exception("429 RESOURCE_EXHAUSTED: Rate limited")
    client = VeoClient(**default_client_kwargs, client=mock_genai)
    with pytest.raises(TransientVideoError, match="Rate limited"):
        await client.submit_job("prompt", 4.0, "16:9")


async def test_download_video_cached_and_fallback(default_client_kwargs):
    mock_genai = _make_mock_genai_client()
    client = VeoClient(**default_client_kwargs, client=mock_genai)

    # Pre-cached bytes
    client._video_cache["op_cached"] = b"cached_mp4_bytes"
    data = await client.download_video("op_cached")
    assert data == b"cached_mp4_bytes"

    # Fallback to operation fetch
    op_fetch = MagicMock()
    mock_vid = MagicMock()
    mock_vid.video.video_bytes = b"fetched_bytes"
    op_fetch.response.generated_videos = [mock_vid]
    mock_genai.operations.get.return_value = op_fetch
    data2 = await client.download_video("op_fetch")
    assert data2 == b"fetched_bytes"


async def test_api_key_not_leaked_in_logs_or_errors(default_client_kwargs, caplog):
    mock_genai = _make_mock_genai_client()
    mock_genai.models.generate_videos.side_effect = Exception("403 PERMISSION_DENIED: Bad request")
    client = VeoClient(**default_client_kwargs, client=mock_genai)
    with caplog.at_level(logging.DEBUG):
        with pytest.raises(PermanentVideoError) as exc_info:
            await client.submit_job("prompt", 4.0, "16:9")
        assert "test_secret_key_123" not in str(exc_info.value)
        assert "test_secret_key_123" not in caplog.text
