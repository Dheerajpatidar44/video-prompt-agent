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
        """Single-call structured generation using forced tool-use."""
        
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
        
        t_enqueued = time.perf_counter()
        async with LLMService._semaphore:
            t_call_start = time.perf_counter()
            queue_wait = t_call_start - t_enqueued
            try:
                response = await self.client.messages.create(
                    model=self.model_name,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=effective_max_tokens,
                    tools=tools,
                    tool_choice={"type": "tool", "name": tool_name}
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
            raise LLMException(f"No tool_use block returned for {operation}")
            
        try:
            return schema.model_validate(tool_use.input)
        except Exception as e:
            raise LLMException(f"Structured output validation failed for {operation}: {e}")


# Module-level singleton — import this wherever you need LLM access.
llm_service = LLMService()
