import pytest
import asyncio
from datetime import datetime, UTC, timedelta
from app.schemas.video_job import VideoJob, VideoJobStatus
from app.services.video_generation.base_client import PermanentVideoError, TransientVideoError
from app.core.config import settings
import app.services.video_generation.poller as poller

@pytest.fixture
def fake_repo(monkeypatch):
    class FakeRepo:
        def __init__(self):
            self.jobs = []
            self.updates = []
        def get_incomplete_jobs(self):
            return self.jobs
        def update_job_status(self, job_id, status, **kwargs):
            self.updates.append((job_id, status, kwargs))
            for j in self.jobs:
                if j.job_id == job_id:
                    j.status = status
        def get_project_final_video_url(self, *a):
            return None
        def get_jobs_for_project(self, *a):
            return self.jobs
    repo = FakeRepo()
    monkeypatch.setattr(poller, "repo", repo)
    return repo

@pytest.fixture
def fake_client(monkeypatch):
    class FakeClient:
        def __init__(self):
            self.err = None
            self.status = "PROCESSING"
        async def check_status(self, *a):
            if self.err: raise self.err
            return {"status": self.status, "error": getattr(self, "err_msg", None)}
        async def submit_job(self, *a, **kw):
            return "new_id"
    client = FakeClient()
    monkeypatch.setattr(poller, "get_video_client", lambda: client)
    return client

@pytest.fixture(autouse=True)
def mock_sleep_and_stitching(monkeypatch):
    async def mock_sleep(seconds):
        raise asyncio.CancelledError()
    monkeypatch.setattr(asyncio, "sleep", mock_sleep)
    monkeypatch.setattr(poller, "stitch_project_videos", lambda *a: asyncio.sleep(0))
    monkeypatch.setattr(poller, "_job_error_counts", {})

@pytest.mark.asyncio
async def test_transient_error(fake_repo, fake_client, monkeypatch):
    monkeypatch.setattr(settings, "video_status_max_consecutive_errors", 2)
    job = VideoJob(job_id="1", project_id="p1", prompt_id="pr1", shot_id="s1", sequence_number=1, status=VideoJobStatus.SUBMITTED, external_job_id="ext1")
    fake_repo.jobs.append(job)
    fake_client.err = TransientVideoError("boom")
    
    # Attempt 1 -> warning, loop stops due to sleep raise
    await poller.run_poller_loop()
    assert len(fake_repo.updates) == 0
    assert poller._job_error_counts["1"] == 1
    
    # Attempt 2 -> FAILED
    await poller.run_poller_loop()
    assert len(fake_repo.updates) == 1
    assert fake_repo.updates[0][1] == VideoJobStatus.FAILED
    assert "status check unreachable" in fake_repo.updates[0][2]["error_message"]
    assert "1" not in poller._job_error_counts

@pytest.mark.asyncio
async def test_permanent_error_resubmits(fake_repo, fake_client, monkeypatch):
    job = VideoJob(job_id="1", project_id="p1", prompt_id="pr1", shot_id="s1", sequence_number=1, status=VideoJobStatus.SUBMITTED, external_job_id="ext1")
    fake_repo.jobs.append(job)
    fake_client.err = PermanentVideoError("404")
    
    async def dummy_state(*a):
        class P: 
            prompt_id = "pr1"
            prompt_text = "test"
            duration_seconds = 2
            negative_constraints = None
        class S: 
            prompts = [P()]
        class OR: aspect_ratio="16:9"
        class Spec: output_requirements=OR()
        return {"prompt_set": S(), "video_specification": Spec()}
        
    import app.api.routes.scripts as scripts
    monkeypatch.setattr(scripts, "_get_state_values", dummy_state)
    
    await poller.run_poller_loop()
    assert len(fake_repo.updates) == 1
    assert fake_repo.updates[0][1] == VideoJobStatus.SUBMITTED
    assert fake_repo.updates[0][2]["external_job_id"] == "new_id"

@pytest.mark.asyncio
async def test_job_timeout(fake_repo, fake_client, monkeypatch):
    monkeypatch.setattr(settings, "video_job_max_wait_seconds", 10)
    job = VideoJob(
        job_id="1", project_id="p1", prompt_id="pr1", shot_id="s1", sequence_number=1, 
        status=VideoJobStatus.SUBMITTED, external_job_id="ext1",
        submitted_at=datetime.now(UTC) - timedelta(seconds=20)
    )
    fake_repo.jobs.append(job)
    
    await poller.run_poller_loop()
    assert len(fake_repo.updates) == 1
    assert fake_repo.updates[0][1] == VideoJobStatus.FAILED
    assert "timed out" in fake_repo.updates[0][2]["error_message"]

@pytest.mark.asyncio
async def test_provider_failed(fake_repo, fake_client, monkeypatch):
    job = VideoJob(job_id="1", project_id="p1", prompt_id="pr1", shot_id="s1", sequence_number=1, status=VideoJobStatus.SUBMITTED, external_job_id="ext1")
    job.retry_count = 5 # exceed
    monkeypatch.setattr(settings, "video_max_retries", 2)
    fake_repo.jobs.append(job)
    fake_client.status = "FAILED"
    fake_client.err_msg = "bad prompt"
    
    await poller.run_poller_loop()
    assert len(fake_repo.updates) == 1
    assert fake_repo.updates[0][1] == VideoJobStatus.FAILED
    assert fake_repo.updates[0][2]["error_message"] == "bad prompt"
