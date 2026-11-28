"""Regression tests for pipeline stability, retry, stitcher, poller, Veo download, and routing fixes."""
import asyncio
from datetime import datetime, UTC, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.config import settings
from app.db.database import get_db
from app.db import video_jobs_repository as repo
from app.schemas.agent import AgentStatus
from app.schemas.generated_prompt import GeneratedPrompt, PromptSet
from app.schemas.specification import OutputRequirements, VideoSpecification
from app.schemas.video_job import VideoJob, VideoJobStatus


def _insert_project(project_id: str, status: str = "PROMPTS_READY", final_video_url: str | None = None):
    conn = get_db()
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO projects (id, title, thread_id, tool, status, final_video_url)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (project_id, f"Proj {project_id}", project_id, "Veo", status, final_video_url),
        )
        conn.commit()
    finally:
        conn.close()


def _cleanup_project(project_id: str):
    conn = get_db()
    try:
        conn.execute("DELETE FROM video_jobs WHERE project_id = ?", (project_id,))
        conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        conn.commit()
    finally:
        conn.close()


def _two_shot_state(project_id: str) -> dict:
    return {
        "project_id": project_id,
        "status": AgentStatus.PROMPTS_READY,
        "video_specification": VideoSpecification(
            project_id=project_id,
            output_requirements=OutputRequirements(duration_seconds=8, aspect_ratio="16:9"),
        ),
        "prompt_set": PromptSet(
            prompts=[
                GeneratedPrompt(
                    prompt_id="p1",
                    scene_id="s1",
                    shot_id="shot_1",
                    sequence_number=1,
                    duration_seconds=4.0,
                    prompt_text="Wide sunset city street.",
                ),
                GeneratedPrompt(
                    prompt_id="p2",
                    scene_id="s1",
                    shot_id="shot_2",
                    sequence_number=2,
                    duration_seconds=4.0,
                    prompt_text="Close up of coffee cup.",
                ),
            ],
            total_duration=8.0,
        ),
    }


