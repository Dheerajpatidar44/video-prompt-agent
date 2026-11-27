"""Gemini Image Generation Service using Google GenAI SDK (gemini-3.1-flash-image).

Supports:
1. Pure text-to-image cinematic asset generation.
2. Multimodal image-to-image conditioning using user/master reference images.
"""
import asyncio
import logging
import os
import random
import re
import uuid
from io import BytesIO
from pathlib import Path
from typing import Optional, Union
from PIL import Image

from google import genai
from google.genai import types

from app.core.config import settings
from app.core.google_client import create_genai_client
from app.utils.aspect_ratio import SUPPORTED_ASPECT_RATIOS, normalize_aspect_ratio

logger = logging.getLogger(__name__)

# Injected into every image generation call to prevent multi-panel outputs.
# The image model interprets sequential-action prompts as a comic strip / storyboard;
# this directive counteracts that tendency at the API level.
_ANTI_COLLAGE_SUFFIX = (
    " Composition rule: single unified photographic frame only. "
    "Strictly avoid: collage, split screen, multiple panels, comic strip, "
    "storyboard, grid layout, montage, side-by-side views, subtitles, captions, "
    "speech bubbles, text overlays, borders between images."
)


class ImageGenerationError(Exception):
    """Raised when image generation fails permanently."""
    pass


