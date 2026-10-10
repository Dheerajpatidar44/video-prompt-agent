"""Cost calculation helpers for video generation."""
import math

# Price per second in USD for WaveSpeed Wan 3.0 API.
# Must be verified against the official pricing page.
PRICE_PER_SECOND_USD = {"480p": 0.05, "720p": 0.10, "1080p": 0.20}
MIN_BILLED_SECONDS = 2
MAX_BILLED_SECONDS = 30


def billed_seconds(duration_seconds: float) -> int:
    """Provider bills whole seconds, rounded up, clamped to 2-30."""
    # round() first: 7.0000000001 must not become 8.
    return max(MIN_BILLED_SECONDS, min(MAX_BILLED_SECONDS, math.ceil(round(duration_seconds, 3))))


def estimate_clip_cost_usd(duration_seconds: float, resolution: str) -> float:
    return round(billed_seconds(duration_seconds) * PRICE_PER_SECOND_USD[resolution], 4)


def estimate_project_cost_usd(durations: list[float], resolution: str) -> float:
    return round(sum(estimate_clip_cost_usd(d, resolution) for d in durations), 4)
