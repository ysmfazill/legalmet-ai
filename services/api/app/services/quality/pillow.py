"""Deterministic, Pillow-only image *usability* analyzer (Prompt 3).

This computes a real, reproducible **image usability** verdict from the actual
pixels of an uploaded package photo — resolution, sharpness, contrast and
exposure — and maps it onto an :class:`ImageQualityGrade`.

IMPORTANT — what this score is, and is NOT
------------------------------------------
The score and grade express **how usable the image is for a human/machine to
read a label later**. They are explicitly NOT:

* an AI-confidence score,
* a compliance / Legal-Metrology judgement,
* any statement that the package is COMPLIANT, a VIOLATION, or LEGAL.

No OCR, object detection, or rule evaluation happens here. This is pure,
deterministic image statistics via Pillow (no numpy/opencv). Same bytes in →
same result out, so it is safe to assert on in tests and to reason about in the
Evidence Graph as a provenance input.
"""
from __future__ import annotations

from io import BytesIO

from PIL import Image as PILImage
from PIL import ImageFilter, ImageOps, ImageStat

from app.core.enums import ImageQualityGrade, ImageQualityStatus
from app.services.interfaces import ImageQualityAnalyzer, ImageQualityResult

# Stats are computed on a bounded copy so cost is independent of input size.
_STATS_MAX_DIM = 1024

# Normalisation constants (empirical, deterministic — not learned parameters).
_CONTRAST_FULL = 72.0        # 8-bit std-dev treated as "full" tonal spread.
_SHARPNESS_FULL = 34.0       # FIND_EDGES std-dev treated as "crisp".
_IDEAL_BRIGHTNESS = 0.55     # Mid-bright luminance reads best for labels.

# Grade thresholds on the overall usability score (0..1).
_GRADE_BANDS = (
    (0.85, ImageQualityGrade.EXCELLENT),
    (0.70, ImageQualityGrade.GOOD),
    (0.50, ImageQualityGrade.ACCEPTABLE),
    (0.30, ImageQualityGrade.POOR),
)


def _clamp01(value: float) -> float:
    return 0.0 if value < 0 else 1.0 if value > 1 else value


class PillowImageQualityAnalyzer(ImageQualityAnalyzer):
    """Real usability grading for the intake pipeline (deterministic)."""

    def __init__(self, *, min_width: int = 400, min_height: int = 400) -> None:
        self._min_width = min_width
        self._min_height = min_height

    def analyze(
        self,
        *,
        image_bytes: bytes | None,
        width: int | None,
        height: int | None,
        mime_type: str,
        seed: str,
    ) -> ImageQualityResult:
        if not image_bytes:
            # Intake always supplies bytes; guard defensively for other callers.
            return ImageQualityResult(
                status=ImageQualityStatus.UNKNOWN,
                score=0.0,
                notes="No image bytes were provided for usability analysis.",
                grade=ImageQualityGrade.REJECTED,
                metrics={},
            )

        try:
            with PILImage.open(BytesIO(image_bytes)) as opened:
                oriented = ImageOps.exif_transpose(opened)
                actual_w, actual_h = oriented.size
                gray = oriented.convert("L")
                small = gray.copy()
                small.thumbnail((_STATS_MAX_DIM, _STATS_MAX_DIM))
                lum = ImageStat.Stat(small)
                brightness = lum.mean[0] / 255.0
                contrast_std = lum.stddev[0]
                edges = small.filter(ImageFilter.FIND_EDGES)
                sharpness_std = ImageStat.Stat(edges).stddev[0]
        except (OSError, ValueError, SyntaxError):
            # Corrupt/truncated/undecodable bytes — not a usable image.
            return ImageQualityResult(
                status=ImageQualityStatus.UNKNOWN,
                score=0.0,
                notes="Image could not be decoded for usability analysis.",
                grade=ImageQualityGrade.REJECTED,
                metrics={},
            )

        min_dim = min(actual_w, actual_h)

        # Component usability scores (each 0..1). These describe legibility
        # potential only — never legal conformity.
        resolution_score = _clamp01(min_dim / 1600.0)
        contrast_score = _clamp01(contrast_std / _CONTRAST_FULL)
        sharpness_score = _clamp01(sharpness_std / _SHARPNESS_FULL)
        brightness_score = _clamp01(
            1.0 - abs(brightness - _IDEAL_BRIGHTNESS) / _IDEAL_BRIGHTNESS
        )

        overall = round(
            0.35 * resolution_score
            + 0.30 * sharpness_score
            + 0.20 * contrast_score
            + 0.15 * brightness_score,
            3,
        )

        metrics = {
            "width": actual_w,
            "height": actual_h,
            "megapixels": round(actual_w * actual_h / 1_000_000, 3),
            "minDimension": min_dim,
            "brightness": round(brightness, 3),
            "contrast": round(contrast_std, 2),
            "sharpness": round(sharpness_std, 2),
            "resolutionScore": round(resolution_score, 3),
            "sharpnessScore": round(sharpness_score, 3),
            "contrastScore": round(contrast_score, 3),
            "brightnessScore": round(brightness_score, 3),
        }

        # Below the configured minimum resolution the image is unusable for
        # label reading regardless of other qualities: reject outright.
        if actual_w < self._min_width or actual_h < self._min_height:
            metrics["rejectedReason"] = "LOW_RESOLUTION"
            return ImageQualityResult(
                status=ImageQualityStatus.LOW_RESOLUTION,
                score=min(overall, 0.29),
                notes=(
                    f"Resolution {actual_w}x{actual_h}px is below the usable minimum "
                    f"({self._min_width}x{self._min_height}px). Usability only — not a "
                    "compliance judgement."
                ),
                grade=ImageQualityGrade.REJECTED,
                metrics=metrics,
            )

        grade = ImageQualityGrade.REJECTED
        for threshold, banded in _GRADE_BANDS:
            if overall >= threshold:
                grade = banded
                break

        status = self._legacy_status(
            grade=grade,
            sharpness_score=sharpness_score,
            contrast_score=contrast_score,
            brightness=brightness,
        )

        return ImageQualityResult(
            status=status,
            score=overall,
            notes=(
                f"Usability grade {grade.value} (score {overall:.2f}). This reflects image "
                "legibility only — NOT compliance, legality, or AI confidence."
            ),
            grade=grade,
            metrics=metrics,
        )

    @staticmethod
    def _legacy_status(
        *,
        grade: ImageQualityGrade,
        sharpness_score: float,
        contrast_score: float,
        brightness: float,
    ) -> ImageQualityStatus:
        """Map the usability grade onto the pre-Prompt-3 status vocabulary.

        Kept for back-compatibility with the aggregate-quality read path; the
        ``grade`` is the authoritative Prompt-3 signal.
        """
        if grade in (ImageQualityGrade.EXCELLENT, ImageQualityGrade.GOOD):
            return ImageQualityStatus.OK
        if grade == ImageQualityGrade.REJECTED:
            return ImageQualityStatus.INSUFFICIENT
        # ACCEPTABLE / POOR: attribute the dominant degradation for the operator.
        if brightness > 0.8 and contrast_score < 0.5:
            return ImageQualityStatus.GLARE
        if sharpness_score < 0.45:
            return ImageQualityStatus.BLURRY
        return ImageQualityStatus.OK
