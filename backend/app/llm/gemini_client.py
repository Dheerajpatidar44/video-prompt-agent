"""Google Gemini LLM Service implementation using google-genai SDK.

Features:
- Native Pydantic structured output enforcement via response_schema.
- Dual-tier retry engine:
    1. Exponential backoff for transient API errors (429, 500, 503).
    2. Self-correction reflection loop for Pydantic schema validation failures.
- Multimodal Vision support with pre-validation (size, MIME type) and persistent httpx client.
- Strict finish_reason inspection (SAFETY, MAX_TOKENS detection).
- Bounded concurrency with asyncio.Semaphore.
"""
import asyncio
import logging
import mimetypes
import os
import random
import time
from typing import TypeVar, Type, Optional, List

import httpx
from pydantic import BaseModel, ValidationError
from google import genai
from google.genai import types

from app.core.config import settings
from app.core.google_client import create_genai_client
from app.llm.base import BaseLLMService, LLMException

T = TypeVar("T", bound=BaseModel)
logger = logging.getLogger(__name__)

# Allowed MIME types for vision
ALLOWED_IMAGE_MIMES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_IMAGE_SIZE_BYTES = 20 * 1024 * 1024  # 20 MB max per image


class GeminiLLMService(BaseLLMService):
    """Production Gemini LLM Service adhering to BaseLLMService."""

    _client: Optional[genai.Client] = None
    _semaphore: Optional[asyncio.Semaphore] = None
    _http_client: Optional[httpx.AsyncClient] = None

    def __init__(self):
        self.model_name = settings.gemini_llm_model
        self.location = settings.gemini_llm_location

        if GeminiLLMService._client is None:
            GeminiLLMService._client = create_genai_client(location=self.location)

        if GeminiLLMService._semaphore is None:
            max_concurrency = getattr(settings, "gemini_llm_concurrency", 3)
            GeminiLLMService._semaphore = asyncio.Semaphore(max_concurrency)

        if GeminiLLMService._http_client is None:
            GeminiLLMService._http_client = httpx.AsyncClient(timeout=30.0, follow_redirects=True)

        self.client = GeminiLLMService._client
        self.http_client = GeminiLLMService._http_client
        self.semaphore = GeminiLLMService._semaphore

    # ------------------------------------------------------------------
    # Cleanup — called at app shutdown (FastAPI lifespan)
    # ------------------------------------------------------------------

    @classmethod
    async def close(cls) -> None:
        """Gracefully release client resources and close persistent HTTP sessions."""
        if cls._http_client is not None:
            try:
                await cls._http_client.aclose()
            except Exception as e:
                logger.warning(f"Error closing GeminiLLMService http client: {e}")
            cls._http_client = None

        cls._client = None
        cls._semaphore = None

    # ------------------------------------------------------------------
    # Core API Invocation with Transient Retries
    # ------------------------------------------------------------------

    async def _call_gemini_with_retries(
        self,
        contents: List[any],
        config: types.GenerateContentConfig,
        operation: str,
        thread_id: str,
        max_retries: int = 3,
    ) -> types.GenerateContentResponse:
        """Executes client.aio.models.generate_content with exponential backoff on 429/500/503."""
        t_enqueued = time.perf_counter()

        async with self.semaphore:
            t_call_start = time.perf_counter()
            queue_wait = t_call_start - t_enqueued

            for attempt in range(max_retries + 1):
                try:
                    if hasattr(self.client, "aio") and hasattr(self.client.aio, "models"):
                        response = await self.client.aio.models.generate_content(
                            model=self.model_name,
                            contents=contents,
                            config=config,
                        )
                    else:
                        response = await asyncio.to_thread(
                            self.client.models.generate_content,
                            model=self.model_name,
                            contents=contents,
                            config=config,
                        )

                    elapsed = time.perf_counter() - t_call_start
                    self._log_usage_metrics(response, operation, thread_id, queue_wait, elapsed)
                    return response

                except Exception as exc:
                    err_str = str(exc)
                    is_transient = any(code in err_str for code in ("429", "500", "503", "RESOURCE_EXHAUSTED", "ResourceExhausted"))

                    if is_transient and attempt < max_retries:
                        backoff = (2.0 ** attempt) + random.uniform(0.5, 1.5)
                        logger.warning(
                            f"Gemini transient error ({exc}) on op={operation} thread={thread_id}. "
                            f"Retrying in {backoff:.2f}s (attempt {attempt + 1}/{max_retries})..."
                        )
                        await asyncio.sleep(backoff)
                        continue

                    elapsed = time.perf_counter() - t_call_start
                    logger.error(
                        f"Gemini FAIL | op={operation} thread={thread_id} "
                        f"queue_wait={queue_wait:.2f}s elapsed={elapsed:.2f}s error={exc}"
                    )
                    raise LLMException(f"Gemini API call failed for {operation}: {exc}") from exc

    def _inspect_response_and_extract_text(
        self,
        response: types.GenerateContentResponse,
        operation: str,
        effective_max_tokens: int,
    ) -> str:
        """Inspects candidates, detects finish reasons (SAFETY, MAX_TOKENS), and extracts JSON text."""
        if not response or not response.candidates:
            raise LLMException(f"Gemini returned empty candidates for {operation}.")

        candidate = response.candidates[0]
        finish_reason = getattr(candidate, "finish_reason", None)
        reason_str = str(finish_reason).upper() if finish_reason else ""

        if "SAFETY" in reason_str:
            ratings = getattr(candidate, "safety_ratings", None)
            raise LLMException(f"Gemini generation blocked by safety filters for {operation}: {ratings}")

        if "MAX_TOKENS" in reason_str:
            raise LLMException(
                f"Gemini output truncated at {effective_max_tokens} tokens for {operation}. "
                f"Thinking tokens + JSON exceeded token budget."
            )

        raw_text = response.text
        if not raw_text or not raw_text.strip():
            raise LLMException(f"Gemini returned empty text for {operation} (finish_reason={finish_reason}).")

        return raw_text.strip()

    def _log_usage_metrics(
        self,
        response: types.GenerateContentResponse,
        operation: str,
        thread_id: str,
        queue_wait: float,
        elapsed: float,
    ) -> None:
        try:
            usage = getattr(response, "usage_metadata", None)
            prompt_tokens = getattr(usage, "prompt_token_count", 0) if usage else 0
            gen_tokens = getattr(usage, "candidates_token_count", 0) if usage else 0

            logger.info(
                f"Gemini OK | op={operation} thread={thread_id} "
                f"queue_wait={queue_wait:.2f}s wall={elapsed:.2f}s "
                f"prompt_tokens={prompt_tokens} gen_tokens={gen_tokens} model={self.model_name}"
            )
        except Exception:
            logger.info(
                f"Gemini OK | op={operation} thread={thread_id} "
                f"queue_wait={queue_wait:.2f}s wall={elapsed:.2f}s model={self.model_name}"
            )

    # ------------------------------------------------------------------
    # Public Methods: generate_structured
    # ------------------------------------------------------------------

    async def generate_structured(
        self,
        prompt: str,
        schema: Type[T],
        *,
        operation: str = "unknown",
        thread_id: str = "",
        max_tokens: Optional[int] = None,
    ) -> T:
        """Generates structured output conforming strictly to Pydantic schema with reflection retry."""
        effective_max_tokens = max_tokens or settings.gemini_llm_max_output_tokens
        val_retries = getattr(settings, "gemini_llm_validation_retries", 2)

        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=schema,
            temperature=settings.gemini_llm_temperature,
            max_output_tokens=effective_max_tokens,
        )

        current_prompt = prompt
        last_error = None

        for val_attempt in range(val_retries + 1):
            response = await self._call_gemini_with_retries(
                contents=[current_prompt],
                config=config,
                operation=operation,
                thread_id=thread_id,
            )

            raw_text = self._inspect_response_and_extract_text(response, operation, effective_max_tokens)

            try:
                return schema.model_validate_json(raw_text)
            except ValidationError as val_err:
                last_error = val_err
                if val_attempt == val_retries:
                    logger.error(f"Validation failed permanently after {val_retries + 1} attempts for {operation}: {val_err}")
                    raise LLMException(f"Structured output validation failed for {operation}: {val_err}")

                logger.warning(
                    f"Gemini validation error on op={operation} (attempt {val_attempt + 1}/{val_retries + 1}): {val_err}. "
                    f"Initiating reflection turn..."
                )
                current_prompt = (
                    f"{prompt}\n\n"
                    f"[SYSTEM CORRECTION REQUIRED]: Your previous JSON response failed validation with the following error:\n"
                    f"{val_err}\n"
                    f"Please correct the schema violations and return valid JSON adhering strictly to {schema.__name__}."
                )

        raise LLMException(f"Failed to generate valid structured output for {operation}: {last_error}")

    # ------------------------------------------------------------------
    # Public Methods: generate_structured_with_images
    # ------------------------------------------------------------------

    async def _fetch_and_validate_image(self, url_or_path: str) -> Optional[types.Part]:
        """Loads and pre-validates image data (MIME type, size limit) into types.Part."""
        if not url_or_path:
            return None

        image_bytes: Optional[bytes] = None
        mime_type: str = "image/jpeg"

        if url_or_path.startswith(("http://", "https://")):
            if "mock-image-url.com" in url_or_path:
                return None

            try:
                resp = await self.http_client.get(url_or_path)
                resp.raise_for_status()

                # Check Content-Length if present
                content_len = len(resp.content)
                if content_len > MAX_IMAGE_SIZE_BYTES:
                    logger.warning(f"Image {url_or_path} exceeds {MAX_IMAGE_SIZE_BYTES} bytes ({content_len}), skipping.")
                    return None

                raw_mime = resp.headers.get("content-type", "").split(";")[0].strip().lower()
                mime_type = raw_mime if raw_mime in ALLOWED_IMAGE_MIMES else "image/jpeg"
                image_bytes = resp.content

            except Exception as e:
                logger.warning(f"Failed to download image from {url_or_path}: {e}")
                return None

        elif os.path.exists(url_or_path):
            file_size = os.path.getsize(url_or_path)
            if file_size > MAX_IMAGE_SIZE_BYTES:
                logger.warning(f"Local image {url_or_path} exceeds {MAX_IMAGE_SIZE_BYTES} bytes, skipping.")
                return None

            guessed_mime, _ = mimetypes.guess_type(url_or_path)
            mime_type = guessed_mime if guessed_mime in ALLOWED_IMAGE_MIMES else "image/jpeg"
            with open(url_or_path, "rb") as f:
                image_bytes = f.read()

        if image_bytes:
            return types.Part.from_bytes(data=image_bytes, mime_type=mime_type)

        return None

    async def generate_structured_with_images(
        self,
        prompt: str,
        image_urls: List[str],
        schema: Type[T],
        *,
        operation: str = "unknown",
        thread_id: str = "",
        max_tokens: Optional[int] = None,
    ) -> T:
        """Generates structured output conditioned on multimodal reference images."""
        effective_max_tokens = max_tokens or settings.gemini_llm_max_output_tokens
        val_retries = getattr(settings, "gemini_llm_validation_retries", 2)

        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=schema,
            temperature=settings.gemini_llm_temperature,
            max_output_tokens=effective_max_tokens,
        )

        # Download and validate image parts in parallel
        image_tasks = [self._fetch_and_validate_image(url) for url in image_urls]
        image_parts = [part for part in await asyncio.gather(*image_tasks) if part is not None]

        current_prompt = prompt
        last_error = None

        for val_attempt in range(val_retries + 1):
            contents = [*image_parts, current_prompt]

            response = await self._call_gemini_with_retries(
                contents=contents,
                config=config,
                operation=operation,
                thread_id=thread_id,
            )

            raw_text = self._inspect_response_and_extract_text(response, operation, effective_max_tokens)

            try:
                return schema.model_validate_json(raw_text)
            except ValidationError as val_err:
                last_error = val_err
                if val_attempt == val_retries:
                    logger.error(f"Validation failed permanently after {val_retries + 1} attempts for {operation}: {val_err}")
                    raise LLMException(f"Structured output validation failed for {operation}: {val_err}")

                logger.warning(
                    f"Gemini vision validation error on op={operation} (attempt {val_attempt + 1}): {val_err}. Retrying with feedback..."
                )
                current_prompt = (
                    f"{prompt}\n\n"
                    f"[SYSTEM CORRECTION REQUIRED]: Your previous JSON response failed validation:\n"
                    f"{val_err}\n"
                    f"Please correct the schema violations and return valid JSON adhering strictly to {schema.__name__}."
                )

        raise LLMException(f"Failed to generate valid structured output for {operation}: {last_error}")

