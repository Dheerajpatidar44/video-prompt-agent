"""Tests for end-to-end aspect ratio preservation and image concurrency/429 hardening."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import SecretStr
from PIL import Image
from io import BytesIO

from app.core.config import settings
from app.graph.nodes.build_video_spec import build_video_spec
from app.graph.nodes.generate_images import generate_images
from app.graph.nodes.generate_videos import generate_videos
from app.graph.state import AgentState
from app.schemas.agent import Answer, AnswerType, Gap, GapCategory, GapStatus, Importance
from app.schemas.generated_prompt import GeneratedPrompt, PromptSet
from app.schemas.specification import OutputRequirements, SpecSource, VideoSpecification
from app.services.image_generation.gemini_image_service import GeminiImageService
from app.services.script_heuristic_service import ScriptHeuristicService
from app.utils.aspect_ratio import (
    VEO_SUPPORTED_ASPECT_RATIOS,
    detect_aspect_ratio_from_script,
    normalize_aspect_ratio,
)


def _tiny_png_bytes() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (4, 4), color=(10, 20, 30)).save(buf, format="PNG")
    return buf.getvalue()


def test_script_with_short_and_portrait_prose_does_not_trigger_9_16():
    """Regression test for 5addf911: words like 'short' or 'portrait' must never override explicit 16:9."""
    script = """
    Total video duration: 1 minute
    Aspect ratio: 16:9 for youtube(all shots images , videos in aspect ratio 16:9)
    SHOT 01 | 0:00 - 0:08 (8s)
    Framed center-weighted for 16:9 landscape composition. Close-up portrait of Kabir.
    SHOT 02 | 0:08 - 0:20 (12s)
    Rohan lets out a short, incredulous laugh, recalling the whole story.
    """
    dur, aspect = ScriptHeuristicService.detect_duration_and_aspect(script)
    report = ScriptHeuristicService.scan_script(script)

    assert dur == 60.0
    assert aspect == "16:9"
    assert report.aspect_ratio_hint == "16:9"
    assert report.aspect_ratio_explicit is True


def test_explicit_header_beats_stray_safe_zone_mention():
    """Regression test for 64343cf6: explicit 'Aspect ratio: 16:9' header wins over a stray body mention."""
    script = """
    Aspect ratio: 16:9for youtube(all shots images , videos in aspect ratio 16:9)
    SHOT 02: framed center-weighted for 9:16 safe-zone.
    All Shots and images in Aspect ratio 16:9 for youtube.
    """
    aspect, is_explicit = detect_aspect_ratio_from_script(script)
    assert aspect == "16:9"
    assert is_explicit is True


def test_negated_aspect_and_true_vertical_scripts():
    assert detect_aspect_ratio_from_script(
        "Shoot a 16:9 widescreen ad. Never make it 9:16 vertical."
    ) == ("16:9", True)
    assert detect_aspect_ratio_from_script("Create a YouTube Shorts video about coffee.") == (
        "9:16",
        False,
    )
    assert detect_aspect_ratio_from_script("Compare 16:9 vs 9:16 framing equally.") == (
        None,
        False,
    )


def test_output_requirements_normalizes_aspect_ratio():
    req_land = OutputRequirements(duration_seconds=10, aspect_ratio="16:9 (Landscape)")
    assert req_land.aspect_ratio == "16:9"

    req_port = OutputRequirements(duration_seconds=10, aspect_ratio="9:16 (Portrait)")
    assert req_port.aspect_ratio == "9:16"

    assert OutputRequirements(duration_seconds=10, aspect_ratio=None).aspect_ratio is None
    assert normalize_aspect_ratio("3:4", allowed=VEO_SUPPORTED_ASPECT_RATIOS, default="16:9") == "9:16"
    assert normalize_aspect_ratio("4:3", allowed=VEO_SUPPORTED_ASPECT_RATIOS, default="16:9") == "16:9"


@pytest.mark.asyncio
@patch("app.graph.nodes.build_video_spec.llm_service")
async def test_build_video_spec_enforces_script_16_9_over_hallucinated_llm_and_stale_precheck(mock_llm):
    """Even if LLM output or stale precheck says 9:16, explicit 16:9 in raw script is enforced."""
    wrong_llm_spec = VideoSpecification(
        project_id="proj-ar-1",
        output_requirements=OutputRequirements(duration_seconds=60, aspect_ratio="9:16", orientation="vertical"),
    )
    mock_llm.generate_structured = AsyncMock(return_value=wrong_llm_spec)

    state: AgentState = {
        "project_id": "proj-ar-1",
        "original_script": "Total video duration: 1 minute\nAspect ratio: 16:9 for youtube\nRohan lets out a short laugh.",
        "analysis": {"aspect_ratio": "16:9", "orientation": "horizontal"},
        "script_precheck": {"detected_duration_seconds": 60.0, "aspect_ratio_hint": "9:16"},
        "gaps": [],
        "questions": [],
        "answers": [],
    }

    new_state = await build_video_spec(state)
    spec = new_state["video_specification"]
    assert spec.output_requirements.aspect_ratio == "16:9"
    assert spec.output_requirements.orientation == "horizontal"
    assert spec.output_requirements.source == SpecSource.SCRIPT


@pytest.mark.asyncio
@patch("app.graph.nodes.build_video_spec.llm_service")
async def test_build_video_spec_user_answer_overrides_all(mock_llm):
    """If the user resolves an ASPECT_RATIO gap in Q&A, that ratio wins with SpecSource.USER."""
    wrong_llm_spec = VideoSpecification(
        project_id="proj-ar-2",
        output_requirements=OutputRequirements(duration_seconds=10, aspect_ratio="16:9", orientation="horizontal"),
    )
    mock_llm.generate_structured = AsyncMock(return_value=wrong_llm_spec)

    state: AgentState = {
        "project_id": "proj-ar-2",
        "original_script": "A scenic product showcase video lasting 10 seconds.",
        "analysis": {"aspect_ratio": "16:9", "orientation": "horizontal"},
        "script_precheck": {"detected_duration_seconds": 10.0, "aspect_ratio_hint": None},
        "gaps": [
            Gap(
                id="gap_ar",
                category=GapCategory.ASPECT_RATIO,
                importance=Importance.CRITICAL,
                title="Aspect Ratio",
                description="Target aspect ratio missing",
                evidence="None",
                current_value="9:16 (Portrait)",
                status=GapStatus.RESOLVED,
            )
        ],
        "questions": [],
        "answers": [Answer(question_id="q1", answer="9:16", answer_type=AnswerType.SINGLE_CHOICE)],
    }

    new_state = await build_video_spec(state)
    spec = new_state["video_specification"]
    assert spec.output_requirements.aspect_ratio == "9:16"
    assert spec.output_requirements.orientation == "vertical"
    assert spec.output_requirements.source == SpecSource.USER


@pytest.mark.asyncio
async def test_downstream_images_and_videos_preserve_spec_aspect_ratio():
    spec_vertical = VideoSpecification(
        project_id="proj-ar-3",
        output_requirements=OutputRequirements(duration_seconds=8, aspect_ratio="9:16", orientation="vertical"),
    )
    prompt_set = PromptSet(
        prompts=[
            GeneratedPrompt(
                prompt_id="p1",
                scene_id="s1",
                shot_id="shot_1",
                sequence_number=1,
                duration_seconds=8.0,
                prompt_text="Vertical shot of coffee pour.",
                keyframe_image_prompt="Still frame of coffee cup",
            )
        ],
        total_duration=8.0,
        aspect_ratio="9:16",
    )

    mock_img_svc = MagicMock()
    mock_img_svc.generate_image = AsyncMock(return_value="static/generated_images/out.png")

    with patch.object(settings, "use_mock_image_api", False), \
         patch.object(settings, "google_api_key", SecretStr("fake-key")), \
         patch("app.graph.nodes.generate_images.get_gemini_image_service", return_value=mock_img_svc):
        img_state = await generate_images({
            "project_id": "proj-ar-3",
            "video_specification": spec_vertical,
            "prompt_set": prompt_set,
            "reference_images": {},
        })

    assert mock_img_svc.generate_image.call_args.kwargs["aspect_ratio"] == "9:16"

    mock_video_client = MagicMock()
    mock_video_client.submit_job = AsyncMock(return_value="ext-job-1")

    with patch.object(settings, "use_mock_video_api", True), \
         patch("app.graph.nodes.generate_videos.get_video_client", return_value=mock_video_client), \
         patch("app.graph.nodes.generate_videos.repo.create_job"), \
         patch("app.graph.nodes.generate_videos.repo.update_job_status"):
        await generate_videos({
            **img_state,
            "project_id": "proj-ar-3",
            "video_specification": spec_vertical,
            "prompt_set": prompt_set,
        })
        await asyncio.sleep(0.05)

    assert mock_video_client.submit_job.call_args.kwargs["aspect_ratio"] == "9:16"


@pytest.mark.asyncio
async def test_image_service_serializes_when_concurrency_is_1_and_retries_429(tmp_path):
    sleep_calls = []

    async def fake_sleep(delay: float):
        sleep_calls.append(delay)

    active = 0
    max_active = 0
    attempts_by_prompt = {}
    png = _tiny_png_bytes()

    with patch("app.services.image_generation.gemini_image_service.create_genai_client", return_value=MagicMock()), \
         patch.object(settings, "gemini_image_concurrency_limit", 1), \
         patch.object(settings, "gemini_image_min_interval_seconds", 0.0), \
         patch.object(settings, "image_output_dir", str(tmp_path)), \
         patch.object(settings, "google_api_key", SimpleNamespace(get_secret_value=lambda: "fake-key")), \
         patch("app.services.image_generation.gemini_image_service.asyncio.sleep", side_effect=fake_sleep):
        svc = GeminiImageService(api_key="fake-key")

        def fake_sync(contents, aspect_ratio):
            nonlocal active, max_active
            active += 1
            max_active = max(max_active, active)
            try:
                key = str(contents[-1])[:40]
                attempts_by_prompt[key] = attempts_by_prompt.get(key, 0) + 1
                if attempts_by_prompt[key] <= 2:
                    raise RuntimeError("429 RESOURCE_EXHAUSTED: Resource exhausted.")
                return png
            finally:
                active -= 1

        with patch.object(svc, "_call_gemini_sync", side_effect=fake_sync):
            results = await asyncio.gather(
                svc.generate_image("Shot 1 prompt", aspect_ratio="16:9", custom_filename="s1.png"),
                svc.generate_image("Shot 2 prompt", aspect_ratio="16:9", custom_filename="s2.png"),
            )

    assert max_active == 1
    assert all(r is not None and r.endswith(".png") for r in results)
    # Two 429 retries per shot -> 4 quota backoff sleeps, all >= 8s exponential schedule
    assert len(sleep_calls) >= 4
    assert sleep_calls[0] >= 8.0


@pytest.mark.asyncio
async def test_image_service_fails_fast_on_non_transient_400(tmp_path):
    with patch("app.services.image_generation.gemini_image_service.create_genai_client", return_value=MagicMock()), \
         patch.object(settings, "gemini_image_concurrency_limit", 1), \
         patch.object(settings, "gemini_image_min_interval_seconds", 0.0), \
         patch.object(settings, "image_output_dir", str(tmp_path)), \
         patch.object(settings, "google_api_key", SimpleNamespace(get_secret_value=lambda: "fake-key")):
        svc = GeminiImageService(api_key="fake-key")
        call_count = 0

        def fail_400(contents, aspect_ratio):
            nonlocal call_count
            call_count += 1
            raise RuntimeError("400 INVALID_ARGUMENT: bad aspect")

        with patch.object(svc, "_call_gemini_sync", side_effect=fail_400):
            res = await svc.generate_image("Bad prompt", aspect_ratio="16:9", max_retries=5)

    assert res is None
    assert call_count == 1