class GeminiImageService:
    def __init__(
        self,
        api_key: Optional[str] = None,
        model_id: Optional[str] = None,
    ):
        raw_key = api_key or (settings.google_api_key.get_secret_value() if settings.google_api_key else "")
        if not raw_key:
            raise ImageGenerationError("GOOGLE_API_KEY is not set. Add it to .env or environment.")

        self.api_key = raw_key
        self.model_id = model_id or settings.gemini_image_model
        self.output_dir = Path(settings.image_output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        image_location = os.environ.get("GEMINI_IMAGE_LOCATION") or "global"
        self._client = create_genai_client(location=image_location)

        concurrency = max(1, int(getattr(settings, "gemini_image_concurrency_limit", 1) or 1))
        self._semaphore = asyncio.Semaphore(concurrency)
        self._rate_lock = asyncio.Lock()
        self._min_request_interval = max(
            0.0, float(getattr(settings, "gemini_image_min_interval_seconds", 2.0) or 0.0)
        )
        self._last_request_ts: float = 0.0
        self._cooldown_until: float = 0.0

    def _normalize_aspect_ratio(self, aspect: Optional[str]) -> str:
        return normalize_aspect_ratio(
            aspect,
            allowed=SUPPORTED_ASPECT_RATIOS,
            default="16:9",
        ) or "16:9"

    async def _wait_for_rate_limit(self) -> None:
        """Space consecutive image requests cleanly and honor shared 429 cooldowns."""
        async with self._rate_lock:
            loop = asyncio.get_running_loop()
            now = loop.time()
            next_allowed = max(
                self._cooldown_until,
                self._last_request_ts + self._min_request_interval if self._last_request_ts > 0 else 0.0,
            )
            if next_allowed > now:
                await asyncio.sleep(next_allowed - now)
            self._last_request_ts = loop.time()

    @staticmethod
    def _classify_retry_backoff(exc: Exception, attempt: int) -> tuple[bool, bool, float]:
        """Return (should_retry, is_quota, backoff_seconds) for an image API error."""
        err_str = str(exc)
        lower = err_str.lower()

        if any(term in lower for term in ("400", "401", "403", "404", "invalid_argument", "permission_denied", "unauthenticated")):
            return False, False, 0.0

        is_quota = any(
            term in lower
            for term in ("429", "resource_exhausted", "too many requests", "rate limit", "quota")
        )
        if is_quota:
            retry_match = re.search(r"retry\s+(?:in|after)\s+(\d+(?:\.\d+)?)\s*s", lower)
            server_hint = float(retry_match.group(1)) if retry_match else 0.0
            base = min(45.0, 8.0 * (2 ** attempt)) + random.uniform(0.5, 2.0)
            return True, True, max(server_hint, base)

        delay = min(20.0, 2.5 * (attempt + 1)) + random.uniform(0.2, 0.8)
        return True, False, delay

    def _load_pil_image(self, ref_input: Union[bytes, str, Path, Image.Image]) -> Optional[Image.Image]:
        """Loads and returns a PIL Image safely from bytes, file path, or existing Image."""
        try:
            if isinstance(ref_input, Image.Image):
                return ref_input.convert("RGB")
            if isinstance(ref_input, (str, Path)):
                path_str = str(ref_input)
                if path_str.startswith(("http://", "https://")):
                    try:
                        import httpx
                        with httpx.Client(timeout=15.0, follow_redirects=True) as http_client:
                            resp = http_client.get(path_str)
                            resp.raise_for_status()
                            return Image.open(BytesIO(resp.content)).convert("RGB")
                    except Exception as exc:
                        logger.warning(f"Failed to download reference image from {path_str}: {exc}")
                        return None
                if os.path.exists(path_str):
                    return Image.open(path_str).convert("RGB")
                logger.warning(f"Reference image path does not exist on disk: {path_str}")
                return None
            if isinstance(ref_input, bytes):
                return Image.open(BytesIO(ref_input)).convert("RGB")
        except Exception as exc:
            logger.warning(f"Error loading PIL image from {type(ref_input)}: {exc}")
            return None
        return None

    def _call_gemini_sync(
        self,
        contents: list,
        aspect_ratio: str,
    ) -> Optional[bytes]:
        """Synchronous wrapper for client.models.generate_content."""
        config = types.GenerateContentConfig(
            response_modalities=[
                types.Modality.TEXT,
                types.Modality.IMAGE,
            ],
            image_config=types.ImageConfig(
                aspect_ratio=self._normalize_aspect_ratio(aspect_ratio),
                image_size=settings.gemini_image_size,
            ),
        )

        response = self._client.models.generate_content(
            model=self.model_id,
            contents=contents,
            config=config,
        )

        if not response or not response.candidates:
            logger.warning("Gemini Image API returned empty candidates.")
            return None

        for candidate in response.candidates:
            if not candidate.content or not candidate.content.parts:
                finish_reason = getattr(candidate, "finish_reason", None)
                if finish_reason:
                    logger.warning(f"Gemini Image candidate had no parts (finish_reason={finish_reason}).")
                continue
            for part in candidate.content.parts:
                if getattr(part, "inline_data", None) and getattr(part.inline_data, "data", None):
                    return part.inline_data.data
                if getattr(part, "text", None):
                    logger.debug(f"Gemini text remark: {part.text}")

        return None

    async def generate_image(
        self,
        prompt: str,
        aspect_ratio: str = "16:9",
        ref_image: Optional[Union[bytes, str, Path, Image.Image]] = None,
        ref_images: Optional[list[Union[bytes, str, Path, Image.Image]]] = None,
        custom_filename: Optional[str] = None,
        max_retries: int = 5,
    ) -> Optional[str]:
        """Generates an image via Gemini 3.1 Flash Image.

        Args:
            prompt: Visual description of the asset/scene.
            aspect_ratio: '16:9', '9:16', '1:1', etc.
            ref_image: Optional single reference image for visual conditioning.
            ref_images: Optional list of reference images (character/product/style).
            custom_filename: Optional explicit filename (without path).
            max_retries: Number of retry attempts on transient failures.

        Returns:
            Relative/absolute file path string of saved image, or None if failed.
        """
        async with self._semaphore:
            contents = []
            all_refs = []
            if ref_images:
                all_refs.extend(ref_images)
            elif ref_image is not None:
                all_refs.append(ref_image)

            # Load up to 3 reference images safely
            loaded_refs = 0
            for r in all_refs[:3]:
                if r is None:
                    continue
                try:
                    pil_ref = self._load_pil_image(r)
                    if pil_ref:
                        contents.append(pil_ref)
                        loaded_refs += 1
                except Exception as load_err:
                    logger.warning(f"Failed to load reference image ({load_err}), skipping.")

            # Build the final prompt text:
            # 1. If reference images were loaded, prepend a visual-conditioning directive so
            #    the model preserves the subject's identity / product appearance exactly.
            # 2. Always append the anti-collage suffix to prevent multi-panel outputs.
            prompt_parts: list[str] = []
            if loaded_refs > 0:
                prompt_parts.append(
                    "Visual conditioning: strictly preserve the identity, facial features, "
                    "hairstyle, wardrobe, and exact appearance of the subject shown in the "
                    "reference image(s). Do not alter or reinterpret their look."
                )
            prompt_parts.append(prompt)
            final_prompt = " ".join(prompt_parts) + _ANTI_COLLAGE_SUFFIX
            contents.append(final_prompt)

            for attempt in range(max_retries + 1):
                try:
                    await self._wait_for_rate_limit()
                    image_bytes = await asyncio.to_thread(
                        self._call_gemini_sync,
                        contents=contents,
                        aspect_ratio=aspect_ratio,
                    )

                    if not image_bytes:
                        if attempt < max_retries:
                            await asyncio.sleep(1.5)
                            continue
                        logger.warning(f"No image bytes returned for prompt: {prompt[:60]}...")
                        return None

                    filename = custom_filename or f"gen_{uuid.uuid4().hex[:12]}.png"
                    if not filename.endswith((".png", ".jpg", ".jpeg")):
                        filename = f"{filename}.png"

                    save_path = self.output_dir / filename
                    with open(save_path, "wb") as f:
                        f.write(image_bytes)

                    # Return path formatted with forward slashes for URL and file compatibility
                    result_path = str(save_path).replace("\\", "/")
                    logger.info(f"Successfully generated image: {result_path}")
                    return result_path

                except Exception as exc:
                    should_retry, is_quota, backoff = self._classify_retry_backoff(exc, attempt)
                    if should_retry and attempt < max_retries:
                        if is_quota:
                            loop = asyncio.get_running_loop()
                            self._cooldown_until = max(self._cooldown_until, loop.time() + backoff)
                        logger.warning(
                            f"Gemini image generation attempt {attempt + 1}/{max_retries + 1} failed ({exc}). "
                            f"Retrying in {backoff:.1f}s..."
                        )
                        await asyncio.sleep(backoff)
                        continue
                    logger.error(f"Gemini image generation failed permanently for prompt: {prompt[:60]}... Error: {exc}")
                    return None


_image_service_instance: Optional[GeminiImageService] = None


def get_gemini_image_service() -> GeminiImageService:
    """Returns singleton instance of GeminiImageService."""
    global _image_service_instance
    if _image_service_instance is None:
        _image_service_instance = GeminiImageService()
    return _image_service_instance

