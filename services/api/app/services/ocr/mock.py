"""Deterministic MOCK OCR service (foundation phase).

DEMO ONLY. Emits plausible, clearly-fabricated label text with bounding boxes
and confidence scores, seeded by a stable key so results are reproducible and
varied across images. This will be replaced by a real OCR backend (e.g.
PaddleOCR) behind the same :class:`OCRService` interface — no call site changes.
"""
from __future__ import annotations

import hashlib
import random

from app.core.enums import ModelServiceType
from app.services.interfaces import BBox, OcrLine, OcrResult, OCRService, ServiceDescriptor

# (text, x, y, width, height) — approximate label layout in 0..1 coordinates.
_DEMO_LINES: list[tuple[str, float, float, float, float]] = [
    ("DEMO Wholesome Product", 0.10, 0.08, 0.55, 0.06),
    ("M.R.P. Rs. 199.00 (incl. of all taxes)", 0.10, 0.20, 0.60, 0.05),
    ("Net Qty: 500 g", 0.10, 0.30, 0.35, 0.05),
    ("Mfd by: DEMO Foods Pvt Ltd, Demo City", 0.10, 0.42, 0.70, 0.05),
    ("Batch No: DMO-2231", 0.10, 0.52, 0.40, 0.05),
    ("Mfg Date: 03/2026", 0.10, 0.60, 0.38, 0.05),
    ("Best Before: 9 months from packaging", 0.10, 0.68, 0.62, 0.05),
    ("Country of Origin: India", 0.10, 0.76, 0.45, 0.05),
    ("Customer Care: care@demo.example, 1800-000-000", 0.10, 0.84, 0.75, 0.05),
]


def _rng(seed: str) -> random.Random:
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return random.Random(int(digest[:12], 16))


class MockOCRService(OCRService):
    @property
    def descriptor(self) -> ServiceDescriptor:
        return ServiceDescriptor(
            service_type=ModelServiceType.OCR,
            name="mock-ocr",
            version="0.1.0-demo",
            provider="mock",
        )

    def extract_text(self, *, image_bytes: bytes | None, storage_key: str, seed: str) -> OcrResult:
        rng = _rng(seed or storage_key)
        lines: list[OcrLine] = []

        # Occasionally drop 0-2 declarations to simulate incomplete labels.
        drop_count = rng.choice([0, 0, 1, 1, 2])
        droppable = list(range(1, len(_DEMO_LINES)))  # keep the product name
        rng.shuffle(droppable)
        dropped = set(droppable[:drop_count])

        for idx, (text, x, y, w, h) in enumerate(_DEMO_LINES):
            if idx in dropped:
                continue
            # Confidence mostly high, occasionally low (drives REVIEW paths).
            base = rng.uniform(0.72, 0.98)
            if rng.random() < 0.12:
                base = rng.uniform(0.35, 0.58)
            lines.append(OcrLine(text=text, bbox=BBox(x, y, w, h), confidence=round(base, 3)))

        mean = round(sum(line.confidence for line in lines) / len(lines), 3) if lines else 0.0
        return OcrResult(lines=lines, mean_confidence=mean, descriptor=self.descriptor)
