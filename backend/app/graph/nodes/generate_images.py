"""Generate Images node — runs after review_prompts and before generate_videos.

Generates ONE cohesive Master Keyframe image per shot driven entirely by the script:
1. Uses `keyframe_image_prompt` (T=0s static opening frame) as the primary image prompt.
   Falls back to `prompt_text` only when keyframe_image_prompt is absent.
2. Derives aspect ratio dynamically from VideoSpecification — zero hardcoding.
3. Preserves user-uploaded reference images (character / product / brand) via multimodal
   conditioning in GeminiImageService.
4. Locks the first successfully generated keyframe as the visual anchor for subsequent shots
   when no user references were uploaded, maintaining cross-shot continuity.
5. Saves exactly ONE MASTER_KEYFRAME entry per shot into state['shot_image_manifest']
   for Veo image-to-video conditioning.
"""
import asyncio
import logging
from typing import Dict, List, Any, Optional

from app.core.config import settings
from app.graph.state import AgentState
from app.schemas.agent import AgentStatus
from app.utils.aspect_ratio import SUPPORTED_ASPECT_RATIOS, get_spec_aspect_ratio
from app.services.image_generation.gemini_image_service import (
    get_gemini_image_service,
    ImageGenerationError,
)

logger = logging.getLogger(__name__)


def _normalize_asset_url(p: str) -> str:
    """Normalizes a local path or remote URL to a clean web-accessible URL."""
    if not p:
        return ""
    if p.startswith(("http://", "https://")):
        return p
    clean = p.replace("\\", "/").lstrip("/")
    return f"/{clean}"


