import asyncio
import time
import logging
from functools import lru_cache
from typing import TypeVar, Type

import anthropic
from anthropic import AsyncAnthropic
from pydantic import BaseModel

from app.core.config import settings

T = TypeVar("T", bound=BaseModel)
logger = logging.getLogger(__name__)


class LLMException(Exception):
    pass


@lru_cache(maxsize=None)
def _schema_json(schema: Type[BaseModel]) -> dict:
    """model_json_schema() walks the whole pydantic model tree — cache it per
    schema class instead of recomputing it on every single call. Cheap win
    when the same schema (e.g. GeneratedPrompt) is used across many shots."""
    return schema.model_json_schema()


class LLMService:
    """Singleton-pattern async Anthropic Claude service.

    - One shared AsyncAnthropic client reused across all calls.
    - Bounded concurrency via a semaphore so parallel callers don't flood
      the API beyond rate limits.
    - Detailed latency instrumentation on every call, with queue-wait time
      reported separately from actual LLM call time.
    - Uses tool_choice="auto" + an explicit prompt instruction (instead of
      forced tool_choice) so this works on ALL models, including ones like
      Claude Opus 5.5 where extended thinking is always on and forced
      tool_choice ("tool"/"any") is not supported and returns a 400 error.
    """

    _client: AsyncAnthropic | None = None
    _semaphore: asyncio.Semaphore | None = None

    def __init__(self):
        self.model_name = settings.anthropic_model

        if LLMService._client is None:
            LLMService._client = AsyncAnthropic(
                api_key=settings.anthropic_api_key,
                max_retries=3,
                timeout=60.0
            )

        if LLMService._semaphore is None:
            # How many requests to let run concurrently.
            max_concurrency = getattr(settings, "anthropic_max_concurrency", 3)
            LLMService._semaphore = asyncio.Semaphore(max_concurrency)

        self.client = LLMService._client

    # ------------------------------------------------------------------
    # Cleanup — call once at app shutdown (FastAPI lifespan)
    # ------------------------------------------------------------------

    @classmethod
    async def close(cls) -> None:
        if cls._client is not None:
            await cls._client.close()
            cls._client = None

    # ------------------------------------------------------------------
    # Core LLM call — ONE Claude request with instrumentation
    # ------------------------------------------------------------------

    async def generate_structured(
        self,
        prompt: str,
        schema: Type[T],
        *,
        operation: str = "unknown",
        thread_id: str = "",
        max_tokens: int | None = None,
    ) -> T:
        """Single-call structured generation using tool-use with tool_choice
        set to "auto" (not forced). Forced tool_choice ("tool"/"any") is
        rejected by models with always-on extended thinking (e.g. Opus 5.5),
        so we steer the model via an explicit instruction appended to the
        prompt instead — this is compatible with every current model."""

        effective_max_tokens = (
            max_tokens if max_tokens is not None else settings.anthropic_max_tokens
        )
        schema_json = _schema_json(schema)

        # Build tool definition for structured output
        tool_name = "extract_structured_data"
        tools = [
            {
                "name": tool_name,
                "description": f"Extract structured data for {schema.__name__}",
                "input_schema": schema_json,
            }
        ]

        # Explicit instruction to steer the model toward using the tool,
        # since tool_choice is "auto" and doesn't guarantee tool use on its own.
        prompt_with_instruction = (
            f"{prompt}\n\n"
            f"Use the `{tool_name}` tool to provide your complete answer. "
            f"Do not respond with plain text — call the tool with the full result."
        )

        t_enqueued = time.perf_counter()
        async with LLMService._semaphore:
            t_call_start = time.perf_counter()
            queue_wait = t_call_start - t_enqueued
            try:
                response = await self.client.messages.create(
                    model=self.model_name,
                    messages=[{"role": "user", "content": prompt_with_instruction}],
                    max_tokens=effective_max_tokens,
                    tools=tools,
                    tool_choice={"type": "auto"},
                )
            except anthropic.APIStatusError as e:
                elapsed = time.perf_counter() - t_call_start
                logger.error(
                    f"LLM APIStatusError | op={operation} thread={thread_id} "
                    f"queue_wait={queue_wait:.2f}s elapsed={elapsed:.2f}s "
                    f"status_code={e.status_code} error={e}"
                )
                raise LLMException(f"Claude API Status Error: {e.status_code} - {e}")
            except Exception as e:
                elapsed = time.perf_counter() - t_call_start
                logger.error(
                    f"LLM FAIL | op={operation} thread={thread_id} "
                    f"queue_wait={queue_wait:.2f}s elapsed={elapsed:.2f}s error={e}"
                )
                raise LLMException(f"Claude call failed: {e}")

        elapsed = time.perf_counter() - t_call_start

        try:
            prompt_tokens = response.usage.input_tokens
            gen_tokens = response.usage.output_tokens

            logger.info(
                f"LLM OK | op={operation} thread={thread_id} "
                f"queue_wait={queue_wait:.2f}s wall={elapsed:.2f}s "
                f"prompt_tokens={prompt_tokens} gen_tokens={gen_tokens} model={self.model_name}"
            )
        except Exception as metric_err:
            logger.warning(f"Failed to parse LLM metrics, but generation succeeded: {metric_err}")
            logger.info(
                f"LLM OK | op={operation} thread={thread_id} "
                f"queue_wait={queue_wait:.2f}s wall={elapsed:.2f}s model={self.model_name}"
            )

        # Extract tool use content block
        tool_use = next((block for block in response.content if block.type == "tool_use"), None)
        if tool_use is None:
            # With tool_choice="auto", the model isn't forced to call the tool.
            # Log what it returned instead (usually a text block) so a bad
            # prompt/instruction is easy to diagnose rather than a bare failure.
            text_block = next((block for block in response.content if block.type == "text"), None)
            fallback_text = text_block.text[:300] if text_block else "(no text block either)"
            logger.error(
                f"LLM NO_TOOL_USE | op={operation} thread={thread_id} "
                f"stop_reason={response.stop_reason} response_preview={fallback_text!r}"
            )
            raise LLMException(
                f"No tool_use block returned for {operation} "
                f"(stop_reason={response.stop_reason}) — model did not call the tool"
            )

        try:
            return schema.model_validate(tool_use.input)
        except Exception as e:
            raise LLMException(f"Structured output validation failed for {operation}: {e}")


# Module-level singleton — import this wherever you need LLM access.
llm_service = LLMService()