"""Generate Images node — runs after review_prompts and before generate_videos.

Executes script-driven visual asset generation:
1. Dynamically identifies 0 to 3 image assets per shot as planned by LLM.
2. Identifies & locks recurring Master Entities (Character, Product) so they are
   generated only ONCE per project or seeded directly from user reference uploads.
3. Subsequent shots reuse existing master asset paths with zero extra API cost and 100% facial/product consistency.
4. Generates shot-specific environments, action keyframes, and settings.
5. Saves all resolved image paths into state['shot_image_manifest'] for Veo conditioning.
"""
import asyncio
import logging
from typing import Dict, List, Any

from app.core.config import settings
from app.graph.state import AgentState
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


async def generate_images(state: AgentState) -> AgentState:
    """Generates visual assets dynamically for all approved prompts."""
    prompt_set = state.get("prompt_set")
    spec = state.get("video_specification")
    project_id = state.get("project_id") or "default_project"

    if not prompt_set or not prompt_set.prompts:
        logger.warning("generate_images: prompt_set is empty, skipping image generation.")
        return state

    # Check if mock image mode is requested or no API key is available
    has_api_key = bool(settings.google_api_key and settings.google_api_key.get_secret_value())
    if settings.use_mock_image_api or not has_api_key:
        logger.info(
            f"generate_images: Mock image mode active (use_mock_image_api={settings.use_mock_image_api}, "
            f"has_api_key={has_api_key}). Creating structured mock asset manifest without calling real Image API."
        )
        mock_manifest: Dict[str, List[Dict[str, Any]]] = {}
        mock_masters: Dict[str, str] = {}
        for p in prompt_set.prompts:
            shot_assets = getattr(p, "image_assets", []) or []
            manifest_items = []
            if shot_assets:
                for a in shot_assets:
                    a_id = a.get("asset_id") or f"asset_{p.shot_id}"
                    role = a.get("role", "ENVIRONMENT")
                    is_master = a.get("is_master_entity", False)
                    reuse_id = a.get("reuse_asset_id")

                    if reuse_id and reuse_id in mock_masters:
                        manifest_items.append({
                            "asset_id": reuse_id,
                            "role": role,
                            "path": mock_masters[reuse_id],
                            "url": _normalize_asset_url(mock_masters[reuse_id]),
                            "reused": True,
                        })
                    else:
                        m_path = f"static/mock_{a_id}.png"
                        if is_master and a_id not in mock_masters:
                            mock_masters[a_id] = m_path
                        manifest_items.append({
                            "asset_id": a_id,
                            "role": role,
                            "path": m_path,
                            "url": _normalize_asset_url(m_path),
                            "reused": False,
                        })
            else:
                manifest_items.append({
                    "asset_id": f"mock_asset_{p.shot_id}",
                    "role": "ACTION_KEYFRAME",
                    "path": f"static/mock_{p.shot_id}.png",
                    "url": f"/static/mock_{p.shot_id}.png",
                    "reused": False,
                })
            mock_manifest[p.shot_id] = manifest_items

        return {
            **state,
            "master_asset_catalog": mock_masters,
            "shot_image_manifest": mock_manifest,
        }

    try:
        image_service = get_gemini_image_service()
    except ImageGenerationError as exc:
        logger.warning(f"generate_images: Image service unavailable ({exc}). Proceeding without images.")
        return state

    user_refs = state.get("reference_images") or {}
    char_refs = user_refs.get("character") or []
    prod_refs = user_refs.get("product") or []
    brand_refs = user_refs.get("brand") or []

    master_asset_catalog: Dict[str, str] = dict(state.get("master_asset_catalog") or {})
    shot_manifest: Dict[str, List[Dict[str, Any]]] = dict(state.get("shot_image_manifest") or {})

    default_aspect = "16:9"
    if spec and getattr(spec, "output_requirements", None):
        default_aspect = spec.output_requirements.aspect_ratio or "16:9"

    # -------------------------------------------------------------
    # Step 1: Scan and resolve Master Entities (Recurring Assets)
    # -------------------------------------------------------------
    for prompt in prompt_set.prompts:
        assets = getattr(prompt, "image_assets", []) or []
        for asset in assets:
            asset_id = asset.get("asset_id")
            is_master = asset.get("is_master_entity", False)
            gen_prompt = asset.get("generation_prompt")
            ref_cat = asset.get("user_reference_category")

            if is_master and asset_id and asset_id not in master_asset_catalog:
                # Collect all uploaded user reference images for this category
                user_image_paths = []
                if ref_cat == "character" and char_refs:
                    user_image_paths = char_refs
                elif ref_cat == "product" and prod_refs:
                    user_image_paths = prod_refs
                elif ref_cat == "brand" and brand_refs:
                    user_image_paths = brand_refs

                if gen_prompt:
                    logger.info(f"Generating Master Asset '{asset_id}' (Category: {ref_cat}, MultiRef: {len(user_image_paths)})")
                    aspect = asset.get("aspect_ratio") or default_aspect
                    saved_path = await image_service.generate_image(
                        prompt=gen_prompt,
                        aspect_ratio=aspect,
                        ref_image=user_image_paths[0] if user_image_paths else None,
                        ref_images=user_image_paths if user_image_paths else None,
                        custom_filename=f"{project_id}_{asset_id}.png",
                    )
                    if saved_path:
                        master_asset_catalog[asset_id] = saved_path
                elif user_image_paths:
                    # User reference image directly serves as master asset
                    master_asset_catalog[asset_id] = user_image_paths[0]

    # -------------------------------------------------------------
    # Step 2: Resolve Shot-Specific Assets (0 to 3 images per shot)
    # -------------------------------------------------------------
    for prompt in prompt_set.prompts:
        shot_id = prompt.shot_id
        shot_manifest[shot_id] = []
        assets = getattr(prompt, "image_assets", []) or []

        # If LLM didn't plan any assets, reuse existing master entities or fallback cleanly
        if not assets:
            if master_asset_catalog:
                for m_id, m_path in list(master_asset_catalog.items())[:2]:
                    is_char = "char" in m_id.lower()
                    shot_manifest[shot_id].append({
                        "asset_id": m_id,
                        "role": "CHARACTER" if is_char else "PRODUCT",
                        "path": m_path,
                        "url": _normalize_asset_url(m_path),
                        "reused": True,
                    })
            else:
                fallback_prompt = prompt.prompt_text
                logger.info(f"Shot '{shot_id}' has no planned assets. Generating fallback scene keyframe.")
                saved_path = await image_service.generate_image(
                    prompt=fallback_prompt,
                    aspect_ratio=default_aspect,
                    custom_filename=f"{project_id}_{shot_id}_keyframe.png",
                )
                await asyncio.sleep(1.0)
                if saved_path:
                    shot_manifest[shot_id].append({
                        "asset_id": f"{shot_id}_keyframe",
                        "role": "ACTION_KEYFRAME",
                        "path": saved_path,
                        "url": _normalize_asset_url(saved_path),
                        "reused": False,
                    })
            continue

        for asset in assets:
            asset_id = asset.get("asset_id")
            role = asset.get("role", "ENVIRONMENT")
            reuse_id = asset.get("reuse_asset_id")
            gen_prompt = asset.get("generation_prompt")
            aspect = asset.get("aspect_ratio") or default_aspect

            # Case A: Reusing an existing master entity
            target_reuse = reuse_id or (asset_id if asset_id in master_asset_catalog else None)
            if target_reuse and target_reuse in master_asset_catalog:
                cached_path = master_asset_catalog[target_reuse]
                logger.info(f"Shot '{shot_id}': Reusing Master Asset '{target_reuse}' -> {cached_path}")
                shot_manifest[shot_id].append({
                    "asset_id": target_reuse,
                    "role": role,
                    "path": cached_path,
                    "url": _normalize_asset_url(cached_path),
                    "reused": True,
                })
                continue

            # Case B: Fresh shot-specific asset generation (or fallback if master failed)
            effective_prompt = gen_prompt or prompt.prompt_text
            ref_cat = asset.get("user_reference_category")
            user_image_paths = []
            if ref_cat == "character" and char_refs:
                user_image_paths = char_refs
            elif ref_cat == "product" and prod_refs:
                user_image_paths = prod_refs
            elif ref_cat == "brand" and brand_refs:
                user_image_paths = brand_refs

            logger.info(f"Shot '{shot_id}': Generating fresh asset '{asset_id}' (Role: {role})")
            saved_path = await image_service.generate_image(
                prompt=effective_prompt,
                aspect_ratio=aspect,
                ref_image=user_image_paths[0] if user_image_paths else None,
                ref_images=user_image_paths if user_image_paths else None,
                custom_filename=f"{project_id}_{shot_id}_{asset_id}.png",
            )
            await asyncio.sleep(1.0)
            if saved_path:
                shot_manifest[shot_id].append({
                    "asset_id": asset_id,
                    "role": role,
                    "path": saved_path,
                    "url": _normalize_asset_url(saved_path),
                    "reused": False,
                })
                if asset.get("is_master_entity", False) and asset_id:
                    master_asset_catalog[asset_id] = saved_path

    total_images_resolved = sum(len(items) for items in shot_manifest.values())
    logger.info(f"generate_images completed: {len(master_asset_catalog)} master entities locked, {total_images_resolved} total shot references mapped.")

    return {
        **state,
        "master_asset_catalog": master_asset_catalog,
        "shot_image_manifest": shot_manifest,
    }
