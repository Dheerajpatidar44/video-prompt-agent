"""Cost calculation helpers for video generation (Veo 3.1 Lite).

Veo 3.1 Lite generates clips at fixed durations: 4, 6, or 8 seconds.
1080p supports 8 s only.  A shot planned shorter than 4 s still produces
(and bills) a 4 s clip.  A shot planned longer than 8 s cannot be generated
in one clip — it is capped at 8 s.

Price per second (verify against https://ai.google.dev/gemini-api/docs/pricing#veo-3.1):
  720p  → $0.05/s
  1080p → $0.08/s
"""
import math

# Price per second in USD for Veo 3.1 Lite.
PRICE_PER_SECOND_USD = {"720p": 0.05, "1080p": 0.08}
ALLOWED_DURATIONS = (4, 6, 8)
MAX_CLIP_SECONDS = 8


def billed_seconds(duration_seconds: float, resolution: str = "720p") -> int:
    """Snap a requested duration to a duration Veo 3.1 Lite actually generates (and bills).

    1080p supports 8 s only. Otherwise round UP to 4/6/8; anything above 8 is capped at 8.
    round() first so float noise (6.0000000001) never bumps a clip to the next tier.
    """
    if resolution == "1080p":
        return 8
    d = round(float(duration_seconds), 3)
    for allowed in ALLOWED_DURATIONS:
        if d <= allowed:
            return allowed
    return MAX_CLIP_SECONDS


def exceeds_max_clip(duration_seconds: float) -> bool:
    """Return True if the planned duration is longer than Veo's 8 s maximum."""
    return round(float(duration_seconds), 3) > MAX_CLIP_SECONDS


def estimate_clip_cost_usd(duration_seconds: float, resolution: str = "720p") -> float:
    return round(billed_seconds(duration_seconds, resolution) * PRICE_PER_SECOND_USD[resolution], 4)


def estimate_project_cost_usd(durations: list[float], resolution: str = "720p") -> float:
    return round(sum(estimate_clip_cost_usd(d, resolution) for d in durations), 4)
