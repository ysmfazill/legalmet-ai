"""Deterministic MOCK image-quality analyzer (foundation phase).

DEMO ONLY. Produces a quality verdict seeded by a stable key, with genuine
low-resolution detection when dimensions are supplied. Feeds the confidence
policy: if quality is insufficient, the rule engine must NOT assert a legal
conclusion.
"""
from __future__ import annotations

import hashlib
import random

from app.core.enums import ImageQualityStatus
from app.services.interfaces import ImageQualityAnalyzer, ImageQualityResult


def _rng(seed: str) -> random.Random:
    digest = hashlib.sha256(("quality:" + seed).encode("utf-8")).hexdigest()
    return random.Random(int(digest[:12], 16))


class MockImageQualityAnalyzer(ImageQualityAnalyzer):
    def analyze(
        self,
        *,
        image_bytes: bytes | None,
        width: int | None,
        height: int | None,
        mime_type: str,
        seed: str,
    ) -> ImageQualityResult:
        # Genuine, deterministic low-resolution check when dimensions are known.
        if width is not None and height is not None and min(width, height) < 400:
            return ImageQualityResult(
                status=ImageQualityStatus.LOW_RESOLUTION,
                score=0.35,
                notes="Image resolution below the recommended minimum (400px).",
            )

        rng = _rng(seed)
        roll = rng.random()
        if roll < 0.72:
            return ImageQualityResult(ImageQualityStatus.OK, round(rng.uniform(0.8, 0.99), 3))
        if roll < 0.84:
            return ImageQualityResult(
                ImageQualityStatus.GLARE, round(rng.uniform(0.45, 0.62), 3),
                "Reflection/glare detected over part of the label.",
            )
        if roll < 0.94:
            return ImageQualityResult(
                ImageQualityStatus.BLURRY, round(rng.uniform(0.4, 0.6), 3),
                "Image appears out of focus.",
            )
        return ImageQualityResult(
            ImageQualityStatus.INSUFFICIENT, round(rng.uniform(0.2, 0.38), 3),
            "Insufficient visual quality for reliable analysis.",
        )
