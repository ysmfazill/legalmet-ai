"""Unit tests for the deterministic Pillow usability analyzer (Prompt 3).

These assert the analyzer's *usability* grading behaviour directly, with no HTTP
or database. The score is an image-usability signal only — never a compliance,
legality, or AI-confidence judgement.
"""
from __future__ import annotations

from io import BytesIO

from PIL import Image, ImageDraw

from app.core.enums import ImageQualityGrade, ImageQualityStatus
from app.services.quality.pillow import PillowImageQualityAnalyzer

ANALYZER = PillowImageQualityAnalyzer(min_width=400, min_height=400)


def _detailed_png(size: tuple[int, int] = (800, 600)) -> bytes:
    """A high-contrast, edge-rich image (good usability)."""
    img = Image.new("RGB", size, (245, 245, 245))
    draw = ImageDraw.Draw(img)
    for x in range(0, size[0], 24):
        draw.line([(x, 0), (x, size[1])], fill=(10, 10, 10), width=2)
    for y in range(0, size[1], 24):
        draw.line([(0, y), (size[0], y)], fill=(40, 40, 40), width=2)
    draw.rectangle([40, 40, size[0] - 40, size[1] - 40], outline=(0, 0, 0), width=6)
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


def _flat_png(size: tuple[int, int] = (800, 600)) -> bytes:
    """A uniform grey image (poor usability: no edges, no contrast)."""
    img = Image.new("RGB", size, (128, 128, 128))
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


def _analyze(data: bytes):
    return ANALYZER.analyze(
        image_bytes=data, width=None, height=None, mime_type="image/png", seed="unit"
    )


def test_detailed_image_grades_usable_with_metrics() -> None:
    result = _analyze(_detailed_png())
    assert result.grade in {
        ImageQualityGrade.EXCELLENT,
        ImageQualityGrade.GOOD,
        ImageQualityGrade.ACCEPTABLE,
    }
    assert 0.0 <= result.score <= 1.0
    # Real, camelCase usability breakdown is populated.
    for key in ("width", "height", "sharpness", "contrast", "sharpnessScore"):
        assert key in result.metrics
    assert result.metrics["width"] == 800
    assert result.metrics["height"] == 600


def test_flat_image_scores_lower_than_detailed() -> None:
    flat = _analyze(_flat_png())
    detailed = _analyze(_detailed_png())
    # A featureless image is less usable for label reading than an edge-rich one.
    assert flat.score < detailed.score
    assert flat.metrics["sharpnessScore"] <= detailed.metrics["sharpnessScore"]


def test_below_minimum_resolution_is_rejected() -> None:
    result = _analyze(_detailed_png((200, 200)))
    assert result.grade == ImageQualityGrade.REJECTED
    assert result.status == ImageQualityStatus.LOW_RESOLUTION
    assert result.score < 0.3


def test_corrupt_bytes_are_rejected_not_crashing() -> None:
    result = _analyze(b"definitely not an image" * 8)
    assert result.grade == ImageQualityGrade.REJECTED
    assert result.status == ImageQualityStatus.UNKNOWN
    assert result.score == 0.0


def test_deterministic_same_bytes_same_result() -> None:
    data = _detailed_png()
    first = _analyze(data)
    second = _analyze(data)
    assert first.score == second.score
    assert first.grade == second.grade
    assert first.metrics == second.metrics


def _low_detail_png(size: tuple[int, int] = (1600, 1200)) -> bytes:
    """Large enough to clear the minimum resolution, but featureless — resolution
    lifts it above REJECTED while the absent edges/contrast keep it well below
    ACCEPTABLE, so it lands deterministically in the POOR band."""
    img = Image.new("RGB", size, (128, 128, 128))
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


def test_low_detail_large_image_grades_poor() -> None:
    result = _analyze(_low_detail_png())
    assert result.grade == ImageQualityGrade.POOR
    assert 0.30 <= result.score < 0.50
    # POOR is a usability signal (legible-ish, not good) — never a compliance verdict.
    assert result.score < _analyze(_detailed_png()).score
