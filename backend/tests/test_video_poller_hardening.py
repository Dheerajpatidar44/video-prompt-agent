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
            shot_id = "s1"
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


@pytest.mark.asyncio
async def test_non_retryable_failure_no_resubmit(fake_repo, fake_client, monkeypatch):
    job = VideoJob(
        job_id="1", project_id="p1", prompt_id="pr1", shot_id="s1", sequence_number=1,
        status=VideoJobStatus.SUBMITTED, external_job_id="ext1"
    )
    fake_repo.jobs.append(job)
    fake_client.status = "FAILED"
    fake_client.err_msg = "Safety blocked"

    async def mock_check_status(*a):
        return {"status": "FAILED", "error": "Safety blocked", "retryable": False}

    fake_client.check_status = mock_check_status

    resubmitted = False
    async def mock_submit(*a, **k):
        nonlocal resubmitted
        resubmitted = True
        return "new_id"

    fake_client.submit_job = mock_submit

    await poller.run_poller_loop()
    assert len(fake_repo.updates) == 1
    assert fake_repo.updates[0][1] == VideoJobStatus.FAILED
    assert "Safety blocked" in fake_repo.updates[0][2]["error_message"]
    assert resubmitted is False


@pytest.mark.asyncio
async def test_poller_passes_downloader_when_required(fake_repo, monkeypatch):
    job = VideoJob(
        job_id="1", project_id="p1", prompt_id="pr1", shot_id="s1", sequence_number=1,
        status=VideoJobStatus.SUBMITTED, external_job_id="ext1"
    )
    fake_repo.jobs.append(job)

    class AuthClient:
        requires_authenticated_download = True
        async def check_status(self, *a):
            return {"status": "COMPLETED", "video_url": "https://storage.googleapis.com/vid.mp4"}
        async def download_video(self, url):
            return b"bytes"

    client = AuthClient()
    monkeypatch.setattr(poller, "get_video_client", lambda: client)

    captured_downloader = None
    async def fake_store_video(url, pid, sid, downloader=None):
        nonlocal captured_downloader
        captured_downloader = downloader
        return "https://cloudinary/permanent.mp4"

    monkeypatch.setattr(poller, "store_video", fake_store_video)

    await poller.run_poller_loop()
    assert len(fake_repo.updates) == 1
    assert fake_repo.updates[0][1] == VideoJobStatus.COMPLETED
    assert captured_downloader == client.download_video



@pytest.mark.asyncio
async def test_poller_regenerates_image_on_veo_safety_rejection(fake_repo, fake_client, monkeypatch):
    poller._image_regen_counts.clear()
    poller._job_error_counts.clear()

    job = VideoJob(
        job_id="job_safety_1", project_id="p1", prompt_id="pr1", shot_id="s1", sequence_number=1,
        status=VideoJobStatus.SUBMITTED, external_job_id="ext_safety"
    )
    fake_repo.jobs.append(job)

    async def mock_check_status(*a):
        return {
            "status": "FAILED",
            "error": "The input image violates Vertex AI's usage guidelines. [15236754]"
        }

    fake_client.check_status = mock_check_status

    from unittest.mock import MagicMock
    fake_prompt = MagicMock()
    fake_prompt.prompt_id = "pr1"
    fake_prompt.shot_id = "s1"
    fake_prompt.keyframe_image_prompt = "Close up of model wearing jacket"
    fake_prompt.prompt_text = "Close up video of model"
    fake_prompt.duration_seconds = 4
    fake_prompt.negative_constraints = None

    fake_spec = MagicMock()
    fake_spec.output_requirements.aspect_ratio = "16:9"

    fake_state = {
        "prompt_set": MagicMock(prompts=[fake_prompt]),
        "video_specification": fake_spec,
        "reference_images": {"character": ["https://cdn.com/char.png"]},
    }

    async def fake_get_state(project_id):
        return fake_state

    import app.api.routes.scripts as scripts
    monkeypatch.setattr(scripts, "_get_state_values", fake_get_state)

    regen_called = False
    class FakeImgService:
        async def generate_image(self, prompt, aspect_ratio, ref_images, custom_filename):
            nonlocal regen_called
            regen_called = True
            return f"static/generated_images/{custom_filename}"

    import app.services.image_generation.gemini_image_service as gis
    monkeypatch.setattr(gis, "get_gemini_image_service", lambda: FakeImgService())

    submitted_ref_assets = None
    async def mock_submit(prompt_text, duration_seconds, aspect_ratio, negative_prompt, reference_assets):
        nonlocal submitted_ref_assets
        submitted_ref_assets = reference_assets
        return "ext_regen_resubmit"

    fake_client.submit_job = mock_submit

    await poller.run_poller_loop()

    assert regen_called is True
    assert submitted_ref_assets is not None
    assert submitted_ref_assets[0]["path"] == "static/generated_images/p1_s1_keyframe_regen1.png"
    assert len(fake_repo.updates) == 1
    assert fake_repo.updates[0][1] == VideoJobStatus.SUBMITTED
    assert fake_repo.updates[0][2]["external_job_id"] == "ext_regen_resubmit"
    assert "[image_regen #1]" in fake_repo.updates[0][2]["error_message"]
    assert poller._image_regen_counts.get("job_safety_1") == 1


