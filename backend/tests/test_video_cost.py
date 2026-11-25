import pytest
from app.services.video_generation.cost import (
    billed_seconds,
    estimate_clip_cost_usd,
    estimate_project_cost_usd,
    exceeds_max_clip,
)


def test_billed_seconds():
    # 720p (default)
    assert billed_seconds(1.0) == 4
    assert billed_seconds(2.0) == 4
    assert billed_seconds(3.999) == 4
    assert billed_seconds(4.0) == 4
    assert billed_seconds(4.0000000001) == 4
    assert billed_seconds(4.01) == 6
    assert billed_seconds(5.0) == 6
    assert billed_seconds(6.0) == 6
    assert billed_seconds(6.0000000001) == 6
    assert billed_seconds(6.01) == 8
    assert billed_seconds(7.0) == 8
    assert billed_seconds(8.0) == 8
    assert billed_seconds(9.0) == 8
    assert billed_seconds(15.0) == 8

    # 1080p: supports 4s, 6s, 8s natively just like 720p
    assert billed_seconds(1.0, "1080p") == 4
    assert billed_seconds(4.0, "1080p") == 4
    assert billed_seconds(5.0, "1080p") == 6
    assert billed_seconds(6.0, "1080p") == 6
    assert billed_seconds(8.0, "1080p") == 8
    assert billed_seconds(10.0, "1080p") == 8


def test_exceeds_max_clip():
    assert not exceeds_max_clip(4.0)
    assert not exceeds_max_clip(8.0)
    assert not exceeds_max_clip(8.0000000001)
    assert exceeds_max_clip(8.001)
    assert exceeds_max_clip(10.0)


def test_estimate_clip_cost():
    # 720p: $0.05 / sec
    assert estimate_clip_cost_usd(1.0, "720p") == 0.20  # 4s * 0.05
    assert estimate_clip_cost_usd(4.0, "720p") == 0.20
    assert estimate_clip_cost_usd(5.0, "720p") == 0.30  # 6s * 0.05
    assert estimate_clip_cost_usd(7.0, "720p") == 0.40  # 8s * 0.05
    assert estimate_clip_cost_usd(9.0, "720p") == 0.40  # 8s capped * 0.05

    # 1080p: $0.08 / sec (4s -> $0.32, 6s -> $0.48, 8s -> $0.64)
    assert estimate_clip_cost_usd(1.0, "1080p") == 0.32
    assert estimate_clip_cost_usd(4.0, "1080p") == 0.32
    assert estimate_clip_cost_usd(6.0, "1080p") == 0.48
    assert estimate_clip_cost_usd(8.0, "1080p") == 0.64


def test_estimate_project_cost():
    # 1s (4s -> $0.20), 5s (6s -> $0.30), 7s (8s -> $0.40) -> total $0.90
    assert estimate_project_cost_usd([1.0, 5.0, 7.0], "720p") == 0.90
    # 1080p: (4s + 6s + 8s) * $0.08 = 18 * 0.08 = 1.44
    assert estimate_project_cost_usd([1.0, 5.0, 7.0], "1080p") == 1.44


def test_estimate_fast_model_cost():
    # 720p: $0.10 / sec
    assert estimate_clip_cost_usd(1.0, "720p", model="veo-3.1-fast-generate-001") == 0.40  # 4s * 0.10
    assert estimate_clip_cost_usd(4.0, "720p", model="veo-3.1-fast-generate-001") == 0.40
    assert estimate_clip_cost_usd(5.0, "720p", model="veo-3.1-fast-generate-001") == 0.60  # 6s * 0.10
    assert estimate_clip_cost_usd(7.0, "720p", model="veo-3.1-fast-generate-001") == 0.80  # 8s * 0.10

    # 1080p: $0.15 / sec (4s -> $0.60, 6s -> $0.90, 8s -> $1.20)
    assert estimate_clip_cost_usd(1.0, "1080p", model="veo-3.1-fast-generate-001") == 0.60
    assert estimate_clip_cost_usd(4.0, "1080p", model="veo-3.1-fast-generate-001") == 0.60
    assert estimate_clip_cost_usd(6.0, "1080p", model="veo-3.1-fast-generate-001") == 0.90
    assert estimate_clip_cost_usd(8.0, "1080p", model="veo-3.1-fast-generate-001") == 1.20
    assert estimate_project_cost_usd([4.0, 4.0], "720p", model="veo-3.1-fast-generate-001") == 0.80