def _mock_manifest(prompt_set) -> Dict[str, List[Dict[str, Any]]]:
    """Returns a structured mock manifest (no API calls) for mock/CI mode."""
    import os
    manifest: Dict[str, List[Dict[str, Any]]] = {}
    os.makedirs("static", exist_ok=True)
    # Minimal 1x1 transparent PNG bytes to avoid 404 in frontend
    DUMMY_PNG = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\rIDATx\x9cc\xf8\xff\xbf\x01\x00\x05\xfe\x02\xfe\xa76\x81\x84\x00\x00\x00\x00IEND\xaeB`\x82"

    for p in prompt_set.prompts:
        mock_path = f"static/mock_{p.shot_id}_keyframe.png"
        if not os.path.exists(mock_path):
            try:
                with open(mock_path, "wb") as f:
                    f.write(DUMMY_PNG)
            except Exception:
                pass
        manifest[p.shot_id] = [{
            "asset_id": f"{p.shot_id}_keyframe",
            "role": "MASTER_KEYFRAME",
            "path": mock_path,
            "url": _normalize_asset_url(mock_path),
            "reused": False,
        }]
    return manifest


def _phase_one_status(state: AgentState) -> AgentStatus:
    """Preserve ERROR if an upstream node failed; otherwise mark Phase 1 complete."""
    if state.get("status") == AgentStatus.ERROR or state.get("error"):
        return AgentStatus.ERROR
    return AgentStatus.PROMPTS_READY


async def generate_images(state: AgentState) -> AgentState:
    """Generates one cohesive Master Keyframe image per shot, driven by script and user references."""
    prompt_set = state.get("prompt_set")
    spec = state.get("video_specification")
    project_id = state.get("project_id") or "default_project"
    next_status = _phase_one_status(state)

    if not prompt_set or not prompt_set.prompts:
        logger.warning("generate_images: prompt_set is empty, skipping image generation.")
        return {**state, "status": next_status}

    # Guard: mock mode or missing API key → return structured mock manifest, no API calls
    has_api_key = bool(settings.google_api_key and settings.google_api_key.get_secret_value())
    if settings.use_mock_image_api or not has_api_key:
        logger.info(
            f"generate_images: Mock mode active "
            f"(use_mock_image_api={settings.use_mock_image_api}, has_api_key={has_api_key}). "
            "Returning mock keyframe manifest."
        )
        return {
            **state,
            "master_asset_catalog": {},
            "shot_image_manifest": _mock_manifest(prompt_set),
            "status": next_status,
        }

    try:
        image_service = get_gemini_image_service()
    except ImageGenerationError as exc:
        logger.warning(f"generate_images: Image service unavailable ({exc}). Skipping image generation.")
        return {**state, "status": next_status}

    # Derive normalized aspect ratio dynamically from VideoSpecification / PromptSet — never hardcoded
    target_aspect = get_spec_aspect_ratio(
        spec,
        prompt_set,
        fallback=settings.default_aspect_ratio,
        allowed=SUPPORTED_ASPECT_RATIOS,
    )

    # Collect user-uploaded reference image paths by category
    user_refs = state.get("reference_images") or {}
    char_refs: List[str] = user_refs.get("character") or []
    prod_refs: List[str] = user_refs.get("product") or []
    brand_refs: List[str] = user_refs.get("brand") or []

    # Combine all user-uploaded refs (up to 3) for multimodal conditioning
    explicit_user_refs: List[str] = []
    for ref_list in (char_refs, prod_refs, brand_refs):
        explicit_user_refs.extend(ref_list)
    explicit_user_refs = explicit_user_refs[:3]

    # Visual continuity anchor: captures the first generated keyframe when no user refs exist
    master_asset_catalog: Dict[str, str] = dict(state.get("master_asset_catalog") or {})
    shot_manifest: Dict[str, List[Dict[str, Any]]] = {}
    total_shots = len(prompt_set.prompts)

    async def _generate_shot_keyframe(idx: int, prompt_item) -> tuple[str, Optional[str]]:
        shot_id = prompt_item.shot_id
        raw_kf_prompt = getattr(prompt_item, "keyframe_image_prompt", None)
        effective_prompt = (
            raw_kf_prompt if (raw_kf_prompt and raw_kf_prompt.strip())
            else prompt_item.prompt_text
        )

        ref_images_to_use: List[str] = []
        if explicit_user_refs:
            ref_images_to_use = explicit_user_refs
        elif "primary_anchor" in master_asset_catalog:
            ref_images_to_use = [master_asset_catalog["primary_anchor"]]

        filename = f"{project_id}_{shot_id}_keyframe.png"
        logger.info(
            f"generate_images: Shot {idx}/{total_shots} ('{shot_id}') → "
            f"aspect={target_aspect}, refs={len(ref_images_to_use)}, "
            f"using={'keyframe_image_prompt' if raw_kf_prompt else 'prompt_text (fallback)'}"
        )

        saved_path = await image_service.generate_image(
            prompt=effective_prompt,
            aspect_ratio=target_aspect,
            ref_images=ref_images_to_use if ref_images_to_use else None,
            custom_filename=filename,
        )
        return shot_id, saved_path

    def _record_shot(shot_id: str, saved_path: Optional[str]) -> None:
        if not saved_path:
            logger.warning(f"generate_images: Shot '{shot_id}' returned no image; omitting broken manifest entry.")
            return
        shot_manifest[shot_id] = [{
            "asset_id": f"{shot_id}_keyframe",
            "role": "MASTER_KEYFRAME",
            "path": saved_path,
            "url": _normalize_asset_url(saved_path),
            "reused": False,
        }]

    # Step 1: Generate Shot 1 first to establish primary_anchor when no user refs exist
    first_prompt = prompt_set.prompts[0]
    first_shot_id, first_path = await _generate_shot_keyframe(1, first_prompt)
    if first_path and not explicit_user_refs and "primary_anchor" not in master_asset_catalog:
        master_asset_catalog["primary_anchor"] = first_path
        logger.info(
            f"generate_images: Shot '{first_shot_id}' locked as primary visual anchor "
            "for cross-shot continuity."
        )
    _record_shot(first_shot_id, first_path)

    # Step 2: Generate remaining shots concurrently (bounded by image_service._semaphore)
    if total_shots > 1:
        rest_results = await asyncio.gather(
            *[
                _generate_shot_keyframe(idx, prompt_item)
                for idx, prompt_item in enumerate(prompt_set.prompts[1:], start=2)
            ]
        )
        for shot_id, saved_path in rest_results:
            _record_shot(shot_id, saved_path)

    total_resolved = sum(len(items) for items in shot_manifest.values())
    logger.info(
        f"generate_images completed: {total_resolved} master keyframes generated "
        f"across {len(prompt_set.prompts)} shots."
    )

    return {
        **state,
        "master_asset_catalog": master_asset_catalog,
        "shot_image_manifest": shot_manifest,
        "status": next_status,
    }