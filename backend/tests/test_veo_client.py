import json
import logging
import pytest
import httpx

from app.services.video_generation.veo_client import VeoClient
from app.services.video_generation.base_client import PermanentVideoError, TransientVideoError

pytestmark = pytest.mark.asyncio

@pytest.fixture
def default_client_kwargs():
    return {
        "api_key": "test_secret_key_123",
        "base_url": "https://generativelanguage.googleapis.com/v1beta",
        "model": "veo-3.1-lite-generate-preview",
        "resolution": "720p",
        "person_generation": "",
        "negative_prompt_mode": "drop",
        "request_timeout": 5.0,
        "download_timeout": 10.0,
        "max_prompt_tokens": 1000,
    }


async def test_blank_key_raises():
    with pytest.raises(PermanentVideoError, match="GEMINI_API_KEY is not set"):
        VeoClient(
            api_key="",
            base_url="https://generativelanguage.googleapis.com/v1beta",
            model="veo-3.1-lite-generate-preview",
            resolution="720p",
            person_generation="",
            negative_prompt_mode="drop",
            request_timeout=5.0,
            download_timeout=10.0,
            max_prompt_tokens=1000,
        )


async def test_submit_success(default_client_kwargs):
    requests = []

    def handler(request: httpx.Request):
        requests.append(request)
        return httpx.Response(200, json={"name": "models/veo-3.1-lite-generate-preview/operations/op_12345"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as hc:
        client = VeoClient(**default_client_kwargs, client=hc)
        op_name = await client.submit_job(
            prompt_text="a golden retriever running on grass",
            duration_seconds=4.0,
            aspect_ratio="16:9",
        )
        assert op_name == "models/veo-3.1-lite-generate-preview/operations/op_12345"

    assert len(requests) == 1
    req = requests[0]
    assert ":predictLongRunning" in str(req.url)
    assert req.headers.get("x-goog-api-key") == "test_secret_key_123"
    
    body = json.loads(req.read().decode())
    assert body["instances"] == [{"prompt": "a golden retriever running on grass"}]
    assert body["parameters"]["aspectRatio"] == "16:9"
    assert body["parameters"]["durationSeconds"] == 4
    assert isinstance(body["parameters"]["durationSeconds"], int)
    assert body["parameters"]["resolution"] == "720p"
    assert "personGeneration" not in body["parameters"]


async def test_submit_missing_name_raises(default_client_kwargs):
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json={"other": "val"}))
    async with httpx.AsyncClient(transport=transport) as hc:
        client = VeoClient(**default_client_kwargs, client=hc)
        with pytest.raises(PermanentVideoError, match="Missing 'name' in response"):
            await client.submit_job("prompt", 4.0, "16:9")


