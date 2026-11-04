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

