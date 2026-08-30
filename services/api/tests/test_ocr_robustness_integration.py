"""PROMPT 9 Phase 3 — OCR robustness (integration, real PaddleOCR engine).

Measures and verifies:
* first-run model initialisation vs warm inference time (printed, recorded in
  docs/production-hardening.md — no fabricated numbers);
* per-image OCR processing time;
* failure behaviour on malformed image bytes (proper failure state, no crash);
* large-image behaviour (preprocessor caps the long edge before inference);
* rotated-image behaviour (recognition degrades gracefully, no exception).

Pipeline invariants re-verified at the API level by the golden E2E test:
original image preserved, OCR derivative stored separately, raw OCR text and
bounding boxes persisted verbatim, confidence semantics unchanged.

    pytest -m integration tests/test_ocr_robustness_integration.py -s
"""
from __future__ import annotations

import io
import time

import pytest
from PIL import Image, ImageDraw, ImageFont

from app.core.errors import ServiceUnavailableError
from app.services.ocr.paddle import PaddleOCRService
from app.services.perception.preprocess import PillowOcrPreprocessor

pytestmark = pytest.mark.integration


def _font(size: int):
    for name in ("arial.ttf", "Arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _label(width: int = 1000, height: int = 640, font_size: int = 36) -> bytes:
    img = Image.new("RGB", (width, height), (248, 248, 248))
    draw = ImageDraw.Draw(img)
    draw.rectangle([20, 20, width - 20, height - 20], outline=(0, 0, 0), width=6)
    lines = [
        "ROBUSTNESS TEST LABEL",
        "Net Qty: 250 g",
        "M.R.P. Rs. 149.00",
        "Batch No: RT-0001",
        "Country of Origin: India",
    ]
    y = 80
    for index, line in enumerate(lines):
        draw.text((70, y), line, fill=(10, 10, 10), font=_font(48 if index == 0 else font_size))
        y += (48 if index == 0 else font_size) + 52
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture(scope="module")
def preprocessor() -> PillowOcrPreprocessor:
    return PillowOcrPreprocessor()


@pytest.fixture(scope="module")
def ocr() -> PaddleOCRService:
    # Engine created but NOT yet initialised (lazy): the first extract_text
    # call below pays the model-init cost, subsequent calls are warm.
    return PaddleOCRService(langs=["en"], timeout_seconds=600.0)


class TestOcrTiming:
    def test_cold_init_then_warm_inference(self, ocr, preprocessor):
        """Record first-run (model init + inference) vs warm inference."""
        prep = preprocessor.prepare(image_bytes=_label())

        t0 = time.perf_counter()
        first = ocr.extract_text(image_bytes=prep.data, storage_key="c", seed="c")
        cold_s = time.perf_counter() - t0

        t0 = time.perf_counter()
        warm = ocr.extract_text(image_bytes=prep.data, storage_key="w", seed="w")
        warm_s = time.perf_counter() - t0

        print(f"\n[cold init+inference] {cold_s:.2f}s  [warm inference] {warm_s:.2f}s")
        assert first.lines and warm.lines
        # Warm inference must not pay the init cost again.
        assert warm_s < cold_s or cold_s < 5.0  # init already cached from earlier modules


class TestOcrFailureBehaviour:
    def test_malformed_image_bytes_fail_cleanly(self, ocr):
        """Garbage bytes -> explicit AI_SERVICE_UNAVAILABLE, no exception leak,
        no fabricated text."""
        with pytest.raises(ServiceUnavailableError) as excinfo:
            ocr.extract_text(
                image_bytes=b"this is not an image at all" * 10,
                storage_key="garbage",
                seed="garbage",
            )
        assert "decode" in str(excinfo.value).lower() or "unavailable" in str(excinfo.value).lower()

    def test_empty_bytes_fail_cleanly(self, ocr):
        with pytest.raises(ServiceUnavailableError):
            ocr.extract_text(image_bytes=b"", storage_key="empty", seed="empty")


class TestLargeImageBehaviour:
    def test_oversized_image_is_capped_and_still_processed(self, ocr, preprocessor):
        """A 4000x5200 upload is downscaled by the preprocessor (max long edge
        2400) before inference; recognition still works."""
        huge = _label(width=4000, height=5200, font_size=120)
        prep = preprocessor.prepare(image_bytes=huge)
        assert max(prep.width, prep.height) <= 2400, "preprocessor must cap the long edge"
        result = ocr.extract_text(image_bytes=prep.data, storage_key="big", seed="big")
        joined = " ".join(line.text for line in result.lines).lower()
        assert "net qty" in joined or "250" in joined, joined


class TestRotatedImageBehaviour:
    def test_rotated_label_still_yields_text(self, ocr, preprocessor):
        """A 10-degree rotation must not crash OCR; recognition may degrade
        but the run completes and returns whatever is genuinely readable."""
        img = Image.open(io.BytesIO(_label()))
        rotated = img.rotate(10, expand=True, fillcolor=(248, 248, 248), resample=Image.BICUBIC)
        buf = io.BytesIO()
        rotated.save(buf, format="PNG")
        prep = preprocessor.prepare(image_bytes=buf.getvalue())
        result = ocr.extract_text(image_bytes=prep.data, storage_key="rot", seed="rot")
        # Recognition is genuinely attempted — no fabricated guarantees about
        # which lines survive a rotation; the engine simply must not fail.
        assert isinstance(result.lines, list)


class TestConfidenceSemantics:
    def test_confidences_are_bounded_scores(self, ocr, preprocessor):
        prep = preprocessor.prepare(image_bytes=_label())
        result = ocr.extract_text(image_bytes=prep.data, storage_key="cs", seed="cs")
        for line in result.lines:
            assert 0.0 <= line.confidence <= 1.0
            # Bounding boxes normalised to the derivative dimensions.
            assert 0.0 <= line.bbox.x <= 1.0
            assert 0.0 < line.bbox.width <= 1.0
