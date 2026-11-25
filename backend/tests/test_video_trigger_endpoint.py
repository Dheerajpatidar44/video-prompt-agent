"""Tests for Human-in-the-Loop video trigger, CAS idempotency, retry, and video-status endpoints."""
from datetime import datetime, UTC
from unittest.mock import AsyncMock, patch
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.db.database import get_db
from app.db import video_jobs_repository as repo
from app.schemas.agent import AgentStatus
from app.schemas.generated_prompt import GeneratedPrompt, PromptSet
from app.schemas.specification import OutputRequirements, VideoSpecification
from app.schemas.video_job import VideoJob, VideoJobStatus


@pytest.fixture
def client():
    return TestClient(app)


def _insert_test_project(project_id: str, status: str = "PROMPTS_READY"):
    conn = get_db()
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO projects (id, title, thread_id, tool, status)
            VALUES (?, ?, ?, ?, ?)
            """,
            (project_id, "Test Project", project_id, "Veo", status),
        )
        conn.commit()
    finally:
        conn.close()


def _cleanup_test_project(project_id: str):
    conn = get_db()
    try:
        conn.execute("DELETE FROM video_jobs WHERE project_id = ?", (project_id,))
        conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        conn.commit()
    finally:
        conn.close()


def _build_phase1_state(project_id: str) -> dict:
    return {
        "project_id": project_id,
        "status": AgentStatus.PROMPTS_READY,
        "video_specification": VideoSpecification(
            project_id=project_id,
            output_requirements=OutputRequirements(duration_seconds=4, aspect_ratio="16:9"),
        ),
        "prompt_set": PromptSet(
            prompts=[
                GeneratedPrompt(
                    prompt_id="p1",
                    scene_id="s1",
                    shot_id="shot_1",
                    sequence_number=1,
                    duration_seconds=4.0,
                    prompt_text="Cinematic shot of a coffee cup on a wooden table.",
                )
            ],
            total_duration=4.0,
        ),
        "shot_image_manifest": {
            "shot_1": [{"asset_id": "shot_1_keyframe", "role": "MASTER_KEYFRAME", "path": "static/mock_shot_1_keyframe.png"}]
        },
    }


def test_video_status_returns_not_started_before_trigger(client):
    pid = "proj-hitl-not-started"
    _cleanup_test_project(pid)
    _insert_test_project(pid, status="PROMPTS_READY")
    try:
        resp = client.get(f"/api/v1/projects/{pid}/video-status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "NOT_STARTED"
        assert data["total_shots"] == 0
        assert data["jobs"] == []
    finally:
        _cleanup_test_project(pid)


def test_video_status_returns_in_progress_when_claimed_but_jobs_empty(client):
    pid = "proj-hitl-claimed-empty"
    _cleanup_test_project(pid)
    _insert_test_project(pid, status="GENERATING_VIDEOS")
    try:
        resp = client.get(f"/api/v1/projects/{pid}/video-status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "IN_PROGRESS"
    finally:
        _cleanup_test_project(pid)


def test_video_status_returns_404_for_unknown_project(client):
    resp = client.get("/api/v1/projects/nonexistent-proj-xyz/video-status")
    assert resp.status_code == 404


def test_trigger_video_generation_and_idempotency(client):
    pid = "proj-hitl-trigger-01"
    _cleanup_test_project(pid)
    _insert_test_project(pid, status="PROMPTS_READY")
    fake_state = _build_phase1_state(pid)

    class FakeVideoClient:
        async def submit_job(self, **kwargs):
            return "ext_job_abc123"

    try:
        with patch("app.api.routes.scripts._get_state_values", new=AsyncMock(return_value=fake_state)), \
             patch("app.api.routes.scripts._update_state", new=AsyncMock()) as mock_update_state, \
             patch("app.graph.nodes.generate_videos.get_video_client", return_value=FakeVideoClient()):

            # 1st click: starts generation and synchronously writes QUEUED job row
            resp1 = client.post(f"/api/v1/projects/{pid}/generate-video")
            assert resp1.status_code == 200
            d1 = resp1.json()
            assert d1["status"] == "GENERATING_VIDEOS"
            assert d1["already_started"] is False
            mock_update_state.assert_awaited_once()
            assert len(repo.get_jobs_for_project(pid)) == 1

            # Verify DB project status transitioned to GENERATING_VIDEOS
            conn = get_db()
            row = conn.execute("SELECT status FROM projects WHERE id = ?", (pid,)).fetchone()
            conn.close()
            assert row["status"] == "GENERATING_VIDEOS"

            # 2nd click (double-click / duplicate call): idempotent, no duplicate jobs
            resp2 = client.post(f"/api/v1/projects/{pid}/generate-video")
            assert resp2.status_code == 200
            d2 = resp2.json()
            assert d2["status"] == "GENERATING_VIDEOS"
            assert d2["already_started"] is True
            assert len(repo.get_jobs_for_project(pid)) == 1
    finally:
        _cleanup_test_project(pid)


def test_trigger_video_generation_allows_retry_when_all_failed(client):
    pid = "proj-hitl-retry-failed"
    _cleanup_test_project(pid)
    _insert_test_project(pid, status="FAILED")
    fake_state = _build_phase1_state(pid)

    repo.create_job(
        VideoJob(
            job_id="vjob_old_failed",
            project_id=pid,
            prompt_id="p1",
            shot_id="shot_1",
            sequence_number=1,
            status=VideoJobStatus.FAILED,
            error_message="Provider timeout",
            submitted_at=datetime.now(UTC),
        )
    )

    class FakeVideoClient:
        async def submit_job(self, **kwargs):
            return "ext_job_retry_ok"

    try:
        with patch("app.api.routes.scripts._get_state_values", new=AsyncMock(return_value=fake_state)), \
             patch("app.api.routes.scripts._update_state", new=AsyncMock()), \
             patch("app.graph.nodes.generate_videos.get_video_client", return_value=FakeVideoClient()):

            resp = client.post(f"/api/v1/projects/{pid}/generate-video")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "GENERATING_VIDEOS"
            assert data["already_started"] is False

            jobs = repo.get_jobs_for_project(pid)
            assert len(jobs) == 1
            assert jobs[0].job_id != "vjob_old_failed"
    finally:
        _cleanup_test_project(pid)


def test_trigger_video_generation_cost_guard_rolls_back_status(client):
    pid = "proj-hitl-cost-guard"
    _cleanup_test_project(pid)
    _insert_test_project(pid, status="PROMPTS_READY")
    fake_state = _build_phase1_state(pid)

    from app.core.config import settings
    try:
        with patch("app.api.routes.scripts._get_state_values", new=AsyncMock(return_value=fake_state)), \
             patch("app.api.routes.scripts._update_state", new=AsyncMock()) as mock_update_state, \
             patch.object(settings, "use_mock_video_api", False), \
             patch.object(settings, "video_max_estimated_cost_usd", 0.01):

            resp = client.post(f"/api/v1/projects/{pid}/generate-video")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "BLOCKED_COST_GUARD"
            assert data["already_started"] is False
            mock_update_state.assert_not_awaited()
            assert repo.get_jobs_for_project(pid) == []

            # DB status rolled back to PROMPTS_READY
            conn = get_db()
            row = conn.execute("SELECT status FROM projects WHERE id = ?", (pid,)).fetchone()
            conn.close()
            assert row["status"] == "PROMPTS_READY"
    finally:
        _cleanup_test_project(pid)


@pytest.mark.asyncio
async def test_poller_marks_project_failed_when_all_jobs_fail():
    pid = "proj-hitl-all-failed"
    _cleanup_test_project(pid)
    _insert_test_project(pid, status="GENERATING_VIDEOS")
    repo.create_job(
        VideoJob(
            job_id="vjob_fail_all_1",
            project_id=pid,
            prompt_id="p1",
            shot_id="shot_1",
            sequence_number=1,
            status=VideoJobStatus.FAILED,
            error_message="Provider failure",
            submitted_at=datetime.now(UTC),
        )
    )
    try:
        from app.services.video_generation.poller import _check_and_trigger_stitching
        await _check_and_trigger_stitching(pid)

        conn = get_db()
        row = conn.execute("SELECT status FROM projects WHERE id = ?", (pid,)).fetchone()
        conn.close()
        assert row["status"] == "FAILED"
    finally:
        _cleanup_test_project(pid)

