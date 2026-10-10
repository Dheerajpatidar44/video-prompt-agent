"""Factory for obtaining the active VideoGenerationClient.

Returns the mock client by default (controlled by settings.use_mock_video_api).
Once a real video model is chosen, add a concrete client branch here.

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

    raise NotImplementedError(
        "Real video client not yet configured. Set USE_MOCK_VIDEO_API=true "
        "or implement a real client in client_factory once a video model is chosen."
    )


def reset_video_client() -> None:
    """Clear the cached client instance.

    Intended for use in tests, where each test typically wants a fresh
    MockVideoClient with empty job state rather than one carrying over state
    from a previous test. Not intended to be called from application code.
    """
    global _client_instance
    _client_instance = None