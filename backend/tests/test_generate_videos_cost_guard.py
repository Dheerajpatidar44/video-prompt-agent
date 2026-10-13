import pytest
from app.graph.nodes.generate_videos import generate_videos
from app.core.config import settings

@pytest.fixture
def mock_state():
    class DummyPrompt:
        def __init__(self, id, d):
            self.prompt_id = id
            self.shot_id = id
            self.sequence_number = 1
            self.duration_seconds = d
            self.prompt_text = "test"
            self.negative_constraints = None
    class DummyPromptSet:
        prompts = [DummyPrompt("1", 4.0), DummyPrompt("2", 4.0)]
    class DummyOutputReq:
        aspect_ratio = "16:9"
    class DummySpec:
        output_requirements = DummyOutputReq()
        reference_assets = []
    
    return {
        "project_id": "test_proj",
        "prompt_set": DummyPromptSet(),
        "video_specification": DummySpec()
    }

@pytest.mark.asyncio
async def test_guard_exceeded_cost(mock_state, monkeypatch):
    # Two 4s clips @ 720p = $0.40. If limit is $0.30, it gets blocked.
    monkeypatch.setattr(settings, "use_mock_video_api", False)
    monkeypatch.setattr(settings, "video_max_estimated_cost_usd", 0.30)
    monkeypatch.setattr(settings, "video_provider", "veo")
    monkeypatch.setattr(settings, "veo_resolution", "720p")
    
    res = await generate_videos(mock_state)
    assert res["video_generation_status"] == "BLOCKED_COST_GUARD"

@pytest.mark.asyncio
async def test_guard_exceeded_shots(mock_state, monkeypatch):
    monkeypatch.setattr(settings, "use_mock_video_api", False)
    monkeypatch.setattr(settings, "video_max_shots_per_project", 1)
    monkeypatch.setattr(settings, "video_provider", "veo")
    
    res = await generate_videos(mock_state)
    assert res["video_generation_status"] == "BLOCKED_COST_GUARD"

@pytest.mark.asyncio
async def test_guard_exceeded_seconds(mock_state, monkeypatch):
    # Two 4s clips = 8 seconds total billed. Limit 6 seconds -> blocked.
    monkeypatch.setattr(settings, "use_mock_video_api", False)
    monkeypatch.setattr(settings, "video_max_total_seconds_per_project", 6)
    monkeypatch.setattr(settings, "video_provider", "veo")
    
    res = await generate_videos(mock_state)
    assert res["video_generation_status"] == "BLOCKED_COST_GUARD"

@pytest.mark.asyncio
async def test_under_limits(mock_state, monkeypatch):
    # Two 4s clips = $0.40. Limit $0.50 -> allowed.
    monkeypatch.setattr(settings, "use_mock_video_api", False)
    monkeypatch.setattr(settings, "video_max_estimated_cost_usd", 0.50)
    monkeypatch.setattr(settings, "video_max_shots_per_project", 5)
    monkeypatch.setattr(settings, "video_max_total_seconds_per_project", 20)
    monkeypatch.setattr(settings, "video_provider", "veo")
    monkeypatch.setattr(settings, "veo_resolution", "720p")
    
    import app.graph.nodes.generate_videos as gv
    
    class FakeClient:
        async def submit_job(self, *a, **kw):
            return "op_123"
            
    monkeypatch.setattr(gv, "get_video_client", lambda: FakeClient())
    monkeypatch.setattr(gv.repo, "create_job", lambda j: None)
    monkeypatch.setattr(gv.repo, "update_job_status", lambda *a, **k: None)
    
    res = await generate_videos(mock_state)
    assert res["video_generation_status"] == "IN_PROGRESS"

@pytest.mark.asyncio
async def test_mock_mode_ignores_guard(mock_state, monkeypatch):
    monkeypatch.setattr(settings, "use_mock_video_api", True)
    monkeypatch.setattr(settings, "video_max_estimated_cost_usd", 0.0)
    
    import app.graph.nodes.generate_videos as gv
    
    class FakeClient:
        async def submit_job(self, *a, **kw):
            return "id"
            
    monkeypatch.setattr(gv, "get_video_client", lambda: FakeClient())
    monkeypatch.setattr(gv.repo, "create_job", lambda j: None)
    monkeypatch.setattr(gv.repo, "update_job_status", lambda *a, **k: None)
    
    res = await generate_videos(mock_state)
    assert res["video_generation_status"] == "IN_PROGRESS"