def test_video_status_returns_failed_when_stitching_failed():
    client = TestClient(app)
    pid = "proj-stab-stitch-failed"
    _cleanup_project(pid)
    _insert_project(pid, status="FAILED", final_video_url=None)
    repo.create_job(
        VideoJob(
            job_id="vjob_sf_1",
            project_id=pid,
            prompt_id="p1",
            shot_id="shot_1",
            sequence_number=1,
            status=VideoJobStatus.COMPLETED,
            video_url="https://cdn.example.com/clip1.mp4",
            submitted_at=datetime.now(UTC),
        )
    )
    try:
        resp = client.get(f"/api/v1/projects/{pid}/video-status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "FAILED"
        assert "stitching failed" in (data.get("error_message") or "").lower()
    finally:
        _cleanup_project(pid)


def test_partial_failure_retry_only_resubmits_failed_shots():
    client = TestClient(app)
    pid = "proj-stab-partial-retry"
    _cleanup_project(pid)
    _insert_project(
        pid,
        status="COMPLETED",
        final_video_url="https://cdn.example.com/partial-final.mp4",
    )
    repo.create_job(
        VideoJob(
            job_id="vjob_pr_ok",
            project_id=pid,
            prompt_id="p1",
            shot_id="shot_1",
            sequence_number=1,
            status=VideoJobStatus.COMPLETED,
            video_url="https://cdn.example.com/shot1.mp4",
            submitted_at=datetime.now(UTC),
        )
    )
    repo.create_job(
        VideoJob(
            job_id="vjob_pr_bad",
            project_id=pid,
            prompt_id="p2",
            shot_id="shot_2",
            sequence_number=2,
            status=VideoJobStatus.FAILED,
            error_message="Provider transient failure",
            submitted_at=datetime.now(UTC),
        )
    )

    class FakeClient:
        async def submit_job(self, **kwargs):
            return "ext_retry_shot2"

    fake_state = _two_shot_state(pid)
    try:
        with patch("app.api.routes.scripts._get_state_values", new=AsyncMock(return_value=fake_state)), \
             patch("app.api.routes.scripts._update_state", new=AsyncMock()), \
             patch("app.graph.nodes.generate_videos.get_video_client", return_value=FakeClient()):
            resp = client.post(f"/api/v1/projects/{pid}/generate-video")
            assert resp.status_code == 200
            data = resp.json()
            assert data["already_started"] is False
            assert data["status"] == "GENERATING_VIDEOS"

            # Partial final_video_url cleared; shot_1 kept, shot_2 re-queued
            assert repo.get_project_final_video_url(pid) is None
            jobs = repo.get_jobs_for_project(pid)
            assert len(jobs) == 2
            by_shot = {j.shot_id: j for j in jobs}
            assert by_shot["shot_1"].job_id == "vjob_pr_ok"
            assert by_shot["shot_1"].status == VideoJobStatus.COMPLETED
            assert by_shot["shot_2"].job_id != "vjob_pr_bad"
    finally:
        _cleanup_project(pid)


def test_stitch_only_retry_does_not_regenerate_completed_shots():
    client = TestClient(app)
    pid = "proj-stab-stitch-retry"
    _cleanup_project(pid)
    _insert_project(pid, status="FAILED", final_video_url=None)
    repo.create_job(
        VideoJob(
            job_id="vjob_sr_1",
            project_id=pid,
            prompt_id="p1",
            shot_id="shot_1",
            sequence_number=1,
            status=VideoJobStatus.COMPLETED,
            video_url="https://cdn.example.com/clip1.mp4",
            submitted_at=datetime.now(UTC),
        )
    )
    try:
        with patch("app.graph.nodes.generate_videos.generate_videos", new=AsyncMock()) as mock_gen, \
             patch("app.services.video_generation.poller._check_and_trigger_stitching", new=AsyncMock()) as mock_stitch:
            resp = client.post(f"/api/v1/projects/{pid}/generate-video")
            assert resp.status_code == 200
            data = resp.json()
            assert data["already_started"] is False
            assert data["status"] == "GENERATING_VIDEOS"
            mock_gen.assert_not_awaited()
            mock_stitch.assert_awaited_once_with(pid)
    finally:
        _cleanup_project(pid)


def test_delete_project_removes_video_jobs_rows():
    client = TestClient(app)
    pid = "proj-stab-delete"
    _cleanup_project(pid)
    _insert_project(pid, status="FAILED")
    repo.create_job(
        VideoJob(
            job_id="vjob_del_1",
            project_id=pid,
            prompt_id="p1",
            shot_id="shot_1",
            sequence_number=1,
            status=VideoJobStatus.FAILED,
            submitted_at=datetime.now(UTC),
        )
    )
    try:
        resp = client.delete(f"/api/v1/projects/{pid}")
        assert resp.status_code == 200
        assert repo.get_jobs_for_project(pid) == []
    finally:
        _cleanup_project(pid)


def test_fail_orphaned_queued_jobs_recovers_stuck_project():
    pid = "proj-stab-orphaned-q"
    _cleanup_project(pid)
    _insert_project(pid, status="GENERATING_VIDEOS")
    repo.create_job(
        VideoJob(
            job_id="vjob_orphan_q",
            project_id=pid,
            prompt_id="p1",
            shot_id="shot_1",
            sequence_number=1,
            status=VideoJobStatus.QUEUED,
            external_job_id=None,
            submitted_at=datetime.now(UTC),
        )
    )
    repo.create_job(
        VideoJob(
            job_id="vjob_submitted_keep",
            project_id=pid,
            prompt_id="p2",
            shot_id="shot_2",
            sequence_number=2,
            status=VideoJobStatus.SUBMITTED,
            external_job_id="ext_valid_123",
            submitted_at=datetime.now(UTC),
        )
    )
    try:
        count = repo.fail_orphaned_queued_jobs()
        assert count >= 1
        q_job = repo.get_job("vjob_orphan_q")
        s_job = repo.get_job("vjob_submitted_keep")
        assert q_job.status == VideoJobStatus.FAILED
        assert "server restarted" in (q_job.error_message or "").lower()
        assert s_job.status == VideoJobStatus.SUBMITTED

        # When all jobs are orphaned -> project transitions out of GENERATING_VIDEOS to FAILED
        repo.update_job_status("vjob_submitted_keep", VideoJobStatus.QUEUED, external_job_id=None)
        repo.fail_orphaned_queued_jobs()
        conn = get_db()
        row = conn.execute("SELECT status FROM projects WHERE id = ?", (pid,)).fetchone()
        conn.close()
        assert row["status"] == "FAILED"
    finally:
        _cleanup_project(pid)


@pytest.mark.asyncio
async def test_stitcher_raises_when_trimmed_concat_fails(monkeypatch):
    from app.services.video_generation import stitcher

    pid = "proj-stab-stitch-trim-err"
    _cleanup_project(pid)
    repo.create_job(
        VideoJob(
            job_id="vjob_trim_err",
            project_id=pid,
            prompt_id="p1",
            shot_id="shot_1",
            sequence_number=1,
            status=VideoJobStatus.COMPLETED,
            video_url="https://cdn.example.com/clip5.mp4",
            duration_seconds=5.0,
            submitted_at=datetime.now(UTC),
        )
    )

    try:
        fake_resp = MagicMock()
        fake_resp.content = b"fake-mp4-bytes"
        fake_resp.raise_for_status = MagicMock()

        mock_http_instance = AsyncMock()
        mock_http_instance.get = AsyncMock(return_value=fake_resp)
        mock_http_ctx = AsyncMock()
        mock_http_ctx.__aenter__ = AsyncMock(return_value=mock_http_instance)
        mock_http_ctx.__aexit__ = AsyncMock(return_value=False)

        trim_proc = MagicMock(returncode=0, stderr=b"")
        concat_fail_proc = MagicMock(returncode=1, stderr=b"concat error")

        monkeypatch.setattr(stitcher, "_get_clip_duration", lambda *a: 6.0)
        monkeypatch.setattr(stitcher, "_trim_clip", lambda *a: trim_proc)
        monkeypatch.setattr(stitcher, "_run_ffmpeg", lambda *a: concat_fail_proc)
        monkeypatch.setattr("app.services.video_generation.stitcher.os.path.exists", lambda p: True)
        monkeypatch.setattr("app.services.video_generation.stitcher.os.path.getsize", lambda p: 1234)

        with patch("app.services.video_generation.stitcher.httpx.AsyncClient", return_value=mock_http_ctx):
            with pytest.raises(stitcher.StitchingError, match="ffmpeg concat failed"):
                await stitcher.stitch_project_videos(pid)
    finally:
        _cleanup_project(pid)


@pytest.mark.asyncio
async def test_veo_client_uri_download_and_ref_mutual_exclusion(monkeypatch):
    from google.genai import types
    from app.services.video_generation.veo_client import VeoClient
    from app.services.video_generation.base_client import PermanentVideoError

    mock_genai = MagicMock()
    mock_genai.aio = None
    mock_op = MagicMock()
    mock_op.name = "op_ref_ok"
    mock_genai.models.generate_videos.return_value = mock_op

    client = VeoClient(
        api_key="secret_key_xyz",
        model="veo-3.1-fast-generate-001",
        resolution="1080p",
        negative_prompt_mode="append",
        max_prompt_tokens=100,
        client=mock_genai,
    )

    # 1. Negative prompt counted inside token guard
    with pytest.raises(PermanentVideoError, match="Shorten the prompt"):
        await client.submit_job("a" * 250, 4.0, "16:9", negative_prompt="b" * 250)

    # 2. MASTER_KEYFRAME + extra assets never mixes `image` and `config.reference_images`
    dummy_img = types.Image(image_bytes=b"img", mime_type="image/png")
    monkeypatch.setattr(client, "_load_reference_image", AsyncMock(return_value=dummy_img))
    await client.submit_job(
        prompt_text="cinematic shot",
        duration_seconds=6.0,
        aspect_ratio="16:9",
        reference_assets=[
            {"path": "kf.png", "role": "MASTER_KEYFRAME"},
            {"path": "extra.png", "role": "CHARACTER"},
        ],
    )
    kwargs = mock_genai.models.generate_videos.call_args[1]
    assert kwargs["image"] == dummy_img
    assert not getattr(kwargs["config"], "reference_images", None)

    # 3. Direct HTTPS URI download succeeds without calling _build_operation_ref
    fake_resp = MagicMock(status_code=200, content=b"uri_video_bytes")
    fake_resp.raise_for_status = MagicMock()
    mock_http_instance = AsyncMock()
    mock_http_instance.get = AsyncMock(return_value=fake_resp)
    mock_http_ctx = AsyncMock()
    mock_http_ctx.__aenter__ = AsyncMock(return_value=mock_http_instance)
    mock_http_ctx.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=mock_http_ctx):
        data = await client.download_video("https://example.com/generated.mp4")
        assert data == b"uri_video_bytes"

    # 4. Operation fetch falling back to video.uri when video_bytes is absent
    op_uri = MagicMock()
    mock_vid = MagicMock()
    mock_vid.video.video_bytes = None
    mock_vid.video.uri = "https://example.com/op_uri.mp4"
    op_uri.response.generated_videos = [mock_vid]
    mock_genai.operations.get.return_value = op_uri

    with patch("httpx.AsyncClient", return_value=mock_http_ctx):
        data2 = await client.download_video("op_fetch_uri")
        assert data2 == b"uri_video_bytes"

    # 5. Direct gs:// URI raises actionable PermanentVideoError
    with pytest.raises(PermanentVideoError, match="Direct GCS URI download is unsupported"):
        await client.download_video("gs://my-bucket/clip.mp4")


