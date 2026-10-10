import pytest
import httpx
import logging
from app.services.video_generation.wavespeed_client import WaveSpeedClient
from app.services.video_generation.base_client import PermanentVideoError, TransientVideoError

pytestmark = pytest.mark.asyncio

@pytest.fixture
def client_kwargs():
    return {
        "api_key": "test_key",
        "base_url": "http://test",
        "model_path": "test/model",
        "resolution": "480p",
        "generate_audio": True,
        "enable_prompt_expansion": False,
        "negative_prompt_mode": "drop",
        "request_timeout": 5.0,
    }

async def test_submit_success_wrapped(client_kwargs):
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json={"data": {"id": "job123"}}))
    async with httpx.AsyncClient(transport=transport) as hc:
        client = WaveSpeedClient(**client_kwargs, client=hc)
        job_id = await client.submit_job("prompt", 2.0, "16:9")
        assert job_id == "job123"

async def test_submit_success_unwrapped(client_kwargs):
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json={"id": "job123"}))
    async with httpx.AsyncClient(transport=transport) as hc:
        client = WaveSpeedClient(**client_kwargs, client=hc)
        job_id = await client.submit_job("prompt", 2.0, "16:9")
        assert job_id == "job123"

async def test_submit_body_processing(client_kwargs, monkeypatch):
    requests = []
    async def handler(r):
        requests.append(r)
        return httpx.Response(200, json={"id": "job"})
    
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as hc:
        client = WaveSpeedClient(**{**client_kwargs, "negative_prompt_mode": "append"}, client=hc)
        await client.submit_job("prompt", 2.4, "unknown", negative_prompt="bad thing", reference_image_url="http://img")
        
        req = requests[0]
        body = req.read().decode()
        import json
        data = json.loads(body)
        
        assert data["duration"] == 3
        assert data["aspect_ratio"] == "16:9"
        assert "Avoid: bad thing" in data["prompt"]
        assert "reference_image_url" not in data

async def test_check_status_mappings(client_kwargs):
    responses = [
        {"data": {"status": "processing"}},
        {"data": {"status": "completed", "outputs": ["http://vid"]}},
        {"data": {"status": "failed", "error": "broken"}},
        {"data": {"status": "completed", "outputs": []}},
    ]
    
    req_idx = 0
    def handler(r):
        nonlocal req_idx
        resp = responses[req_idx]
        req_idx += 1
        return httpx.Response(200, json=resp)
        
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as hc:
        client = WaveSpeedClient(**client_kwargs, client=hc)
        assert (await client.check_status("id"))["status"] == "PROCESSING"
        
        res = await client.check_status("id")
        assert res["status"] == "COMPLETED"
        assert res["video_url"] == "http://vid"
        
        res = await client.check_status("id")
        assert res["status"] == "FAILED"
        assert res["error"] == "broken"
        
        res = await client.check_status("id")
        assert res["status"] == "COMPLETED"
        assert res["video_url"] is None

async def test_api_key_not_leaked(caplog, client_kwargs):
    transport = httpx.MockTransport(lambda r: httpx.Response(400, json={"error": "bad"}))
    async with httpx.AsyncClient(transport=transport) as hc:
        client = WaveSpeedClient(**client_kwargs, client=hc)
        with pytest.raises(PermanentVideoError):
            await client.submit_job("prompt", 2, "16:9")
        assert "test_key" not in caplog.text

async def test_http_404(client_kwargs):
    transport = httpx.MockTransport(lambda r: httpx.Response(404, json={}))
    async with httpx.AsyncClient(transport=transport) as hc:
        client = WaveSpeedClient(**client_kwargs, client=hc)
        with pytest.raises(PermanentVideoError) as exc:
            await client.check_status("id")
        assert "Unknown job id" in str(exc.value)

async def test_http_401(client_kwargs):
    calls = 0
    def handler(r):
        nonlocal calls
        calls += 1
        return httpx.Response(401, json={})
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as hc:
        client = WaveSpeedClient(**client_kwargs, client=hc)
        with pytest.raises(PermanentVideoError):
            await client.submit_job("prompt", 2, "16:9")
        assert calls == 1

async def test_429_retry(client_kwargs):
    calls = 0
    def handler(r):
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, headers={"Retry-After": "0"})
        return httpx.Response(200, json={"id": "job"})
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as hc:
        client = WaveSpeedClient(**client_kwargs, client=hc)
        assert await client.submit_job("p", 2, "16:9") == "job"
        assert calls == 2

async def test_500_post_no_retry(client_kwargs):
    calls = 0
    def handler(r):
        nonlocal calls
        calls += 1
        return httpx.Response(500, text="error")
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as hc:
        client = WaveSpeedClient(**client_kwargs, client=hc)
        with pytest.raises(TransientVideoError):
            await client.submit_job("p", 2, "16:9")
        assert calls == 1

async def test_blank_key_raises():
    with pytest.raises(PermanentVideoError):
        WaveSpeedClient("", "url", "model", "480p", True, False, "drop", 30)
