import pytest
import os
import subprocess
from unittest.mock import patch, MagicMock

from app.schemas.video_job import VideoJob, VideoJobStatus
from app.db import video_jobs_repository as repo
from app.db.database import init_db
from app.prompts.tool_rules import get_tool_rules
from app.services.video_generation.stitcher import (
    _get_clip_duration,
    _trim_clip,
    stitch_project_videos,
)


def test_veo_tool_rules_contain_duration_and_structure_directives():
    """Verify that Veo prompt rules enforce duration blocks and prompt anatomy."""
    rules = get_tool_rules("Veo")
    assert "Veo 3.1 generates clips of exactly 4, 6 or 8 seconds" in rules
    assert "Every shot MUST have duration_seconds of 4, 6 or 8" in rules
    assert "VEO PROMPT FORMULA" in rules
    assert "SINGLE CONTINUOUS MOTION BEAT" in rules


def test_video_job_duration_persistence(tmp_path, monkeypatch):
    """Verify that duration_seconds is properly stored and loaded from SQLite."""
    test_db = str(tmp_path / "test_duration.db")
    monkeypatch.setattr("app.db.database.DB_PATH", test_db)
    init_db()

    job = VideoJob(
        job_id="job_dur_001",
        project_id="proj_dur_001",
        prompt_id="pr_01",
        shot_id="sh_01",
        sequence_number=1,
        status=VideoJobStatus.SUBMITTED,
        duration_seconds=3.5,
    )
    repo.create_job(job)

    loaded = repo.get_job("job_dur_001")
    assert loaded is not None
    assert loaded.duration_seconds == 3.5

    # Update job with a new duration or status
    repo.update_job_status("job_dur_001", VideoJobStatus.COMPLETED, duration_seconds=4.0)
    reloaded = repo.get_job("job_dur_001")
    assert reloaded is not None
    assert reloaded.status == VideoJobStatus.COMPLETED
    assert reloaded.duration_seconds == 4.0


def test_get_clip_duration_with_ffprobe():
    """Verify ffprobe output parser."""
    with patch("app.services.video_generation.stitcher.subprocess.run") as mock_run:
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = b"4.004000\n"
        mock_run.return_value = mock_proc

        dur = _get_clip_duration("dummy.mp4")
        assert dur == 4.004


def test_get_clip_duration_failure_fallback():
    """Verify ffprobe gracefully returns None on failure or missing tool."""
    with patch("app.services.video_generation.stitcher.subprocess.run", side_effect=FileNotFoundError):
        dur = _get_clip_duration("dummy.mp4")
        assert dur is None


def test_trim_clip_calls_ffmpeg_with_duration():
    """Verify _trim_clip passes the planned duration -t argument to ffmpeg."""
    with patch("app.services.video_generation.stitcher.subprocess.run") as mock_run:
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = b""
        mock_proc.stderr = b""
        mock_run.return_value = mock_proc

        _trim_clip("input.mp4", "output.mp4", 2.5)
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert "-t" in cmd
        assert "2.50" in cmd
        assert "input.mp4" in cmd
        assert "output.mp4" in cmd