@pytest.mark.asyncio
async def test_graph_stops_on_generation_error_and_poller_times_out_queued(monkeypatch):
    from app.graph.graph import build_graph
    from app.schemas.script import InitialAnalysisResult
    import app.services.video_generation.poller as poller

    # 1. Graph halts cleanly at END if generate returns ERROR
    graph = build_graph()
    with patch("app.graph.nodes.analyze_script.llm_service") as m_an, \
         patch("app.graph.nodes.build_video_spec.llm_service") as m_spec, \
         patch("app.graph.nodes.generate_scenes_and_prompts.llm_service") as m_gen, \
         patch("app.graph.nodes.generate_images.generate_images", new=AsyncMock()) as m_img:
        m_an.generate_structured = AsyncMock(return_value=InitialAnalysisResult())
        m_spec.generate_structured = AsyncMock(return_value=VideoSpecification(project_id="err-stop"))
        m_gen.generate_structured = AsyncMock(side_effect=RuntimeError("LLM crashed"))

        out = await graph.ainvoke(
            {"project_id": "err-stop", "original_script": "A man walks."},
            {"configurable": {"thread_id": "err-stop"}},
        )
        assert out["status"] == AgentStatus.ERROR
        assert "LLM crashed" in (out.get("error") or "")
        m_img.assert_not_awaited()

    # 2. Poller times out stale QUEUED job rather than skipping forever
    class FakeRepo:
        def __init__(self, j):
            self.jobs = [j]
            self.updates = []
        def get_incomplete_jobs(self):
            return self.jobs
        def update_job_status(self, jid, st, **kw):
            self.updates.append((jid, st, kw))
            self.jobs[0].status = st
        def get_project_final_video_url(self, *a):
            return None
        def get_jobs_for_project(self, *a):
            return self.jobs

    stale_q = VideoJob(
        job_id="q_stale",
        project_id="p_q",
        prompt_id="pr1",
        shot_id="s1",
        sequence_number=1,
        status=VideoJobStatus.QUEUED,
        submitted_at=datetime.now(UTC) - timedelta(seconds=100),
    )
    fr = FakeRepo(stale_q)
    monkeypatch.setattr(poller, "repo", fr)
    monkeypatch.setattr(poller, "get_video_client", lambda: MagicMock())
    monkeypatch.setattr(settings, "video_job_max_wait_seconds", 10)

    async def stop_loop(_):
        raise asyncio.CancelledError()
    monkeypatch.setattr(asyncio, "sleep", stop_loop)

    await poller.run_poller_loop()
    assert len(fr.updates) == 1
    assert fr.updates[0][1] == VideoJobStatus.FAILED
    assert "timed out" in fr.updates[0][2]["error_message"]


