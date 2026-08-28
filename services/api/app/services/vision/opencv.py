"""Real OpenCV vision service (Prompt 4).

Region-level perception behind the existing :class:`VisionService` seam:
QR-code and 1D barcode (EAN/UPC/Code-128 family) detection + decoding via
OpenCV's detectors. OCR text-line regions are NOT produced here — the pipeline
derives them directly from OCR boxes, which keeps the text evidence chain exact.

Decoded symbol values are stored as region payload evidence only. They are
never used to draw legal conclusions.

This is a deliberately modest first vision implementation: it does not attempt
logo/graphic segmentation, and reports no fabricated accuracy. Detected-but-
undecodable symbols are still reported as regions with a low confidence and a
payload marked ``decoded: false``.
"""
from __future__ import annotations

import cv2
import numpy as np

from app.core.enums import ModelServiceType, RegionType
from app.core.errors import ServiceUnavailableError
from app.services.interfaces import (
    BBox,
    DetectedRegion,
    FieldCandidate,
    OcrResult,
    ProductProfile,
    ServiceDescriptor,
    VisionRegionsResult,
    VisionService,
)


class OpenCVVisionService(VisionService):
    """QR/barcode region detection using the local OpenCV build."""

    def __init__(self) -> None:
        self._qr = cv2.QRCodeDetector()
        self._barcode = cv2.barcode.BarcodeDetector()

    @property
    def descriptor(self) -> ServiceDescriptor:
        return ServiceDescriptor(
            service_type=ModelServiceType.VISION,
            name="opencv-qr-barcode",
            version=cv2.__version__,
            provider="OpenCV",
        )

    # --- VisionService ---------------------------------------------------------

    def detect_regions(
        self, *, image_bytes: bytes | None, storage_key: str, seed: str
    ) -> VisionRegionsResult:
        if image_bytes is None:
            raise ServiceUnavailableError(
                "Real vision analysis requires the stored image bytes; none were provided.",
                details={"storageKey": storage_key},
            )
        array = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
        if array is None:
            raise ServiceUnavailableError(
                "The vision derivative could not be decoded for inference.",
                details={"storageKey": storage_key},
            )
        height, width = array.shape[:2]
        regions: list[DetectedRegion] = []

        try:
            regions.extend(self._detect_qr(array, width, height))
        except cv2.error:
            # A detector crash on one modality must not sink the whole run.
            pass
        try:
            regions.extend(self._detect_barcodes(array, width, height))
        except cv2.error:
            pass

        return VisionRegionsResult(regions=regions, descriptor=self.descriptor)

    def detect_fields(
        self, *, ocr: OcrResult, regions: VisionRegionsResult, profile: ProductProfile, seed: str
    ) -> list[FieldCandidate]:
        """Field extraction lives in the deterministic FieldExtractionProvider
        seam (see ``app.services.perception.extract``); this vision backend is
        region-only and intentionally proposes no field candidates."""
        return []

    # --- internals ---------------------------------------------------------------

    def _detect_qr(self, array: np.ndarray, width: int, height: int) -> list[DetectedRegion]:
        regions: list[DetectedRegion] = []
        ok, decoded, points, _ = self._qr.detectAndDecodeMulti(array)
        if not ok or points is None:
            # Fallback: single-code path catches codes the multi detector misses.
            text, single_points, _ = self._qr.detectAndDecode(array)
            if single_points is not None:
                regions.append(
                    self._region_from_points(
                        single_points, width, height, RegionType.QR_CODE,
                        payload={"symbology": "QR", "value": text or None, "decoded": bool(text)},
                        confidence=1.0 if text else 0.5,
                    )
                )
            return regions
        for value, quad in zip(decoded, points, strict=False):
            text = str(value) if value else None
            regions.append(
                self._region_from_points(
                    quad, width, height, RegionType.QR_CODE,
                    payload={"symbology": "QR", "value": text, "decoded": text is not None},
                    confidence=1.0 if text else 0.5,
                )
            )
        return regions

    def _detect_barcodes(self, array: np.ndarray, width: int, height: int) -> list[DetectedRegion]:
        regions: list[DetectedRegion] = []
        try:
            ok, decoded, types, points = self._barcode.detectAndDecodeWithType(array)
        except (cv2.error, ValueError):
            return regions
        if not ok or points is None or len(points) == 0:
            return regions
        decoded = list(decoded or [])
        types = list(types or [])
        for i, quad in enumerate(points):
            value = decoded[i] if i < len(decoded) else ""
            symbology = types[i] if i < len(types) else "UNKNOWN"
            regions.append(
                self._region_from_points(
                    quad, width, height, RegionType.BARCODE,
                    payload={
                        "symbology": str(symbology or "UNKNOWN").upper(),
                        "value": value or None,
                        "decoded": bool(value),
                    },
                    confidence=1.0 if value else 0.5,
                )
            )
        return regions

    @staticmethod
    def _region_from_points(
        points: np.ndarray,
        width: int,
        height: int,
        region_type: RegionType,
        *,
        payload: dict | None,
        confidence: float,
    ) -> DetectedRegion:
        xs = [float(pt[0]) for pt in points]
        ys = [float(pt[1]) for pt in points]
        x0, x1 = max(0.0, min(xs)), min(float(width), max(xs))
        y0, y1 = max(0.0, min(ys)), min(float(height), max(ys))
        bbox = BBox(
            x=round(x0 / width, 6),
            y=round(y0 / height, 6),
            width=round(max(0.0, x1 - x0) / width, 6),
            height=round(max(0.0, y1 - y0) / height, 6),
        )
        return DetectedRegion(
            region_type=region_type, bbox=bbox, confidence=confidence, payload=payload
        )
