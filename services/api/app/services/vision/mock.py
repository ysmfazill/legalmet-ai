"""Deterministic MOCK computer-vision service (foundation phase).

DEMO ONLY. Synthesises region detections from OCR line boxes and maps OCR text
to declaration field candidates using simple keyword heuristics. A real
implementation (e.g. a YOLO-based detector + layout model) plugs in behind the
same :class:`VisionService` interface.

The field mapping here is intentionally a *perception* step: it only proposes
"this text looks like an MRP", never whether that satisfies any legal rule.
"""
from __future__ import annotations

import re

from app.core.enums import FieldType, ModelServiceType, RegionType
from app.services.interfaces import (
    DetectedRegion,
    FieldCandidate,
    OcrResult,
    ProductProfile,
    ServiceDescriptor,
    VisionRegionsResult,
    VisionService,
)

_QTY_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(kg|g|mg|l|ml|pcs|n|units?)\b", re.IGNORECASE)
_PRICE_RE = re.compile(r"(?:rs\.?|inr|₹)\s*([\d,]+(?:\.\d{1,2})?)", re.IGNORECASE)


def _classify_text(text: str) -> tuple[FieldType, str | None, str | None]:
    """Return (field_type, normalized_value, unit) for a line of OCR text."""
    lowered = text.lower()
    if "mrp" in lowered or "m.r.p" in lowered or _PRICE_RE.search(text):
        match = _PRICE_RE.search(text)
        value = match.group(1).replace(",", "") if match else None
        return FieldType.MRP, value, "INR" if value else None
    if "net qty" in lowered or "net quantity" in lowered:
        match = _QTY_RE.search(text)
        if match:
            return FieldType.NET_QUANTITY, match.group(1), match.group(2).lower()
        return FieldType.NET_QUANTITY, None, None
    if "mfd by" in lowered or "manufactured" in lowered or "mfg by" in lowered:
        return FieldType.MANUFACTURER_DETAILS, text.split(":", 1)[-1].strip() or None, None
    if "batch" in lowered:
        return FieldType.BATCH_NUMBER, text.split(":", 1)[-1].strip() or None, None
    if "mfg date" in lowered or "date of manufacture" in lowered or "mfd date" in lowered:
        return FieldType.DATE_OF_MANUFACTURE, text.split(":", 1)[-1].strip() or None, None
    if "best before" in lowered or "use by" in lowered or "expiry" in lowered:
        return FieldType.BEST_BEFORE, text.split(":", 1)[-1].strip() or None, None
    if "country of origin" in lowered:
        return FieldType.COUNTRY_OF_ORIGIN, text.split(":", 1)[-1].strip() or None, None
    if "customer care" in lowered or "consumer care" in lowered:
        return FieldType.CONSUMER_CARE, text.split(":", 1)[-1].strip() or None, None
    return FieldType.OTHER, None, None


class MockVisionService(VisionService):
    @property
    def descriptor(self) -> ServiceDescriptor:
        return ServiceDescriptor(
            service_type=ModelServiceType.VISION,
            name="mock-vision",
            version="0.1.0-demo",
            provider="mock",
        )

    def detect_regions(
        self, *, image_bytes: bytes | None, storage_key: str, seed: str
    ) -> VisionRegionsResult:
        # Region detection is proxied from OCR line boxes in the orchestrator;
        # here we return an empty scaffold — real detectors fill this in.
        return VisionRegionsResult(regions=[], descriptor=self.descriptor)

    def detect_fields(
        self,
        *,
        ocr: OcrResult,
        regions: VisionRegionsResult,
        profile: ProductProfile,
        seed: str,
    ) -> list[FieldCandidate]:
        candidates: list[FieldCandidate] = []
        for line in ocr.lines:
            field_type, normalized, unit = _classify_text(line.text)
            if field_type == FieldType.OTHER:
                continue
            candidates.append(
                FieldCandidate(
                    field_type=field_type,
                    raw_text=line.text,
                    confidence=line.confidence,
                    bbox=line.bbox,
                    normalized_value=normalized,
                    unit=unit,
                )
            )
        return candidates

    def regions_from_ocr(self, ocr: OcrResult) -> VisionRegionsResult:
        """Helper used by the orchestrator to persist spatial evidence regions."""
        regions = [
            DetectedRegion(region_type=RegionType.TEXT_LINE, bbox=line.bbox, confidence=line.confidence)
            for line in ocr.lines
        ]
        return VisionRegionsResult(regions=regions, descriptor=self.descriptor)