@pytest.mark.asyncio
async def test_stitch_project_videos_trims_when_planned_duration_is_shorter(monkeypatch):
    """Verify stitcher detects that planned duration (e.g. 2s) is shorter than clip (4s) and trims it."""
    project_id = "test_stitch_trim_proj"

    # Completed job where planned duration is 2.0s, but Veo generated a 4.0s clip
    job = VideoJob(
        job_id="j1",
        project_id=project_id,
        prompt_id="pr1",
        shot_id="sh1",
        sequence_number=1,
        status=VideoJobStatus.COMPLETED,
        video_url="https://mock.cdn/shot1.mp4",
        duration_seconds=2.0,
    )

    monkeypatch.setattr(repo, "get_jobs_for_project", lambda pid: [job])
    monkeypatch.setattr(repo, "set_project_final_video_url", lambda pid, url: None)

    trim_calls = []

    def mock_trim(in_p, out_p, dur):
        trim_calls.append((in_p, out_p, dur))
        # Touch output file
        with open(out_p, "wb") as f:
            f.write(b"trimmed_data")
        m = MagicMock()
        m.returncode = 0
        return m

    monkeypatch.setattr("app.services.video_generation.stitcher._trim_clip", mock_trim)
    # Clip duration probed as 4.0s
    monkeypatch.setattr("app.services.video_generation.stitcher._get_clip_duration", lambda p: 4.0)

    # Patch httpx to write dummy raw clip
    with patch("app.services.video_generation.stitcher.httpx.AsyncClient") as mock_client:
        mock_resp = MagicMock()
        mock_resp.content = b"raw_data_4s"
        mock_resp.raise_for_status = MagicMock()
        mock_client.return_value.__aenter__.return_value.get.return_value = mock_resp

        # Patch ffmpeg concat run
        with patch("app.services.video_generation.stitcher._run_ffmpeg") as mock_ffmpeg:
            mock_proc = MagicMock()
            mock_proc.returncode = 0
            mock_ffmpeg.return_value = mock_proc

            with patch("app.services.video_generation.stitcher.os.path.exists", return_value=True):
                with patch("app.services.video_generation.stitcher.os.path.getsize", return_value=1234):
                    with patch("app.services.video_generation.stitcher.open"):
                        with patch("app.services.cloudinary_service.upload_video", return_value="https://cdn/final.mp4"):
                            final_url = await stitch_project_videos(project_id)
                            assert final_url == "https://cdn/final.mp4"

    # Verify that trim was indeed invoked with 2.0s
    assert len(trim_calls) == 1
    assert trim_calls[0][2] == 2.0


def test_validate_prompt_set_warns_on_sub_4s_veo_shot():
    """Verify that validate_prompt_set flags a warning if a shot is under 4s for Veo."""
    from app.schemas.specification import VideoSpecification, OutputRequirements
    from app.schemas.scene_plan import MasterScenePlan, ScenePlan, ShotPlan, PlanStatus, NarrativeRole
    from app.schemas.generated_prompt import PromptSet, GeneratedPrompt, PromptStatus
    from app.validators.prompt_validation import validate_prompt_set

    spec = VideoSpecification(
        project_id="test_sub4",
        output_requirements=OutputRequirements(duration_seconds=2.0)
    )
    shot = ShotPlan(
        shot_id="sh_1", shot_number=1, scene_id="sc_1",
        start_time=0.0, end_time=2.0, duration_seconds=2.0,
        purpose="intro", subject="hero", action="runs",
    )
    scene = ScenePlan(
        scene_id="sc_1", scene_number=1, title="intro", purpose="intro",
        narrative_role=NarrativeRole.ACTION, start_time=0.0, end_time=2.0, duration_seconds=2.0,
        shots=[shot]
    )
    plan = MasterScenePlan(scenes=[scene], total_duration=2.0, status=PlanStatus.READY)

    prompt = GeneratedPrompt(
        prompt_id="pr_1", scene_id="sc_1", shot_id="sh_1", sequence_number=1,
        duration_seconds=2.0, prompt_text="Hero runs swiftly across the open landscape."
    )
    prompt_set = PromptSet(prompts=[prompt], total_duration=2.0)

    validated = validate_prompt_set(spec, plan, prompt_set, target_tool="Veo")
    # Status should still be READY (warning is non-blocking)
    assert validated.status == PromptStatus.READY
    # Should contain SHOT_DURATION_TOO_SHORT warning issue
    issue_types = [iss.issue_type for iss in validated.validation_issues]
    assert "SHOT_DURATION_TOO_SHORT" in issue_types


def test_detect_duration_from_various_script_phrasings():
    """Verify that ScriptHeuristicService reliably detects duration from various user phrasings."""
    from app.services.script_heuristic_service import ScriptHeuristicService

    test_cases = [
        ("Final video duration 8 sec for commercial ad.", 8.0),
        ("Create an 8-second video of a car.", 8.0),
        ("Target duration: 8s. Aspect ratio: 16:9.", 8.0),
        ("Length: 8 seconds. Hero walking.", 8.0),
        ("Runtime: 8. Landscape format.", 8.0),
        ("Make a 4 second clip.", 4.0),
        ("16s promotional video.", 16.0),
    ]

    for script, expected_dur in test_cases:
        dur, _ = ScriptHeuristicService.detect_duration_and_aspect(script)
        assert dur == expected_dur, f"Failed to extract {expected_dur} from: {script}"