@pytest.mark.asyncio
async def test_poller_fails_permanently_when_image_regen_retries_exhausted(fake_repo, fake_client, monkeypatch):
    poller._image_regen_counts.clear()
    poller._job_error_counts.clear()

    # Pre-set regen count to max (1)
    poller._image_regen_counts["job_safety_2"] = 1

    job = VideoJob(
        job_id="job_safety_2", project_id="p1", prompt_id="pr1", shot_id="s1", sequence_number=1,
        status=VideoJobStatus.SUBMITTED, external_job_id="ext_safety_2"
    )
    fake_repo.jobs.append(job)

    async def mock_check_status(*a):
        return {
            "status": "FAILED",
            "error": "The input image violates Vertex AI's usage guidelines. [15236754]"
        }

    fake_client.check_status = mock_check_status

    submit_called = False
    async def mock_submit(*a, **kw):
        nonlocal submit_called
        submit_called = True
        return "new_id"

    fake_client.submit_job = mock_submit

    await poller.run_poller_loop()

    # Should not resubmit again
    assert submit_called is False
    assert len(fake_repo.updates) == 1
    assert fake_repo.updates[0][1] == VideoJobStatus.FAILED
    assert "persisted after 1 image regeneration attempt" in fake_repo.updates[0][2]["error_message"]
    assert "job_safety_2" not in poller._image_regen_counts


@pytest.mark.asyncio
async def test_poller_regenerates_image_on_celebrity_likeness_rai(fake_repo, fake_client, monkeypatch):
    poller._image_regen_counts.clear()
    poller._job_error_counts.clear()

    job = VideoJob(
        job_id="job_celeb_1", project_id="p1", prompt_id="pr1", shot_id="s1", sequence_number=1,
        status=VideoJobStatus.SUBMITTED, external_job_id="ext_celeb"
    )
    fake_repo.jobs.append(job)

    async def mock_check_status(*a):
        return {
            "status": "FAILED",
            "error": "Video generation completed without video (blocked by safety filters: Sorry, we can't create videos from input images containing celebrity or their likenesses.)",
            "image_safety_rejected": True,
            "retryable": True,
        }

    fake_client.check_status = mock_check_status

    from unittest.mock import MagicMock
    fake_prompt = MagicMock()
    fake_prompt.prompt_id = "pr1"
    fake_prompt.shot_id = "s1"
    fake_prompt.keyframe_image_prompt = "Two executives seated in boardroom"
    fake_prompt.prompt_text = "Executives sliding folder"
    fake_prompt.duration_seconds = 8
    fake_prompt.negative_constraints = None

    fake_spec = MagicMock()
    fake_spec.output_requirements.aspect_ratio = "16:9"

    fake_state = {
        "prompt_set": MagicMock(prompts=[fake_prompt]),
        "video_specification": fake_spec,
        "reference_images": {},
    }

    async def fake_get_state(project_id):
        return fake_state

    import app.api.routes.scripts as scripts
    monkeypatch.setattr(scripts, "_get_state_values", fake_get_state)

    class FakeImgService:
        async def generate_image(self, prompt, aspect_ratio, ref_images, custom_filename):
            return f"static/generated_images/{custom_filename}"

    import app.services.image_generation.gemini_image_service as gis
    monkeypatch.setattr(gis, "get_gemini_image_service", lambda: FakeImgService())

    submitted_ref_assets = None
    async def mock_submit(prompt_text, duration_seconds, aspect_ratio, negative_prompt, reference_assets):
        nonlocal submitted_ref_assets
        submitted_ref_assets = reference_assets
        return "ext_celeb_regen"

    fake_client.submit_job = mock_submit

    await poller.run_poller_loop()

    assert submitted_ref_assets is not None
    assert submitted_ref_assets[0]["path"] == "static/generated_images/p1_s1_keyframe_regen1.png"
    assert fake_repo.updates[0][1] == VideoJobStatus.SUBMITTED
    assert fake_repo.updates[0][2]["external_job_id"] == "ext_celeb_regen"


@pytest.mark.asyncio
async def test_poller_retry_preserves_reference_assets_no_text_fallback(fake_repo, fake_client, monkeypatch):
    poller._image_regen_counts.clear()
    poller._job_error_counts.clear()

    job = VideoJob(
        job_id="job_keep_ref", project_id="p1", prompt_id="pr1", shot_id="s1", sequence_number=1,
        status=VideoJobStatus.SUBMITTED, external_job_id="ext_keep_ref"
    )
    fake_repo.jobs.append(job)

    async def mock_check_status(*a):
        return {
            "status": "FAILED",
            "error": "Transient error with reference image payload",
        }

    fake_client.check_status = mock_check_status

    from unittest.mock import MagicMock
    fake_prompt = MagicMock()
    fake_prompt.prompt_id = "pr1"
    fake_prompt.shot_id = "s1"
    fake_prompt.prompt_text = "Boardroom shot"
    fake_prompt.duration_seconds = 8
    fake_prompt.negative_constraints = None

    fake_spec = MagicMock()
    fake_spec.output_requirements.aspect_ratio = "16:9"

    fake_state = {
        "prompt_set": MagicMock(prompts=[fake_prompt]),
        "video_specification": fake_spec,
        "shot_image_manifest": {
            "s1": [{"path": "static/generated_images/p1_s1_keyframe.png", "role": "MASTER_KEYFRAME", "asset_id": "s1_kf", "reused": False}]
        },
    }

    async def fake_get_state(project_id):
        return fake_state

    import app.api.routes.scripts as scripts
    monkeypatch.setattr(scripts, "_get_state_values", fake_get_state)

    captured_assets = None
    async def mock_submit(prompt_text, duration_seconds, aspect_ratio, negative_prompt, reference_assets):
        nonlocal captured_assets
        captured_assets = reference_assets
        return "ext_resubmitted"

    fake_client.submit_job = mock_submit

    await poller.run_poller_loop()

    assert captured_assets is not None
    assert captured_assets[0]["path"] == "static/generated_images/p1_s1_keyframe.png"
    assert fake_repo.updates[0][1] == VideoJobStatus.SUBMITTED