async def test_duration_snapping_table(default_client_kwargs, caplog):
    requests = []

    def handler(request: httpx.Request):
        requests.append(request)
        return httpx.Response(200, json={"name": "op_test"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as hc:
        client = VeoClient(**default_client_kwargs, client=hc)
        
        # 720p durations:
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
            requests.clear()
            with caplog.at_level(logging.WARNING):
                await client.submit_job("prompt", planned, "16:9")
            body = json.loads(requests[0].read().decode())
            assert body["parameters"]["durationSeconds"] == expected

            if planned > 8:
                assert "shot is longer than Veo's 8 s maximum" in caplog.text

    # 1080p duration is always 8
    requests.clear()
    kwargs_1080p = {**default_client_kwargs, "resolution": "1080p"}
    async with httpx.AsyncClient(transport=transport) as hc:
        client_1080 = VeoClient(**kwargs_1080p, client=hc)
        await client_1080.submit_job("prompt", 2.0, "16:9")
        body = json.loads(requests[0].read().decode())
        assert body["parameters"]["durationSeconds"] == 8


async def test_aspect_ratio_mapping(default_client_kwargs, caplog):
    requests = []

    def handler(request: httpx.Request):
        requests.append(request)
        return httpx.Response(200, json={"name": "op_test"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as hc:
        client = VeoClient(**default_client_kwargs, client=hc)

        mapping_cases = [
            ("16:9", "16:9", False),
            ("9:16", "9:16", False),
            ("1:1", "16:9", True),
            ("4:3", "16:9", True),
            ("3:4", "9:16", True),
            ("garbage", "16:9", True),
        ]

        for input_aspect, expected_aspect, expect_warning in mapping_cases:
            requests.clear()
            caplog.clear()
            with caplog.at_level(logging.WARNING):
                await client.submit_job("prompt", 4.0, input_aspect)
            body = json.loads(requests[0].read().decode())
            assert body["parameters"]["aspectRatio"] == expected_aspect
            if expect_warning:
                assert "not supported by Veo, mapping to" in caplog.text


async def test_prompt_token_guard(default_client_kwargs):
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json={"name": "op_test"}))
    async with httpx.AsyncClient(transport=transport) as hc:
        # max_prompt_tokens = 100 -> ~400 characters max
        client = VeoClient(**{**default_client_kwargs, "max_prompt_tokens": 100}, client=hc)

        # Under limit: 200 chars (~50 tokens) -> succeeds
        await client.submit_job("a" * 200, 4.0, "16:9")

        # Over limit: 500 chars (~125 tokens) -> raises PermanentVideoError
        with pytest.raises(PermanentVideoError, match="Veo accepts at most 1,024. Shorten the prompt."):
            await client.submit_job("a" * 500, 4.0, "16:9")


async def test_negative_prompt_and_person_generation(default_client_kwargs):
    requests = []

    def handler(request: httpx.Request):
        requests.append(request)
        return httpx.Response(200, json={"name": "op_test"})

    transport = httpx.MockTransport(handler)

    # 1. Mode 'drop': negative prompt is dropped
    async with httpx.AsyncClient(transport=transport) as hc:
        client_drop = VeoClient(**{**default_client_kwargs, "negative_prompt_mode": "drop"}, client=hc)
        await client_drop.submit_job(
            "main prompt", 4.0, "16:9",
            negative_prompt="blurry, distorted",
            reference_image_url="https://example.com/img.png"
        )
        body = json.loads(requests[0].read().decode())
        assert body["instances"][0]["prompt"] == "main prompt"
        assert "negativePrompt" not in body["parameters"]
        assert "reference_image_url" not in body

    # 2. Mode 'append': negative prompt appended + personGeneration sent
    requests.clear()
    async with httpx.AsyncClient(transport=transport) as hc:
        client_append = VeoClient(
            **{**default_client_kwargs, "negative_prompt_mode": "append", "person_generation": "allow_all"},
            client=hc
        )
        await client_append.submit_job("main prompt", 4.0, "16:9", negative_prompt="blurry")
        body = json.loads(requests[0].read().decode())
        assert body["instances"][0]["prompt"] == "main prompt\n\nAvoid: blurry"
        assert body["parameters"]["personGeneration"] == "allow_all"


async def test_check_status_mappings(default_client_kwargs):
    responses = [
        # 1. Not done
        {"done": False},
        # 2. Done + URI
        {
            "done": True,
            "response": {
                "generateVideoResponse": {
                    "generatedSamples": [{"video": {"uri": "https://storage.googleapis.com/veo/video1.mp4"}}]
                }
            }
        },
        # 3. Done + Error
        {
            "done": True,
            "error": {"code": 400, "status": "INVALID_ARGUMENT", "message": "Invalid input"}
        },
        # 4. Done without sample + safety filtered
        {
            "done": True,
            "response": {
                "generateVideoResponse": {
                    "generatedSamples": [],
                    "raiMediaFilteredReasons": ["IMAGE_SAFETY"],
                    "raiMediaFilteredCount": 1,
                }
            }
        },
        # 5. Done without sample and nothing else
        {
            "done": True,
            "response": {"generateVideoResponse": {}}
        }
    ]

    req_idx = 0
    def handler(request: httpx.Request):
        nonlocal req_idx
        resp = responses[req_idx]
        req_idx += 1
        return httpx.Response(200, json=resp)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as hc:
        client = VeoClient(**default_client_kwargs, client=hc)

        # 1. PROCESSING
        r1 = await client.check_status("models/veo/operations/op1")
        assert r1["status"] == "PROCESSING"
        assert r1["video_url"] is None

        # 2. COMPLETED
        r2 = await client.check_status("models/veo/operations/op1")
        assert r2["status"] == "COMPLETED"
        assert r2["video_url"] == "https://storage.googleapis.com/veo/video1.mp4"

        # 3. FAILED with error
        r3 = await client.check_status("models/veo/operations/op1")
        assert r3["status"] == "FAILED"
        assert "400 INVALID_ARGUMENT: Invalid input" in r3["error"]

        # 4. FAILED safety blocked -> retryable False
        r4 = await client.check_status("models/veo/operations/op1")
        assert r4["status"] == "FAILED"
        assert "Video was blocked by Google's safety filters" in r4["error"]
        assert r4.get("retryable") is False

        # 5. FAILED empty -> retryable False
        r5 = await client.check_status("models/veo/operations/op1")
        assert r5["status"] == "FAILED"
        assert "Operation finished without a video" in r5["error"]
        assert r5.get("retryable") is False


async def test_check_status_operation_id_validation(default_client_kwargs):
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json={"done": False}))
    async with httpx.AsyncClient(transport=transport) as hc:
        client = VeoClient(**default_client_kwargs, client=hc)

        invalid_ids = [
            "",
            "/models/veo/operations/123",
            "models/../veo/operations/123",
            "models/veo/operations/123; rm -rf",
            "https://evil.com/models/veo",
        ]
        for bad_id in invalid_ids:
            with pytest.raises(PermanentVideoError, match="Invalid operation id"):
                await client.check_status(bad_id)


