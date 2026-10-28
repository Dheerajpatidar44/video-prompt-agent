import io
import pytest
from PIL import Image, ImageDraw
import numpy as np

from app.services.image_analysis_service import ImageAnalysisService, ImageFeatureProfile


def _create_synthetic_image(width=200, height=100, color=(255, 0, 0)) -> bytes:
    """Helper to generate a clean synthetic PNG in memory."""
    img = Image.new("RGB", (width, height), color=color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _create_complex_image(width=300, height=300) -> bytes:
    """Helper to generate a multi-colored image with shapes and text."""
    img = Image.new("RGB", (width, height), color=(20, 30, 60))  # Deep navy
    draw = ImageDraw.Draw(img)
    draw.rectangle([50, 50, 250, 250], fill=(212, 175, 55))  # Gold
    draw.ellipse([80, 80, 220, 220], fill=(255, 255, 255))   # White
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_aspect_ratio_calculations():
    assert ImageAnalysisService._calculate_aspect_ratio_str(1920, 1080) == "16:9"
    assert ImageAnalysisService._calculate_aspect_ratio_str(1080, 1920) == "9:16"
    assert ImageAnalysisService._calculate_aspect_ratio_str(1080, 1080) == "1:1"
    assert ImageAnalysisService._calculate_aspect_ratio_str(800, 600) == "4:3"
    assert ImageAnalysisService._calculate_aspect_ratio_str(0, 100) == "UNKNOWN"


def test_color_extraction_solid_red():
    img_bytes = _create_synthetic_image(150, 150, color=(255, 0, 0))
    dominant_hex, palette, lighting = ImageAnalysisService.extract_colors(img_bytes)
    assert dominant_hex.startswith("#")
    assert lighting in ["LOW_KEY", "BALANCED", "HIGH_KEY"]
    assert len(palette) >= 1


def test_color_extraction_dark_low_key():
    img_bytes = _create_synthetic_image(150, 150, color=(10, 10, 10))
    dominant_hex, palette, lighting = ImageAnalysisService.extract_colors(img_bytes)
    assert lighting == "LOW_KEY"


def test_quality_and_framing():
    img_bytes = _create_complex_image(300, 300)
    profile = ImageAnalysisService.analyze_image_bytes(
        img_bytes, filename="bottle.png", category="product"
    )
    assert profile.width == 300
    assert profile.height == 300
    assert profile.aspect_ratio == "1:1"
    assert profile.is_vertical is False
    assert profile.blur_score > 0
    assert profile.framing_type in ["PRODUCT_ISOLATED", "ENVIRONMENT_OR_PROP", "GENERAL"]
    assert len(profile.phash) > 0
    assert "visual_summary_bullet" in profile.__dict__
    assert "[PRODUCT - bottle.png]" in profile.visual_summary_bullet


def test_phash_computation():
    img = Image.new("RGB", (100, 100), color=(100, 150, 200))
    h1 = ImageAnalysisService.compute_phash(img)
    assert len(h1) > 0

    # Same image produces identical hash
    h2 = ImageAnalysisService.compute_phash(img)
    assert h1 == h2


def test_empty_bytes_handling():
    profile = ImageAnalysisService.analyze_image_bytes(b"", "empty.jpg", "product")
    assert profile.filename == "empty.jpg"
    assert profile.width == 0
    assert profile.height == 0


def test_analyze_batch_duplicate_detection():
    img_bytes = _create_synthetic_image(200, 200, color=(50, 100, 150))
    batch = [
        (img_bytes, "shot_1.png", "character"),
        (img_bytes, "shot_2.png", "character"),
    ]
    results = ImageAnalysisService.analyze_batch(batch)
    assert len(results) == 2
    assert "Visually similar to shot_1.png" in results[1].visual_summary_bullet
