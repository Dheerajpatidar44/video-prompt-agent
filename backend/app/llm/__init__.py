"""Unified LLM Provider Factory and Interfaces.

Exports:
- llm_service: BaseLLMService (Typed singleton proxy for nodes)
- get_llm_service() -> BaseLLMService (Direct factory access)
- close_llm_service() (Lifespan resource cleanup)
- reset_llm_service() (Test fixture cleanup)
- BaseLLMService (Abstract interface)
- LLMException (Unified exception class)
"""
import os
import logging
from typing import Optional, List, Type, TypeVar
from pydantic import BaseModel

from app.core.config import settings
from app.llm.base import BaseLLMService, LLMException

T = TypeVar("T", bound=BaseModel)
logger = logging.getLogger(__name__)

_active_llm_service: Optional[BaseLLMService] = None


def get_llm_service() -> BaseLLMService:
    """Returns the configured LLM service singleton with lazy provider imports.

    Returns:
        BaseLLMService: Instance of GeminiLLMService, ClaudeLLMService, or MockLLMService.
    """
    global _active_llm_service
    if _active_llm_service is not None:
        return _active_llm_service

    # Automated Testing / CI Isolation
    if os.environ.get("TESTING") == "1":
        from app.llm.mock_client import MockLLMService
        _active_llm_service = MockLLMService()
        logger.info("LLM Service initialized: MockLLMService (TESTING=1)")
        return _active_llm_service

    provider = getattr(settings, "llm_provider", "gemini").lower()

    if provider == "claude":
        # Lazy import: Anthropic SDK is loaded ONLY if Claude is explicitly requested
        from app.llm.claude_client import ClaudeLLMService
        _active_llm_service = ClaudeLLMService()
        logger.info(f"LLM Service initialized: ClaudeLLMService (model={settings.anthropic_model})")
    else:
        # Lazy import: Google GenAI SDK
        from app.llm.gemini_client import GeminiLLMService
        _active_llm_service = GeminiLLMService()
        logger.info(
            f"LLM Service initialized: GeminiLLMService (model={settings.gemini_llm_model}, location={settings.gemini_llm_location})"
        )

    return _active_llm_service


async def close_llm_service() -> None:
    """Closes and releases the active LLM service resources."""
    global _active_llm_service
    if _active_llm_service is not None:
        await _active_llm_service.close()
        _active_llm_service = None


def reset_llm_service() -> None:
    """Reset the singleton instance (useful in test fixtures)."""
    global _active_llm_service
    _active_llm_service = None


class _LLMProxy(BaseLLMService):
    """Typed proxy that delegates to get_llm_service() lazily on invocation.
    Provides complete type safety and IDE autocomplete without premature initialization.
    """
    async def generate_structured(
        self,
        prompt: str,
        schema: Type[T],
        *,
        operation: str = "unknown",
        thread_id: str = "",
        max_tokens: Optional[int] = None,
    ) -> T:
        return await get_llm_service().generate_structured(
            prompt, schema, operation=operation, thread_id=thread_id, max_tokens=max_tokens
        )

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
        return await get_llm_service().generate_structured_with_images(
            prompt, image_urls, schema, operation=operation, thread_id=thread_id, max_tokens=max_tokens
        )

    async def close(self) -> None:
        return await close_llm_service()


# Module-level singleton instance for clean node imports
llm_service: BaseLLMService = _LLMProxy()


__all__ = [
    "llm_service",
    "get_llm_service",
    "close_llm_service",
    "reset_llm_service",
    "BaseLLMService",
    "LLMException",
]
