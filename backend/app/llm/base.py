"""Base Interface and Exception definitions for LLM Services.

Provides a unified contract for:
- GeminiLLMService (Google GenAI)
- ClaudeLLMService (Anthropic)
- MockLLMService (Testing & CI)
"""
from abc import ABC, abstractmethod
from typing import TypeVar, Type, Optional, List
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMException(Exception):
    """Base exception for all LLM service failures (timeouts, rate limits, schema errors, safety blocks)."""
    pass


class BaseLLMService(ABC):
    """Abstract base class for all LLM providers."""

    @abstractmethod
    async def generate_structured(
        self,
        prompt: str,
        schema: Type[T],
        *,
        system_instruction: Optional[str] = None,
        operation: str = "unknown",
        thread_id: str = "",
        max_tokens: Optional[int] = None,
    ) -> T:
        """Generates structured output adhering strictly to the provided Pydantic schema."""
        pass

    @abstractmethod
    async def generate_structured_with_images(
        self,
        prompt: str,
        image_urls: List[str],
        schema: Type[T],
        *,
        system_instruction: Optional[str] = None,
        operation: str = "unknown",
        thread_id: str = "",
        max_tokens: Optional[int] = None,
    ) -> T:
        """Generates structured output conditioned on multimodal reference images."""
        pass

    @abstractmethod
    async def close(self) -> None:
        """Gracefully release client resources, semaphores, and underlying HTTP clients."""
        pass

