"""Google Veo 3.1 Lite client for video generation using the official google-genai SDK (Vertex AI).

Submits video generation jobs, polls operation status, and returns video bytes
for storage and FFmpeg stitching.
"""
import asyncio
import logging
import math
import os
from typing import Optional, Any

from google import genai
from google.genai import types

from app.services.video_generation.base_client import (
    VideoGenerationClient,
    PermanentVideoError,
    TransientVideoError,
)
from app.services.video_generation.cost import billed_seconds, estimate_clip_cost_usd
from app.utils.aspect_ratio import VEO_SUPPORTED_ASPECT_RATIOS, normalize_aspect_ratio

logger = logging.getLogger(__name__)


class VeoClient(VideoGenerationClient):
    """Client for Google Veo 3.1 text-to-video generation via google-genai."""

    requires_authenticated_download: bool = True

    def __init__(
        self,
        api_key: str,
        model: str = "veo-3.1-fast-generate-001",
        resolution: str = "720p",
        person_generation: str = "",
        negative_prompt_mode: str = "drop",
        max_prompt_tokens: int = 1000,
        project: str = "",
        location: str = "us-central1",
        client: Optional[Any] = None,
    ):
        if not api_key:
            raise PermanentVideoError(
                "GOOGLE_API_KEY is not set. Add it to .env or set USE_MOCK_VIDEO_API=true."
            )

        self._api_key = api_key
        self.model = model
        self.resolution = resolution
        self.person_generation = person_generation
        self.negative_prompt_mode = negative_prompt_mode
        self.max_prompt_tokens = max_prompt_tokens
        self.project = project
        self.location = location or "us-central1"

        self._video_cache: dict[str, bytes] = {}

        if client is not None:
            self._client = client
        else:
            from app.core.google_client import create_genai_client
            self._client = create_genai_client(location=self.location)

    def _normalize_aspect_ratio(self, aspect: str) -> str:
        return normalize_aspect_ratio(
            aspect,
            allowed=VEO_SUPPORTED_ASPECT_RATIOS,
            default="16:9",
        ) or "16:9"

    async def aclose(self) -> None:
        """Close client if needed."""
        pass

    async def _load_reference_image(self, ref_url: str) -> Optional[types.Image]:
        """Fetch or load image bytes and wrap in types.Image for Veo image-to-video."""
        if not ref_url or not isinstance(ref_url, str):
            return None
        resolved_local_path = next((p for p in (ref_url, ref_url.lstrip("/\\"), os.path.join("backend", ref_url.lstrip("/\\")), os.path.abspath(ref_url)) if os.path.exists(p)), None)
        if not ref_url.startswith(("http://", "https://")) and not resolved_local_path:
            return None
        try:
            if ref_url.startswith("http://") or ref_url.startswith("https://"):
                if "mock-image-url.com" in ref_url:
                    logger.info(f"Skipping mock image URL: {ref_url}")
                    return None
                import httpx
                async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as http_client:
                    resp = await http_client.get(ref_url)
                    resp.raise_for_status()
                    image_bytes = resp.content
                    raw_type = resp.headers.get("content-type", "image/jpeg").split(";")[0].strip()
                    mime_type = raw_type if raw_type.startswith("image/") else "image/jpeg"
                    return types.Image(image_bytes=image_bytes, mime_type=mime_type)
            elif resolved_local_path:
                import mimetypes
                mime_type, _ = mimetypes.guess_type(resolved_local_path)
                mime_type = mime_type or "image/jpeg"
                with open(resolved_local_path, "rb") as f:
                    image_bytes = f.read()
                return types.Image(image_bytes=image_bytes, mime_type=mime_type)
            else:
                logger.warning(f"Reference image path not accessible: {ref_url}")
                return None
        except Exception as exc:
            logger.warning(f"Could not load reference image from {ref_url} ({exc}). Proceeding text-only.")
            return None

    async def submit_job(
        self,
        prompt_text: str,
        duration_seconds: float,
        aspect_ratio: str,
        negative_prompt: Optional[str] = None,
        reference_image_url: Optional[str] = None,
        reference_image_urls: Optional[list[str]] = None,
        reference_assets: Optional[list[dict]] = None,
    ) -> str:
        # 1. Duration snapping using billed_seconds
        duration = billed_seconds(duration_seconds, self.resolution)
        if duration != round(duration_seconds):
            logger.info(f"planned {duration_seconds}s → Veo generates {duration}s")
        if round(float(duration_seconds), 3) > 8:
            logger.warning(
                f"shot is longer than Veo's 8 s maximum; it will be {duration} s"
            )

        # 2. Aspect ratio
        aspect = self._normalize_aspect_ratio(aspect_ratio)

        # 3. Token guard
        estimated_tokens = math.ceil(len(prompt_text) / 4)
        if estimated_tokens > self.max_prompt_tokens:
            raise PermanentVideoError(
                f"Prompt is about {estimated_tokens} tokens; Veo accepts at most 1,024. Shorten the prompt."
            )

        # 4. Build base config kwargs
        config_kwargs: dict[str, Any] = {
            "aspect_ratio": aspect,
            "resolution": self.resolution,
            "duration_seconds": duration,
            "number_of_videos": 1,
        }
        if self.person_generation:
            config_kwargs["person_generation"] = self.person_generation
        if negative_prompt and self.negative_prompt_mode == "append":
            config_kwargs["negative_prompt"] = negative_prompt

        # 5. Process reference / keyframe images
        ref_items_to_load = []
        if reference_assets:
            ref_items_to_load = reference_assets[:3]
        elif reference_image_urls:
            ref_items_to_load = [{"path": u, "role": "ENVIRONMENT"} for u in reference_image_urls[:3]]
        elif reference_image_url:
            ref_items_to_load = [{"path": reference_image_url, "role": "CHARACTER"}]

        first_frame_image = None
        additional_ref_objects = []

        for item in ref_items_to_load:
            path = item.get("path")
            role = (item.get("role") or "").upper()
            if path:
                img_obj = await self._load_reference_image(path)
                if img_obj:
                    # The first image (e.g. opening keyframe) becomes the primary I2V starting frame
                    if first_frame_image is None:
                        first_frame_image = img_obj
                    elif hasattr(types, "VideoGenerationReferenceImage"):
                        # Any subsequent images (if multi-asset) are wrapped as reference assets
                        ref_type = "asset"
                        try:
                            ref_img_wrapper = types.VideoGenerationReferenceImage(
                                image=img_obj,
                                reference_type=ref_type,
                            )
                            additional_ref_objects.append(ref_img_wrapper)
                        except Exception as wrap_err:
                            logger.warning(f"Failed to wrap VideoGenerationReferenceImage: {wrap_err}")

        # If additional multi-reference objects were built, attach them directly into GenerateVideosConfig
        if additional_ref_objects:
            config_kwargs["reference_images"] = additional_ref_objects
            logger.info(f"Veo Multi-Reference enabled: attached {len(additional_ref_objects)} extra reference image(s) to config")

        config = types.GenerateVideosConfig(**config_kwargs)

        generate_kwargs: dict[str, Any] = {
            "model": self.model,
            "prompt": prompt_text,
            "config": config,
        }

        # Direct First-Frame Image-to-Video:
        # Pass opening keyframe so Veo animates directly from this frame
        if first_frame_image is not None:
            generate_kwargs["image"] = first_frame_image
            logger.info("Veo Image-to-Video mode enabled: attached first_frame_image successfully.")

        try:
            if hasattr(self._client, "aio") and hasattr(self._client.aio, "models"):
                operation = await self._client.aio.models.generate_videos(**generate_kwargs)
            else:
                operation = await asyncio.to_thread(
                    self._client.models.generate_videos,
                    **generate_kwargs
                )
        except Exception as exc:
            exc_str = str(exc)
            if any(k in exc_str for k in ("401", "403", "PERMISSION_DENIED", "Authentication failed")):
                raise PermanentVideoError(f"Authentication/permission error: {exc}") from exc
            if any(k in exc_str for k in ("429", "RESOURCE_EXHAUSTED", "Rate limited")):
                raise TransientVideoError(f"Rate limited / Quota exhausted: {exc}") from exc
            raise PermanentVideoError(f"Failed to submit Veo job: {exc}") from exc

        operation_name = getattr(operation, "name", None)
        if not operation_name:
            raise PermanentVideoError(f"Missing 'name' in response: {operation}")

        cost = estimate_clip_cost_usd(duration_seconds, self.resolution, model=self.model)
        logger.info(
            f"Submitted Veo job {operation_name}: {duration}s at {self.resolution} "
            f"(est. cost ${cost:.2f})"
        )
        return operation_name

    @staticmethod
    def _build_operation_ref(operation_id: str) -> types.GenerateVideosOperation:
        """Build a GenerateVideosOperation reference by name for status/download lookups."""
        return types.GenerateVideosOperation.model_validate({"name": operation_id})

    async def check_status(self, external_job_id: str) -> dict:
        if not external_job_id:
            raise PermanentVideoError("Invalid operation id: must not be empty")

        op_arg = self._build_operation_ref(external_job_id)

        try:
            if hasattr(self._client, "aio") and hasattr(self._client.aio, "operations"):
                operation = await self._client.aio.operations.get(operation=op_arg)
            else:
                operation = await asyncio.to_thread(
                    self._client.operations.get,
                    op_arg,
                )
        except Exception as exc:
            exc_str = str(exc)
            if "404" in exc_str or "NOT_FOUND" in exc_str:
                raise PermanentVideoError(f"Unknown operation: {external_job_id}") from exc
            if any(k in exc_str for k in ("429", "503", "RESOURCE_EXHAUSTED", "timeout")):
                raise TransientVideoError(f"Transient error polling status: {exc}") from exc
            raise

        done = getattr(operation, "done", False)
        if not done:
            return {"status": "PROCESSING", "video_url": None, "error": None}

        # Check for error in operation
        error_obj = getattr(operation, "error", None)
        if error_obj:
            return {
                "status": "FAILED",
                "video_url": None,
                "error": str(error_obj)[:200],
            }

        # Check for generated videos
        res = getattr(operation, "response", None) or getattr(operation, "result", None)
        videos = getattr(res, "generated_videos", None) if res else None

        if videos and len(videos) > 0:
            vid = videos[0]
            video_obj = getattr(vid, "video", None)
            v_bytes = getattr(video_obj, "video_bytes", None) if video_obj else None
            if v_bytes:
                self._video_cache[external_job_id] = v_bytes
                return {"status": "COMPLETED", "video_url": external_job_id, "error": None}

            uri = getattr(video_obj, "uri", None) if video_obj else None
            if uri:
                return {"status": "COMPLETED", "video_url": uri, "error": None}

        # Check for safety filter block and surface exact RAI filtered reasons
        raw_reasons = getattr(res, "rai_media_filtered_reasons", None) if res else None
        raw_count = getattr(res, "rai_media_filtered_count", None) if res else None
        reasons_list = (
            [str(r) for r in raw_reasons if r]
            if isinstance(raw_reasons, (list, tuple))
            else []
        )
        filtered_count = raw_count if isinstance(raw_count, int) else 0

        if reasons_list or filtered_count > 0:
            logger.warning(
                f"Veo operation {external_job_id} blocked by RAI safety filters "
                f"(filtered_count={filtered_count}): {reasons_list}"
            )

        if reasons_list:
            reasons_joined = "; ".join(reasons_list)
            reasons_lower = reasons_joined.lower()
            is_image_safety = any(
                term in reasons_lower
                for term in (
                    "input image",
                    "celebrity",
                    "likeness",
                    "photorealistic",
                    "image",
                    "face",
                    "15236754",
                    "usage guidelines",
                )
            )
            return {
                "status": "FAILED",
                "video_url": None,
                "error": f"Video generation completed without video (blocked by safety filters: {reasons_joined})",
                "retryable": is_image_safety,
                "image_safety_rejected": is_image_safety,
                "rai_filtered_reasons": reasons_list,
            }

        return {
            "status": "FAILED",
            "video_url": None,
            "error": "Video generation completed without video (possibly blocked by safety filters)",
            "retryable": False,
        }

    async def download_video(self, video_url: str) -> bytes:
        if video_url in self._video_cache:
            return self._video_cache.pop(video_url)

        op_arg = self._build_operation_ref(video_url)

        try:
            if hasattr(self._client, "aio") and hasattr(self._client.aio, "operations"):
                op = await self._client.aio.operations.get(operation=op_arg)
            else:
                op = await asyncio.to_thread(self._client.operations.get, op_arg)
            res = getattr(op, "response", None) or getattr(op, "result", None)
            videos = getattr(res, "generated_videos", None) if res else None
            if videos and len(videos) > 0:
                v_bytes = getattr(videos[0].video, "video_bytes", None)
                if v_bytes:
                    return v_bytes
        except Exception as exc:
            raise PermanentVideoError(f"Failed to retrieve video bytes for {video_url}: {exc}") from exc

        raise PermanentVideoError(f"No video bytes found for operation: {video_url}")
