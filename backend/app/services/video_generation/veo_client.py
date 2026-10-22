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
            client_kwargs = {
                "vertexai": True,
                "api_key": self._api_key,
            }
            if self.project:
                client_kwargs["project"] = self.project
            if self.location:
                client_kwargs["location"] = self.location
            self._client = genai.Client(**client_kwargs)

    def _normalize_aspect_ratio(self, aspect: str) -> str:
        raw = (aspect or "16:9").strip()
        return {"16:9": "16:9", "9:16": "9:16", "1:1": "1:1"}.get(raw, "16:9")

    async def aclose(self) -> None:
        """Close client if needed."""
        pass

    async def _load_reference_image(self, ref_url: str) -> Optional[types.Image]:
        """Fetch or load image bytes and wrap in types.Image for Veo image-to-video."""
        if not ref_url or not isinstance(ref_url, str):
            return None
        if not ref_url.startswith(("http://", "https://")) and not os.path.exists(ref_url):
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
            elif os.path.exists(ref_url):
                import mimetypes
                mime_type, _ = mimetypes.guess_type(ref_url)
                mime_type = mime_type or "image/jpeg"
                with open(ref_url, "rb") as f:
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

        # 4. Build config
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

        config = types.GenerateVideosConfig(**config_kwargs)

        # 5. Load reference image for Image-to-Video if provided
        veo_image = None
        if reference_image_url:
            veo_image = await self._load_reference_image(reference_image_url)
            if veo_image:
                logger.info(f"Veo Image-to-Video enabled: attached image from {reference_image_url}")

        generate_kwargs: dict[str, Any] = {
            "model": self.model,
            "prompt": prompt_text,
            "config": config,
        }
        if veo_image is not None:
            generate_kwargs["image"] = veo_image

        try:
            if hasattr(self._client, "aio") and hasattr(self._client.aio, "models"):
                operation = await self._client.aio.models.generate_videos(**generate_kwargs)
            else:
                operation = await asyncio.to_thread(
                    self._client.models.generate_videos,
                    **generate_kwargs
                )
        except Exception as exc:
            # Fallback: if job submission failed with image, retry once in text-only mode
            if "image" in generate_kwargs:
                logger.warning(
                    f"Veo job submission with reference image failed ({exc}). "
                    f"Falling back to text-only video generation..."
                )
                generate_kwargs.pop("image", None)
                try:
                    if hasattr(self._client, "aio") and hasattr(self._client.aio, "models"):
                        operation = await self._client.aio.models.generate_videos(**generate_kwargs)
                    else:
                        operation = await asyncio.to_thread(
                            self._client.models.generate_videos,
                            **generate_kwargs
                        )
                except Exception as text_exc:
                    exc = text_exc
                else:
                    operation_name = getattr(operation, "name", None)
                    if operation_name:
                        cost = estimate_clip_cost_usd(duration_seconds, self.resolution, model=self.model)
                        logger.info(
                            f"Submitted Veo job (text-fallback) {operation_name}: {duration}s at {self.resolution} "
                            f"(est. cost ${cost:.2f})"
                        )
                        return operation_name

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

    async def check_status(self, external_job_id: str) -> dict:
        if not external_job_id:
            raise PermanentVideoError("Invalid operation id: must not be empty")

        op_arg = (
            types.GenerateVideosOperation.model_construct(name=external_job_id)
            if isinstance(external_job_id, str)
            else external_job_id
        )

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

        # Check for safety filter block
        return {
            "status": "FAILED",
            "video_url": None,
            "error": "Video generation completed without video (possibly blocked by safety filters)",
            "retryable": False,
        }

    async def download_video(self, video_url: str) -> bytes:
        if video_url in self._video_cache:
            return self._video_cache.pop(video_url)

        op_arg = (
            types.GenerateVideosOperation.model_construct(name=video_url)
            if isinstance(video_url, str)
            else video_url
        )

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
