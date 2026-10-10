import pytest
import asyncio
from unittest.mock import patch, MagicMock

from app.schemas.video_job import VideoJobStatus
from app.db import video_jobs_repository as repo
from app.graph.state import AgentState
from app.schemas.agent import AgentStatus
from app.graph.nodes.generate_videos import generate_videos
from app.services.video_generation.mock_client import MockVideoClient
from app.services.video_generation.poller import run_poller_loop
from app.schemas.generated_prompt import PromptSet, GeneratedPrompt
from app.schemas.specification import VideoSpecification

# Minimal mock for the Cloudinary upload in storage and stitcher
@pytest.fixture(autouse=True)
def mock_cloudinary():
    with patch("app.services.video_generation.storage.upload_video", return_value="https://res.cloudinary.com/mock-video.mp4") as m1:
        with patch("app.services.cloudinary_service.upload_video", return_value="https://res.cloudinary.com/mock-final.mp4") as m2:
            yield m1, m2

@pytest.fixture
def mock_db(monkeypatch):
    """Ensure tests run against a clean test DB or just patch repository."""
    # For a real project we'd use a test DB. We'll just patch the repo for isolated tests.
    jobs = {}
    projects = {}

    def _create_job(j):
        jobs[j.job_id] = j

    def _update_job_status(jid, status, **kwargs):
        if jid in jobs:
            jobs[jid].status = status
            for k, v in kwargs.items():
                setattr(jobs[jid], k, v)

    def _get_jobs(pid):
        return [j for j in jobs.values() if j.project_id == pid]

    def _get_incomplete():
        return [j for j in jobs.values() if j.status in (VideoJobStatus.QUEUED, VideoJobStatus.SUBMITTED, VideoJobStatus.PROCESSING, VideoJobStatus.RETRYING)]
        
    def _set_final_url(pid, url):
        projects[pid] = url
        
    def _get_final_url(pid):
        return projects.get(pid)

    monkeypatch.setattr(repo, "create_job", _create_job)
    monkeypatch.setattr(repo, "update_job_status", _update_job_status)
    monkeypatch.setattr(repo, "get_jobs_for_project", _get_jobs)
    monkeypatch.setattr(repo, "get_incomplete_jobs", _get_incomplete)
    monkeypatch.setattr(repo, "set_project_final_video_url", _set_final_url)
    monkeypatch.setattr(repo, "get_project_final_video_url", _get_final_url)


@pytest.mark.asyncio
async def test_video_generation_happy_path(mock_db, monkeypatch):
    # Setup test state
    project_id = "test-proj-happy"
    prompt_set = PromptSet(
        prompts=[
            GeneratedPrompt(prompt_id="p1", scene_id="sc1", shot_id="sh1", sequence_number=1, duration_seconds=5, prompt_text="A"),
            GeneratedPrompt(prompt_id="p2", scene_id="sc1", shot_id="sh2", sequence_number=2, duration_seconds=5, prompt_text="B"),
        ]
    )
    spec = VideoSpecification(project_id=project_id)
    
    state = AgentState(
        project_id=project_id,
        prompt_set=prompt_set,
        video_specification=spec,
        status=AgentStatus.COMPLETED
    )

    # Use a fast mock client
    fast_client = MockVideoClient(submit_delay=0.01, polls_before_done=2, simulate_failure=False)
    monkeypatch.setattr("app.graph.nodes.generate_videos.get_video_client", lambda: fast_client)
    monkeypatch.setattr("app.services.video_generation.poller.get_video_client", lambda: fast_client)
    
    # We must patch httpx and ffmpeg in stitcher and storage to not actually make real network/process calls
    with patch("app.services.video_generation.storage.httpx.AsyncClient") as mock_httpx:
        mock_httpx.return_value.__aenter__.return_value.get.return_value.content = b"fakevideo"
        mock_httpx.return_value.__aenter__.return_value.get.return_value.raise_for_status = MagicMock()
        
        with patch("app.services.video_generation.stitcher.subprocess.run") as mock_exec:
            mock_proc = MagicMock()
            mock_proc.returncode = 0
            mock_proc.stdout = b""
            mock_proc.stderr = b""
            mock_exec.return_value = mock_proc
            
            with patch("app.services.video_generation.stitcher.os.path.exists", return_value=True):
                with patch("app.services.video_generation.stitcher.os.path.getsize", return_value=100):
                    with patch("app.services.video_generation.stitcher.open"):
                    
                        # 1. Trigger generate_videos (Node)
                        new_state = await generate_videos(state)
                        assert new_state["status"] == AgentStatus.GENERATING_VIDEOS
                        
                        # Wait briefly for background submissions to hit the mock DB
                        for _ in range(10):
                            jobs = repo.get_jobs_for_project(project_id)
                            if len(jobs) == 2 and all(j.status == VideoJobStatus.SUBMITTED for j in jobs):
                                break
                            await asyncio.sleep(0.1)
                        
                        jobs = repo.get_jobs_for_project(project_id)
                        assert len(jobs) == 2
                        assert all(j.status == VideoJobStatus.SUBMITTED for j in jobs)

                        # 2. Run poller manually a few times instead of waiting in a loop
                        from app.services.video_generation.poller import _process_completed_job, _check_and_trigger_stitching
                        
                        # Poll 1 (PROCESSING)
                        for job in repo.get_incomplete_jobs():
                            res = await fast_client.check_status(job.external_job_id)
                            assert res["status"] == "PROCESSING"
                            repo.update_job_status(job.job_id, VideoJobStatus.PROCESSING)
                            
                        # Poll 2 (COMPLETED)
                        for job in repo.get_incomplete_jobs():
                            res = await fast_client.check_status(job.external_job_id)
                            assert res["status"] == "COMPLETED"
                            await _process_completed_job(job, res)

                        assert all(j.status == VideoJobStatus.COMPLETED for j in repo.get_jobs_for_project(project_id))
                        
                        # 3. Stitching
                        await _check_and_trigger_stitching(project_id)
                        
                        assert repo.get_project_final_video_url(project_id) == "https://res.cloudinary.com/mock-final.mp4"

class AsyncMock(MagicMock):
    async def __call__(self, *args, **kwargs):
        return super(AsyncMock, self).__call__(*args, **kwargs)
