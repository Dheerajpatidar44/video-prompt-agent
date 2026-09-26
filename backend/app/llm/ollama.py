import asyncio
import time
import logging
from functools import lru_cache
from typing import TypeVar, Type

import httpx
import ollama
from pydantic import BaseModel

from app.core.config import settings

T = TypeVar("T", bound=BaseModel)
logger = logging.getLogger(__name__)

# How long to wait before re-attempting a health/model check after a failure.
# Prevents every concurrent request from hammering Ollama with its own check
# while it's down or still starting up.
_CHECK_COOLDOWN_SECONDS = 2.0


class LLMException(Exception):
    pass


@lru_cache(maxsize=None)
def _schema_json(schema: Type[BaseModel]) -> dict:
    """model_json_schema() walks the whole pydantic model tree — cache it per
    schema class instead of recomputing it on every single call. Cheap win
    when the same schema (e.g. GeneratedPrompt) is used across many shots."""
    return schema.model_json_schema()


class LLMService:
    """Singleton-pattern async Ollama service.

    - One shared AsyncClient reused across all calls.
    - Health/model checks cached after first success, with a cooldown on
      failure so concurrent requests don't all re-check at once.
    - Bounded concurrency via a semaphore so parallel callers (e.g. multiple
      scenes generated with asyncio.gather) don't flood Ollama with more
      in-flight requests than the server/GPU can actually run at once.
    - Detailed latency instrumentation on every call, with queue-wait time
      reported separately from actual LLM call time.
    - Configurable keep_alive, num_ctx, num_predict, temperature.
    """

    _client: ollama.AsyncClient | None = None
    _health_client: httpx.AsyncClient | None = None
    _semaphore: asyncio.Semaphore | None = None

    _health_ok: bool = False
    _model_ok: bool = False
    _last_health_check: float = 0.0
    _last_model_check: float = 0.0

    def __init__(self):
        self.base_url = settings.ollama_base_url
        self.model_name = settings.ollama_model

        if LLMService._client is None:
            LLMService._client = ollama.AsyncClient(host=self.base_url)

        if LLMService._health_client is None:
            LLMService._health_client = httpx.AsyncClient(timeout=5.0)

        if LLMService._semaphore is None:
            # How many Ollama requests this process will let run concurrently.
            # Should roughly match OLLAMA_NUM_PARALLEL / what your GPU can hold.
            # Falls back to 2 if not yet added to config.
            max_concurrency = getattr(settings, "ollama_max_concurrency", 2)
            LLMService._semaphore = asyncio.Semaphore(max_concurrency)

        self.client = LLMService._client

    # ------------------------------------------------------------------
    # Cleanup — call once at app shutdown (FastAPI lifespan) so the shared
    # httpx/ollama clients don't leak connections across restarts.
    # ------------------------------------------------------------------

    @classmethod
    async def close(cls) -> None:
        if cls._health_client is not None:
            await cls._health_client.aclose()
            cls._health_client = None
        if cls._client is not None:
            # ollama.AsyncClient wraps an internal httpx client; some versions
            # expose it as ._client, others don't expose a close() at all.
            # Guard defensively so shutdown never crashes on a version diff.
            inner = getattr(cls._client, "_client", None)
            if inner is not None and hasattr(inner, "aclose"):
                await inner.aclose()
            cls._client = None

    # ------------------------------------------------------------------
    # Health / Model checks — merged into as few round trips as possible,
    # cached after success, cooled down after failure, and now logged on
    # failure so a misconfigured base_url/port doesn't fail silently.
    # ------------------------------------------------------------------

    async def check_health(self) -> bool:
        if LLMService._health_ok:
            return True
        now = time.monotonic()
        if now - LLMService._last_health_check < _CHECK_COOLDOWN_SECONDS:
            return False
        LLMService._last_health_check = now
        try:
            resp = await LLMService._health_client.get(f"{self.base_url}/")
            if resp.status_code == 200:
                LLMService._health_ok = True
                return True
            logger.debug(f"check_health: unexpected status {resp.status_code} from {self.base_url}")
            return False
        except Exception as e:
            logger.debug(f"check_health failed against {self.base_url}: {e}")
            return False

    async def check_model(self) -> bool:
        if LLMService._model_ok:
            return True
        now = time.monotonic()
        if now - LLMService._last_model_check < _CHECK_COOLDOWN_SECONDS:
            return False
        LLMService._last_model_check = now
        try:
            resp = await self.client.list()
            # A successful .list() call also proves the server is reachable,
            # so piggyback the health flag off it instead of a second round trip.
            LLMService._health_ok = True
            names = [m["model"] for m in resp.get("models", [])]
            if self.model_name in names or f"{self.model_name}:latest" in names:
                LLMService._model_ok = True
                return True
            logger.debug(f"check_model: '{self.model_name}' not found in installed models: {names}")
            return False
        except Exception as e:
            logger.debug(f"check_model failed: {e}")
            return False

    async def _ensure_ready(self) -> None:
        # check_model() alone proves both "server reachable" and "model present"
        # in one round trip; only fall back to the plain health check if that
        # single call fails, to give a clearer error message.
        if await self.check_model():
            return
        if not await self.check_health():
            raise LLMException("Ollama is not running. Start Ollama and try again.")
        raise LLMException(
            f"Model '{self.model_name}' is not available in Ollama. "
            f"Run: ollama pull {self.model_name}"
        )

    # ------------------------------------------------------------------
    # Optional startup warm-up (call once at app boot)
    # ------------------------------------------------------------------

    async def warmup(self) -> None:
        """Force-load the model at the SAME num_ctx used by real calls —
        a different num_ctx at warm-up time causes Ollama to reload the
        runner on the first real request, defeating the point of warming up."""
        if not settings.ollama_warmup_enabled:
            return
        try:
            logger.info(
                f"Warming up model '{self.model_name}' (num_ctx={settings.ollama_num_ctx})..."
            )
            await self.client.chat(
                model=self.model_name,
                messages=[{"role": "user", "content": "hi"}],
                keep_alive=settings.ollama_keep_alive,
                options={
                    "num_ctx": settings.ollama_num_ctx,
                    "num_predict": 1,
                },
            )
            logger.info("Model warm-up complete.")
        except Exception as e:
            logger.warning(f"Model warm-up failed (non-fatal): {e}")

    # ------------------------------------------------------------------
    # Core LLM call — ONE Ollama request with instrumentation
    # ------------------------------------------------------------------

    async def generate_structured(
        self,
        prompt: str,
        schema: Type[T],
        *,
        operation: str = "unknown",
        thread_id: str = "",
        num_predict: int | None = None,
    ) -> T:
        """Single-call structured generation with full latency logging,
        bounded concurrency, and cached schema serialization.

        Logs queue_wait (time spent waiting for the concurrency semaphore)
        separately from elapsed (the actual Ollama call time), so slow logs
        can be diagnosed correctly — a high queue_wait means you need more
        concurrency headroom (or your hardware is maxed out), not that
        Ollama itself is slow.
        """

        await self._ensure_ready()

        effective_num_predict = (
            num_predict if num_predict is not None else settings.ollama_num_predict
        )
        schema_json = _schema_json(schema)

        t_enqueued = time.perf_counter()
        async with LLMService._semaphore:
            t_call_start = time.perf_counter()
            queue_wait = t_call_start - t_enqueued
            try:
                response = await self.client.chat(
                    model=self.model_name,
                    messages=[{"role": "user", "content": prompt}],
                    format=schema_json,
                    keep_alive=settings.ollama_keep_alive,
                    options={
                        "num_ctx": settings.ollama_num_ctx,
                        "num_predict": effective_num_predict,
                        "temperature": settings.ollama_temperature,
                    },
                )
            except Exception as e:
                elapsed = time.perf_counter() - t_call_start
                logger.error(
                    f"LLM FAIL | op={operation} thread={thread_id} "
                    f"queue_wait={queue_wait:.2f}s elapsed={elapsed:.2f}s error={e}"
                )
                raise LLMException(f"Ollama call failed: {e}")

        elapsed = time.perf_counter() - t_call_start
        content = response["message"]["content"]

        try:    
            total_dur = (response.get("total_duration") or 0) / 1e9
            load_dur = (response.get("load_duration") or 0) / 1e9
            prompt_eval = response.get("prompt_eval_count") or 0
            eval_count = response.get("eval_count") or 0

            logger.info(
                f"LLM OK | op={operation} thread={thread_id} "
                f"queue_wait={queue_wait:.2f}s wall={elapsed:.2f}s "
                f"ollama_total={total_dur:.2f}s load={load_dur:.2f}s "
                f"prompt_tokens={prompt_eval} gen_tokens={eval_count} model={self.model_name}"
            )
        except Exception as metric_err:
            logger.warning(f"Failed to parse LLM metrics, but generation succeeded: {metric_err}")
            logger.info(
                f"LLM OK | op={operation} thread={thread_id} "
                f"queue_wait={queue_wait:.2f}s wall={elapsed:.2f}s model={self.model_name}"
            )

        try:
            return schema.model_validate_json(content)
        except Exception as e:
            raise LLMException(f"Structured output validation failed for {operation}: {e}")


# Module-level singleton — import this wherever you need LLM access.
llm_service = LLMService()