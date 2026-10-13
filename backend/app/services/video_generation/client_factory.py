"""Factory for obtaining the active VideoGenerationClient.

Returns the mock client by default (controlled by settings.use_mock_video_api).
The real provider is Google Veo 3.1 Lite via the Gemini API.

IMPORTANT: This returns a process-wide singleton. The mock client keeps job
state (submitted job ids, poll counts) in memory, so every caller — the
generate_videos node that submits jobs, and the background poller that checks
their status — must share the exact same client instance. Returning a fresh
instance on every call would give each caller its own empty job registry,
causing "Unknown external job id" errors.
"""
import logging
from app.services.video_generation.base_client import VideoGenerationClient
from app.core.config import settings

logger = logging.getLogger(__name__)

# Module-level cache. Populated lazily on first call, then reused for the
# lifetime of the process.
_client_instance: VideoGenerationClient | None = None


def get_video_client() -> VideoGenerationClient:
    """Return the configured video generation client (process-wide singleton).

    Always returns the same instance within this process once created, so
    callers in different modules (generate_videos node, poller loop, API
    routes) all operate on the same in-memory job state.
    """
    global _client_instance
    if _client_instance is not None:
        return _client_instance

    if settings.use_mock_video_api:
        from app.services.video_generation.mock_client import MockVideoClient
        _client_instance = MockVideoClient()
        logger.info("Video client initialized: MockVideoClient (singleton)")
        return _client_instance
    elif settings.video_provider == "veo":
        from app.services.video_generation.veo_client import VeoClient
        _client_instance = VeoClient(
            api_key=settings.gemini_api_key.get_secret_value(),
            base_url=settings.veo_base_url,
            model=settings.veo_model,
            resolution=settings.veo_resolution,
            person_generation=settings.veo_person_generation,
            negative_prompt_mode=settings.veo_negative_prompt_mode,
            request_timeout=settings.veo_request_timeout_seconds,
            download_timeout=settings.veo_download_timeout_seconds,
            max_prompt_tokens=settings.veo_max_prompt_tokens,
        )
        logger.info("Video client initialized: VeoClient (singleton)")
        return _client_instance
    else:
        raise ValueError(f"Unknown VIDEO_PROVIDER: {settings.video_provider!r} (supported: 'veo')")


def reset_video_client() -> None:
    """Clear the cached client instance.

    Intended for use in tests, where each test typically wants a fresh
    MockVideoClient with empty job state rather than one carrying over state
    from a previous test. Not intended to be called from application code.
    """
    global _client_instance
    _client_instance = None


async def close_video_client() -> None:
    """Close the HTTP client and clear the cache."""
    global _client_instance
    if _client_instance is not None:
        if hasattr(_client_instance, "aclose"):
            await _client_instance.aclose()
        _client_instance = None