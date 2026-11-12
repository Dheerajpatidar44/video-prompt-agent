"""Tests for Dynamic Visual Asset & Image Generation Layer."""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from app.schemas.generation import VisualAssetRole, ShotImageAssetPlan, GeneratedPromptItem
from app.schemas.generated_prompt import PromptSet, GeneratedPrompt
from app.graph.state import AgentState
from app.graph.nodes.generate_images import generate_images


def test_shot_image_asset_plan_schema():
    """Verify that ShotImageAssetPlan serializes and validates roles properly."""
    asset = ShotImageAssetPlan(
        asset_id="char_lead",
        role=VisualAssetRole.CHARACTER,
        is_master_entity=True,
        generation_prompt="A realistic portrait of a young Indian woman, 16:9",
        aspect_ratio="16:9",
    )
    assert asset.asset_id == "char_lead"
    assert asset.role == VisualAssetRole.CHARACTER
    assert asset.is_master_entity is True

    reuse_asset = ShotImageAssetPlan(
        asset_id="char_lead_shot_2",
        role=VisualAssetRole.CHARACTER,
        reuse_asset_id="char_lead",
    )
    assert reuse_asset.reuse_asset_id == "char_lead"
    assert reuse_asset.generation_prompt is None


@pytest.mark.asyncio
async def test_generate_images_node_mock_mode():
    """Verify generate_images node executes in mock mode without API keys."""
    prompts = [
        GeneratedPrompt(
            prompt_id="p1",
            scene_id="s1",
            shot_id="shot_1",
            sequence_number=1,
            duration_seconds=4.0,
            prompt_text="Cinematic close-up of a smiling young woman.",
            image_assets=[
                {
                    "asset_id": "char_lead",
                    "role": "CHARACTER",
                    "is_master_entity": True,
                    "generation_prompt": "Portrait of young woman",
                }
            ],
        )
    ]
    prompt_set = PromptSet(prompts=prompts, total_duration=4.0)

    state: AgentState = {
        "project_id": "test_proj_123",
        "prompt_set": prompt_set,
        "reference_images": {},
        "master_asset_catalog": {},
        "shot_image_manifest": {},
    }

    result = await generate_images(state)
    assert "shot_image_manifest" in result
    manifest = result["shot_image_manifest"]
    assert "shot_1" in manifest
    assert len(manifest["shot_1"]) >= 1


@pytest.mark.asyncio
async def test_generate_images_respects_use_mock_image_api_true_even_with_key():
    """Verify that when use_mock_image_api=True, NO real image API call is made even if an API key exists."""
    from pydantic import SecretStr
    from app.core.config import settings

    with patch.object(settings, "use_mock_image_api", True), \
         patch.object(settings, "google_api_key", SecretStr("AIzaSyFakeKey123")), \
         patch("app.graph.nodes.generate_images.get_gemini_image_service") as mock_get_svc:

        prompts = [
            GeneratedPrompt(
                prompt_id="p1",
                scene_id="s1",
                shot_id="shot_1",
                sequence_number=1,
                duration_seconds=4.0,
                prompt_text="Cinematic shot",
            )
        ]
        prompt_set = PromptSet(prompts=prompts, total_duration=4.0)

        state: AgentState = {
            "project_id": "test_mock_guard",
            "prompt_set": prompt_set,
        }

        result = await generate_images(state)
        
        # Real image service MUST NOT be retrieved or invoked!
        mock_get_svc.assert_not_called()
        assert "shot_image_manifest" in result
        assert "shot_1" in result["shot_image_manifest"]
        assert result["shot_image_manifest"]["shot_1"][0]["path"].startswith("static/mock_")