@pytest.mark.asyncio
async def test_generate_scenes_and_prompts_enforces_8s_ceiling():
    """Verify that generate_scenes_and_prompts condenses 4 shots (16s) to 2 shots (8s) when target is 8s."""
    from app.schemas.specification import VideoSpecification, OutputRequirements
    from app.schemas.generation import GenerationResult, GeneratedScenePlan, GeneratedShotPlan, GeneratedPromptItem
    from app.graph.nodes.generate_scenes_and_prompts import generate_scenes_and_prompts

    spec = VideoSpecification(
        project_id="test_8s_guard",
        output_requirements=OutputRequirements(duration_seconds=8)
    )

    # Mock LLM returning 4 shots x 4s = 16s (the exact bug scenario)
    fake_generation_result = GenerationResult(
        total_duration=16,
        scenes=[
            GeneratedScenePlan(
                scene_id="sc_1", scene_number=1, title="Scene 1", purpose="Street",
                narrative_role="ACTION", start_time=0.0, end_time=8.0, duration_seconds=8,
                shots=[
                    GeneratedShotPlan(shot_id="sh_1", shot_number="1", scene_id="sc_1", start_time=0.0, end_time=4.0, duration_seconds=4, purpose="p1", subject="s1", action="a1"),
                    GeneratedShotPlan(shot_id="sh_2", shot_number="2", scene_id="sc_1", start_time=4.0, end_time=8.0, duration_seconds=4, purpose="p2", subject="s2", action="a2"),
                ]
            ),
            GeneratedScenePlan(
                scene_id="sc_2", scene_number=2, title="Scene 2", purpose="Rooftop",
                narrative_role="ACTION", start_time=8.0, end_time=16.0, duration_seconds=8,
                shots=[
                    GeneratedShotPlan(shot_id="sh_3", shot_number="3", scene_id="sc_2", start_time=8.0, end_time=12.0, duration_seconds=4, purpose="p3", subject="s3", action="a3"),
                    GeneratedShotPlan(shot_id="sh_4", shot_number="4", scene_id="sc_2", start_time=12.0, end_time=16.0, duration_seconds=4, purpose="p4", subject="s4", action="a4"),
                ]
            ),
        ],
        prompts=[
            GeneratedPromptItem(prompt_id="pr_1", scene_id="sc_1", shot_id="sh_1", sequence_number=1, duration_seconds=4, prompt_text="Cinematic shot 1"),
            GeneratedPromptItem(prompt_id="pr_2", scene_id="sc_1", shot_id="sh_2", sequence_number=2, duration_seconds=4, prompt_text="Cinematic shot 2"),
            GeneratedPromptItem(prompt_id="pr_3", scene_id="sc_2", shot_id="sh_3", sequence_number=3, duration_seconds=4, prompt_text="Cinematic shot 3"),
            GeneratedPromptItem(prompt_id="pr_4", scene_id="sc_2", shot_id="sh_4", sequence_number=4, duration_seconds=4, prompt_text="Cinematic shot 4"),
        ]
    )

    state = {
        "video_specification": spec,
        "project_id": "test_8s_guard",
        "selected_tool": "Veo",
    }

    with patch("app.graph.nodes.generate_scenes_and_prompts.llm_service.generate_structured", return_value=fake_generation_result):
        out_state = await generate_scenes_and_prompts(state)

    scene_plan = out_state["scene_plan"]
    prompt_set = out_state["prompt_set"]

    # Must be strictly 8 seconds, exactly 2 shots!
    assert scene_plan.total_duration == 8
    assert prompt_set.total_duration == 8
    assert len(prompt_set.prompts) == 2
    assert [p.shot_id for p in prompt_set.prompts] == ["sh_1", "sh_2"]
    assert sum(p.duration_seconds for p in prompt_set.prompts) == 8