async def test_http_permanent_errors(default_client_kwargs):
    # 401 / 403 / 404 / 400
    for code in [401, 403, 400, 404]:
        calls = 0
        def handler(r):
            nonlocal calls
            calls += 1
            return httpx.Response(code, json={"error": {"message": f"error {code}"}})

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as hc:
            client = VeoClient(**default_client_kwargs, client=hc)
            with pytest.raises(PermanentVideoError):
                await client.submit_job("prompt", 4.0, "16:9")
            assert calls == 1


async def test_429_retry_on_post(default_client_kwargs):
    calls = 0
    def handler(r):
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, headers={"Retry-After": "0"})
        return httpx.Response(200, json={"name": "op_recovered"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as hc:
        client = VeoClient(**default_client_kwargs, client=hc)
        op_name = await client.submit_job("prompt", 4.0, "16:9")
        assert op_name == "op_recovered"
        assert calls == 2


async def test_post_500_and_timeout_no_retry(default_client_kwargs):
    # POST 500 should fail immediately as TransientVideoError (no double billing)
    calls = 0
    def handler_500(r):
        nonlocal calls
        calls += 1
        return httpx.Response(500, text="Internal Server Error")

    transport = httpx.MockTransport(handler_500)
    async with httpx.AsyncClient(transport=transport) as hc:
        client = VeoClient(**default_client_kwargs, client=hc)
        with pytest.raises(TransientVideoError):
            await client.submit_job("prompt", 4.0, "16:9")
        assert calls == 1

    # POST ReadTimeout should also NOT retry
    calls_timeout = 0
    def handler_timeout(r):
        nonlocal calls_timeout
        calls_timeout += 1
        raise httpx.ReadTimeout("timed out")

    transport_timeout = httpx.MockTransport(handler_timeout)
    async with httpx.AsyncClient(transport=transport_timeout) as hc:
        client = VeoClient(**default_client_kwargs, client=hc)
        with pytest.raises(TransientVideoError):
            await client.submit_job("prompt", 4.0, "16:9")
        assert calls_timeout == 1


async def test_get_timeout_retried(default_client_kwargs):
    # GET (idempotent) read timeout should retry
    calls = 0
    def handler(r):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.ReadTimeout("read error")
        return httpx.Response(200, json={"done": False})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as hc:
        client = VeoClient(**default_client_kwargs, client=hc)
        res = await client.check_status("models/veo/operations/op1")
        assert res["status"] == "PROCESSING"
        assert calls == 2


async def test_download_video_authenticated_redirects(default_client_kwargs):
    # Test:
    # 1. First hop https://generativelanguage.googleapis.com/... sends x-goog-api-key
    # 2. Redirect (302) to https://storage.googleapis.com/... sends x-goog-api-key
    # 3. Redirect (302) to https://signed-bucket.external-cdn.com/... does NOT send x-goog-api-key
    # 4. Successfully returns bytes
    video_content = b"fake_mp4_video_bytes_content"
    received_headers = []

    def handler(request: httpx.Request):
        received_headers.append((str(request.url), dict(request.headers)))
        if "generativelanguage.googleapis.com" in str(request.url):
            return httpx.Response(302, headers={"Location": "https://storage.googleapis.com/bucket/video.mp4"})
        elif "storage.googleapis.com" in str(request.url):
            return httpx.Response(302, headers={"Location": "https://signed-bucket.external-cdn.com/download"})
        elif "signed-bucket.external-cdn.com" in str(request.url):
            return httpx.Response(200, content=video_content, headers={"content-type": "video/mp4"})
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as hc:
        client = VeoClient(**default_client_kwargs, client=hc)
        data = await client.download_video("https://generativelanguage.googleapis.com/v1beta/files/12345:download")
        assert data == video_content

    assert len(received_headers) == 3
    # Hop 1: Google host -> has auth header
    assert received_headers[0][1].get("x-goog-api-key") == "test_secret_key_123"
    # Hop 2: Google host -> has auth header
    assert received_headers[1][1].get("x-goog-api-key") == "test_secret_key_123"
    # Hop 3: Non-Google host -> MUST NOT have auth header!
    assert "x-goog-api-key" not in received_headers[2][1]


async def test_download_video_safety_checks(default_client_kwargs):
    transport = httpx.MockTransport(lambda r: httpx.Response(200, content=b"data", headers={"content-type": "video/mp4"}))
    async with httpx.AsyncClient(transport=transport) as hc:
        client = VeoClient(**default_client_kwargs, client=hc)

        # Non-https
        with pytest.raises(PermanentVideoError, match="Refusing non-https"):
            await client.download_video("http://generativelanguage.googleapis.com/video.mp4")

        # Non-Google first host
        with pytest.raises(PermanentVideoError, match="Refusing to send API key to non-Google host"):
            await client.download_video("https://evil.com/video.mp4")

    # JSON/HTML body rejected
    def json_handler(r):
        return httpx.Response(200, content=b'{"error": "not found"}', headers={"content-type": "application/json"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(json_handler)) as hc:
        client = VeoClient(**default_client_kwargs, client=hc)
        with pytest.raises(PermanentVideoError, match="Expected video content-type"):
            await client.download_video("https://generativelanguage.googleapis.com/video.mp4")


async def test_api_key_not_leaked_in_logs_or_errors(default_client_kwargs, caplog):
    def error_handler(r):
        return httpx.Response(400, json={"error": {"message": "Invalid request"}})

    transport = httpx.MockTransport(error_handler)
    async with httpx.AsyncClient(transport=transport) as hc:
        client = VeoClient(**default_client_kwargs, client=hc)
        with caplog.at_level(logging.DEBUG):
            with pytest.raises(PermanentVideoError) as exc_info:
                await client.submit_job("prompt", 4.0, "16:9")

            # Check exception message
            assert "test_secret_key_123" not in str(exc_info.value)
            # Check logged text
            assert "test_secret_key_123" not in caplog.text
