import pytest
from app.services.video_generation.cost import billed_seconds, estimate_clip_cost_usd, estimate_project_cost_usd

def test_billed_seconds():
    assert billed_seconds(1.0) == 2
    assert billed_seconds(2.0) == 2
    assert billed_seconds(2.4) == 3
    assert billed_seconds(7.0000000001) == 7
    assert billed_seconds(45.0) == 30

def test_estimate_clip_cost():
    assert estimate_clip_cost_usd(5.0, "720p") == 0.50
    assert estimate_clip_cost_usd(30.0, "480p") == 1.50
    assert estimate_clip_cost_usd(1.0, "1080p") == 0.40  # 2s min

def test_estimate_project_cost():
    assert estimate_project_cost_usd([1.0, 5.0, 30.0], "720p") == 3.70