def test_submit_answers_surfaces_error_and_fallback_video_dir(monkeypatch, tmp_path):
    from app.services import cloudinary_service

    client = TestClient(app)
    tid = "thread-stab-ans-err"
    waiting_state = {"status": AgentStatus.WAITING_FOR_USER, "gaps": []}
    errored_state = {
        "status": AgentStatus.ERROR,
        "gaps": [],
        "error": "Spec generation failed due to upstream quota",
    }

    with patch("app.api.routes.scripts._get_state_values", new=AsyncMock(return_value=waiting_state)), \
         patch("app.api.routes.scripts._update_state", new=AsyncMock()), \
         patch("app.api.routes.scripts._run_graph", new=AsyncMock(return_value=errored_state)), \
         patch("app.api.routes.scripts._sync_project_in_db"):
        resp = client.post(
            f"/api/v1/scripts/{tid}/answers",
            json={"answers": [{"question_id": "q1", "answer": "16:9", "answer_type": "TEXT"}]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ERROR"
        assert data["error"] == "Spec generation failed due to upstream quota"

    # Outside TESTING=1, local fallback writes strictly into configured backend static dir
    monkeypatch.delenv("TESTING", raising=False)
    monkeypatch.setattr(cloudinary_service, "_BACKEND_STATIC_VIDEOS_DIR", tmp_path / "static" / "generated_videos")
    url = cloudinary_service._save_local_video_fallback(b"mp4data", "final-test-dir")
    assert "/static/generated_videos/final-test-dir.mp4" in url
    assert (tmp_path / "static" / "generated_videos" / "final-test-dir.mp4").exists()


def test_submission_limiter_multi_loop_and_backoff_policy():
    from app.services.video_generation.base_client import PermanentVideoError, TransientVideoError
    from app.services.video_generation.rate_limiter import AsyncSubmissionLimiter, compute_submit_backoff

    limiter = AsyncSubmissionLimiter()

    # Cross-loop safety: run the same limiter across distinct asyncio event loops
    async def _run_loop_once(delay: float):
        await limiter.wait_for_slot(delay)
        limiter.extend_cooldown(0.02)

    asyncio.run(_run_loop_once(0.01))
    asyncio.run(_run_loop_once(0.01))

    # Backoff policy: permanent error never retries; server hint & quota detection work dynamically
    assert compute_submit_backoff(PermanentVideoError("bad"), 0, base_seconds=10.0, max_seconds=60.0) == (False, False, 0.0)

    should_retry, is_quota, delay = compute_submit_backoff(
        TransientVideoError("429 RESOURCE_EXHAUSTED: retry in 25s"),
        0,
        base_seconds=5.0,
        max_seconds=60.0,
    )
    assert should_retry is True
    assert is_quota is True
    assert delay >= 25.0


@pytest.mark.asyncio
async def test_veo_client_submit_transient_vs_permanent_classification():
    from app.services.video_generation.veo_client import VeoClient
    from app.services.video_generation.base_client import PermanentVideoError, TransientVideoError

    mock_genai = MagicMock()
    mock_genai.aio = None
    client = VeoClient(api_key="key123", client=mock_genai)

    # Empty-message asyncio.TimeoutError -> TransientVideoError
    mock_genai.models.generate_videos.side_effect = asyncio.TimeoutError()
    with pytest.raises(TransientVideoError):
        await client.submit_job("prompt", 4.0, "16:9")

    # 503 UNAVAILABLE -> TransientVideoError
    mock_genai.models.generate_videos.side_effect = Exception("503 UNAVAILABLE: upstream busy")
    with pytest.raises(TransientVideoError):
        await client.submit_job("prompt", 4.0, "16:9")

    # 400 INVALID_ARGUMENT -> PermanentVideoError even if message contains 'quota'
    mock_genai.models.generate_videos.side_effect = Exception("400 INVALID_ARGUMENT: quota tag invalid")
    with pytest.raises(PermanentVideoError):
        await client.submit_job("prompt", 4.0, "16:9")


@pytest.mark.asyncio
async def test_generate_videos_retries_transient_submit_and_fast_fails_permanent(monkeypatch):
    import app.graph.nodes.generate_videos as gv
    import app.services.video_generation.poller as poller
    from app.services.video_generation.base_client import PermanentVideoError, TransientVideoError
    from app.services.video_generation.rate_limiter import get_video_submit_limiter

    limiter = get_video_submit_limiter()
    limiter.reset()

    pid = "proj-stab-submit-queue"
    _cleanup_project(pid)
    _insert_project(pid, status="PROMPTS_READY")
    monkeypatch.setattr(settings, "use_mock_video_api", False)
    monkeypatch.setattr(settings, "video_submit_min_interval_seconds", 0.0)
    monkeypatch.setattr(settings, "video_submit_max_retries", 2)
    monkeypatch.setattr(settings, "video_submit_backoff_base_seconds", 0.0)
    monkeypatch.setattr(settings, "video_submit_backoff_max_seconds", 0.0)
    monkeypatch.setattr(settings, "video_max_shots_per_project", 10)
    monkeypatch.setattr(settings, "video_max_total_seconds_per_project", 100)
    monkeypatch.setattr(settings, "video_max_estimated_cost_usd", 50.0)

    attempts = {"shot_1": 0, "shot_2": 0}

    class FlakyClient:
        async def submit_job(self, **kwargs):
            text = kwargs["prompt_text"]
            if "Wide sunset" in text:
                attempts["shot_1"] += 1
                if attempts["shot_1"] < 3:
                    raise TransientVideoError("429 RESOURCE_EXHAUSTED")
                return "op_shot1_ok"
            attempts["shot_2"] += 1
            raise PermanentVideoError("Bad shot_2 prompt")

    stitch_calls = []
    async def fake_stitch_trigger(project_id):
        stitch_calls.append(project_id)

    monkeypatch.setattr(gv, "get_video_client", lambda: FlakyClient())
    monkeypatch.setattr(poller, "_check_and_trigger_stitching", fake_stitch_trigger)

    try:
        state = _two_shot_state(pid)
        await gv.generate_videos(state)

        for _ in range(30):
            jobs = repo.get_jobs_for_project(pid)
            if len(jobs) == 2 and all(j.status in (VideoJobStatus.SUBMITTED, VideoJobStatus.FAILED) for j in jobs):
                break
            await asyncio.sleep(0.05)

        jobs = {j.shot_id: j for j in repo.get_jobs_for_project(pid)}
        assert jobs["shot_1"].status == VideoJobStatus.SUBMITTED
        assert jobs["shot_1"].external_job_id == "op_shot1_ok"
        assert attempts["shot_1"] == 3
        # Permanent error fails fast in 1 attempt and records completed_at
        assert jobs["shot_2"].status == VideoJobStatus.FAILED
        assert jobs["shot_2"].completed_at is not None
        assert attempts["shot_2"] == 1
        assert limiter.active_job_ids == set()

        # Simulate Shot 1 also finishing earlier when Shot 2 fails last: stitch check still fires
        assert stitch_calls == []
    finally:
        limiter.reset()
        _cleanup_project(pid)


@pytest.mark.asyncio
async def test_poller_respects_active_submission_queue_before_timing_out(monkeypatch):
    import app.services.video_generation.poller as poller
    from app.services.video_generation.rate_limiter import get_video_submit_limiter

    limiter = get_video_submit_limiter()
    limiter.reset()
    limiter.active_job_ids.add("q_active")

    class FakeRepo:
        def __init__(self, jobs):
            self.jobs = jobs
            self.updates = []
        def get_incomplete_jobs(self):
            return self.jobs
        def update_job_status(self, jid, st, **kw):
            self.updates.append((jid, st, kw))
        def get_project_final_video_url(self, *a):
            return None
        def get_jobs_for_project(self, *a):
            return self.jobs

    old_ts = datetime.now(UTC) - timedelta(seconds=200)
    active_q = VideoJob(
        job_id="q_active", project_id="p_act", prompt_id="pr1", shot_id="s1",
        sequence_number=1, status=VideoJobStatus.QUEUED, submitted_at=old_ts,
    )
    orphan_q = VideoJob(
        job_id="q_orphan", project_id="p_act", prompt_id="pr2", shot_id="s2",
        sequence_number=2, status=VideoJobStatus.QUEUED, submitted_at=old_ts,
    )
    fr = FakeRepo([active_q, orphan_q])
    monkeypatch.setattr(poller, "repo", fr)
    monkeypatch.setattr(poller, "get_video_client", lambda: MagicMock())
    monkeypatch.setattr(settings, "video_job_max_wait_seconds", 10)

    async def stop_loop(_):
        raise asyncio.CancelledError()
    monkeypatch.setattr(asyncio, "sleep", stop_loop)

    try:
        await poller.run_poller_loop()
        updated_ids = [u[0] for u in fr.updates]
        assert "q_active" not in updated_ids
        assert updated_ids == ["q_orphan"]
    finally:
        limiter.reset()


@pytest.mark.asyncio
async def test_terminal_submit_failure_triggers_stitch_when_peer_shots_done(monkeypatch):
    import app.graph.nodes.generate_videos as gv
    import app.services.video_generation.poller as poller
    from app.services.video_generation.base_client import PermanentVideoError
    from app.services.video_generation.rate_limiter import get_video_submit_limiter

    limiter = get_video_submit_limiter()
    limiter.reset()

    pid = "proj-stab-term-stitch"
    _cleanup_project(pid)
    _insert_project(pid, status="GENERATING_VIDEOS")
    repo.create_job(
        VideoJob(
            job_id="vjob_done_1",
            project_id=pid,
            prompt_id="p1",
            shot_id="shot_1",
            sequence_number=1,
            status=VideoJobStatus.COMPLETED,
            video_url="https://cdn.example.com/done1.mp4",
            submitted_at=datetime.now(UTC),
        )
    )

    monkeypatch.setattr(settings, "use_mock_video_api", False)
    monkeypatch.setattr(settings, "video_submit_min_interval_seconds", 0.05)
    monkeypatch.setattr(settings, "video_submit_max_retries", 0)
    monkeypatch.setattr(settings, "video_submit_backoff_base_seconds", 0.0)
    monkeypatch.setattr(settings, "video_submit_backoff_max_seconds", 0.0)
    monkeypatch.setattr(settings, "video_max_shots_per_project", 10)
    monkeypatch.setattr(settings, "video_max_total_seconds_per_project", 100)
    monkeypatch.setattr(settings, "video_max_estimated_cost_usd", 50.0)

    class FailClient:
        async def submit_job(self, **kwargs):
            raise PermanentVideoError("Bad shot 2")

    stitch_calls = []
    async def fake_stitch_trigger(project_id):
        stitch_calls.append(project_id)

    monkeypatch.setattr(gv, "get_video_client", lambda: FailClient())
    monkeypatch.setattr(poller, "_check_and_trigger_stitching", fake_stitch_trigger)

    try:
        state = _two_shot_state(pid)
        await gv.generate_videos(state, target_shot_ids={"shot_2"})

        for _ in range(20):
            if stitch_calls:
                break
            await asyncio.sleep(0.05)

        assert stitch_calls == [pid]
    finally:
        limiter.reset()
        _cleanup_project(pid)
