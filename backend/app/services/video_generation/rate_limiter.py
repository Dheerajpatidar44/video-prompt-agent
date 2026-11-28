"""Event-loop-safe async submission rate limiter and retry backoff policy.

Coordinates spacing between provider API submissions, shared cooldown windows
triggered by rate-limit responses, and bounded exponential backoff without tying
asyncio primitives to a single module-import event loop.
"""
import asyncio
import random
import re
import weakref
from dataclasses import dataclass

from app.services.video_generation.base_client import PermanentVideoError

_QUOTA_ERROR_TERMS = (
    "429",
    "resource_exhausted",
    "rate limit",
    "too many requests",
    "quota",
)

_RETRY_HINT_PATTERN = re.compile(r"retry\s+(?:in|after)\s+(\d+(?:\.\d+)?)\s*s", re.IGNORECASE)


@dataclass
class _LoopRateState:
    lock: asyncio.Lock
    last_request_ts: float = 0.0
    cooldown_until: float = 0.0


class AsyncSubmissionLimiter:
    """Coordinates submission pacing and shared cooldowns per running event loop."""

    def __init__(self) -> None:
        self._loop_states: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, _LoopRateState] = (
            weakref.WeakKeyDictionary()
        )
        self.active_job_ids: set[str] = set()

    def _get_loop_state(self) -> tuple[asyncio.AbstractEventLoop, _LoopRateState]:
        loop = asyncio.get_running_loop()
        state = self._loop_states.get(loop)
        if state is None:
            state = _LoopRateState(lock=asyncio.Lock())
            self._loop_states[loop] = state
        return loop, state

    async def wait_for_slot(self, min_interval: float) -> None:
        """Wait until both shared cooldown and minimum dispatch spacing have elapsed."""
        spacing = max(0.0, float(min_interval or 0.0))
        loop, state = self._get_loop_state()
        async with state.lock:
            while True:
                now = loop.time()
                next_allowed = state.cooldown_until
                if spacing > 0.0 and state.last_request_ts > 0.0:
                    next_allowed = max(next_allowed, state.last_request_ts + spacing)
                if next_allowed <= now:
                    state.last_request_ts = now
                    return
                await asyncio.sleep(next_allowed - now)

    def extend_cooldown(self, delay_seconds: float) -> None:
        """Push the active loop's shared cooldown window forward without holding the lock."""
        delay = max(0.0, float(delay_seconds or 0.0))
        if delay <= 0.0:
            return
        try:
            loop, state = self._get_loop_state()
        except RuntimeError:
            return
        state.cooldown_until = max(state.cooldown_until, loop.time() + delay)

    def reset(self) -> None:
        """Clear all loop rate state and active job tracking (intended for tests)."""
        self._loop_states.clear()
        self.active_job_ids.clear()


def compute_submit_backoff(
    exc: Exception,
    attempt: int,
    *,
    base_seconds: float,
    max_seconds: float,
    jitter_ratio: float = 0.15,
) -> tuple[bool, bool, float]:
    """Return ``(should_retry, is_quota, delay_seconds)`` for a submission error."""
    if isinstance(exc, PermanentVideoError):
        return False, False, 0.0

    err_lower = str(exc).lower()
    is_quota = any(term in err_lower for term in _QUOTA_ERROR_TERMS)

    max_cap = max(0.0, float(max_seconds or 0.0))
    if max_cap <= 0.0:
        return True, is_quota, 0.0

    base = max(0.0, float(base_seconds or 0.0))
    hint_match = _RETRY_HINT_PATTERN.search(err_lower)
    hint_cap = max(max_cap, 120.0)
    server_hint = min(hint_cap, float(hint_match.group(1))) if hint_match else 0.0

    if base <= 0.0:
        return True, is_quota, server_hint

    exp_delay = base * (2 ** max(0, int(attempt)))
    jitter = random.uniform(0.0, max(0.5, exp_delay * jitter_ratio))
    computed = min(max_cap, exp_delay + jitter)
    return True, is_quota, max(computed, server_hint)


_submit_limiter: AsyncSubmissionLimiter | None = None


def get_video_submit_limiter() -> AsyncSubmissionLimiter:
    """Return the process-wide video submission rate limiter."""
    global _submit_limiter
    if _submit_limiter is None:
        _submit_limiter = AsyncSubmissionLimiter()
    return _submit_limiter
