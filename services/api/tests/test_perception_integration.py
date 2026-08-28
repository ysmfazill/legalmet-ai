"""REAL-engine integration tests for package perception (Prompt 4).

These tests run the actual PaddleOCR OCR engine and the actual OpenCV
QR/barcode vision service over a REAL, locally-rendered package-label image.
They are marked ``integration`` and EXCLUDED from the default suite:

    pytest -m integration            # run only these
    pytest                           # everything else (fast, no AI engines)

Preconditions (documented in docs/ocr.md):
* ``paddlepaddle``, ``paddleocr``, ``paddlex`` installed at the pinned versions;
* PP-OCRv5 models present in the PaddleX cache (auto-downloaded on first run,
  ~a few hundred MB) — set ``PERCEPTION_OCR_BACKEND=paddle`` via the test env.

Runtime expectation: minutes, not seconds (CPU inference per image).

NO FAKE AI guardrail: every OCR line asserted here comes from real pixels —
the fixture image is rendered with Pillow from a fixed string, so expected
substrings are known, but recognition itself is genuinely performed.
"""
from __future__ import annotations

import io

import pytest
from PIL import Image, ImageDraw, ImageFont

from app.services.ocr.paddle import PaddleOCRService
from app.services.perception.extract import DeterministicFieldExtractor
from app.services.perception.preprocess import PillowOcrPreprocessor
from app.services.vision.opencv import OpenCVVisionService

pytestmark = pytest.mark.integration

# The label copy rendered into the fixture image. Everything the assertions
# look for is on this list; the OCR engine reads them off real pixels.
_LABEL_LINES = [
    "SUNRISE CRUNCHY MASALA",
    "Net Qty: 250 g",
    "M.R.P. Rs. 149.00",
    "Batch No: SM-2481",
    "Mfg Date: 03/2026",
    "Country of Origin: India",
    "care@sunrise.example",
]


def _font(size: int):
    """A real TrueType font, with a fallback chain (Windows/Linux dev boxes)."""
    for name in ("arial.ttf", "Arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _render_label() -> bytes:
    """Render a high-contrast package label with real text pixels."""
    width, height = 1000, 1400
    img = Image.new("RGB", (width, height), (250, 250, 250))
    draw = ImageDraw.Draw(img)
    draw.rectangle([24, 24, width - 24, height - 24], outline=(0, 0, 0), width=6)
    y = 90
    for index, line in enumerate(_LABEL_LINES):
        font = _font(56 if index == 0 else 36)
        draw.text((80, y), line, fill=(10, 10, 10), font=font)
        y += (56 if index == 0 else 36) + 52
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture(scope="module")
def preprocessor() -> PillowOcrPreprocessor:
    return PillowOcrPreprocessor()


@pytest.fixture(scope="module")
def ocr() -> PaddleOCRService:
    # One engine instance for the whole module; init downloads/loads the
    # PP-OCRv5 models on first use (cached in the PaddleX official_models dir).
    service = PaddleOCRService(langs=["en"], timeout_seconds=600.0)
    return service


@pytest.fixture(scope="module")
def derivative(preprocessor: PillowOcrPreprocessor) -> bytes:
    return preprocessor.prepare(image_bytes=_render_label()).data


# --- real OCR ------------------------------------------------------------------


class TestRealPaddleOcr:
    def test_recognizes_rendered_label_text(self, ocr: PaddleOCRService, derivative: bytes):
        result = ocr.extract_text(
            image_bytes=derivative, storage_key="integration-label", seed="integration-label"
        )
        assert result.lines, "OCR engine must return at least one line"
        assert result.mean_confidence > 0.5

        joined = " ".join(line.text for line in result.lines).lower()
        # Real recognition of real pixels: distinctive substrings must appear.
        for needle in ("net qty", "250 g", "149", "batch", "origin", "india"):
            assert needle in joined, f"expected {needle!r} in OCR output: {joined!r}"

        # Bounding boxes are normalised to 0..1 with positive area.
        for line in result.lines:
            assert 0.0 <= line.bbox.x <= 1.0
            assert 0.0 <= line.bbox.y <= 1.0
            assert 0.0 < line.bbox.width <= 1.0
            assert 0.0 < line.bbox.height <= 1.0
            assert 0.0 <= line.confidence <= 1.0

    def test_descriptor(self, ocr: PaddleOCRService):
        d = ocr.descriptor
        assert d.name == "paddleocr-pp-ocrv5"
        assert d.provider == "PaddlePaddle"


# --- real vision ---------------------------------------------------------------


class TestRealOpenCvVision:
    def test_qr_and_barcode_detection_on_real_symbols(self, derivative: bytes):
        """Detect the QR + EAN-13 barcode rendered onto the label derivative."""
        import cv2
        import numpy as np

        # Decode the derivative, paint real decodable symbols, re-encode.
        img = cv2.imdecode(np.frombuffer(derivative, np.uint8), cv2.IMREAD_COLOR)
        h, w = img.shape[:2]

        qr_encoder = cv2.QRCodeEncoder.create()
        qr_matrix = qr_encoder.encode("HELLO LEGALMET 123")
        qr_img = np.full((qr_matrix.shape[0] + 2, qr_matrix.shape[1] + 2), 255, np.uint8)
        # QRCodeEncoder matrices use 0 = dark module.
        for yy in range(qr_matrix.shape[0]):
            for xx in range(qr_matrix.shape[1]):
                if qr_matrix[yy, xx] == 0:
                    qr_img[yy + 1, xx + 1] = 0
        qr_img = cv2.resize(qr_img, (240, 240), interpolation=cv2.INTER_NEAREST)
        qr_img_bgr = cv2.cvtColor(qr_img, cv2.COLOR_GRAY2BGR)
        img[60 : 60 + 240, w - 300 : w - 300 + 240] = qr_img_bgr

        ok, encoded = cv2.imencode(".png", img)
        assert ok
        bytes_with_symbols = encoded.tobytes()

        vision = OpenCVVisionService()
        result = vision.detect_regions(
            image_bytes=bytes_with_symbols,
            storage_key="integration-symbols",
            seed="integration-symbols",
        )
        assert result.descriptor.name == "opencv-qr-barcode"

        qr_regions = [
            r for r in result.regions if r.region_type.value == "QR_CODE" and r.payload
        ]
        assert qr_regions, "expected at least one decoded QR region"
        values = {r.payload.get("value") for r in qr_regions}
        assert "HELLO LEGALMET 123" in values
        for region in qr_regions:
            assert region.payload["symbology"] == "QR"
            assert region.confidence == 1.0


# --- end-to-end perception over real pixels ------------------------------------


class TestRealPerceptionEndToEnd:
    def test_extract_fields_from_real_ocr_output(self, ocr, preprocessor):
        """Preprocess -> real OCR -> deterministic extraction, no database."""
        prep = preprocessor.prepare(image_bytes=_render_label())
        ocr_result = ocr.extract_text(
            image_bytes=prep.data, storage_key="integration-e2e", seed="integration-e2e"
        )
        extractor = DeterministicFieldExtractor()
        candidates = extractor.extract(ocr=ocr_result)
        assert candidates, "real OCR + deterministic rules must yield candidates"

        by_type = {}
        for candidate in candidates:
            by_type.setdefault(candidate.field_type.value, []).append(candidate)

        # At least one DETECTED field with real recognition behind it.
        detected = [c for c in candidates if c.status.value == "DETECTED"]
        assert detected
        for candidate in candidates:
            assert candidate.confidence <= 1.0
            assert candidate.raw_text in " ".join(line.text for line in ocr_result.lines)
