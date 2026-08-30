"""PROMPT 9 Phase 4 — Indian-language OCR validation (integration).

Only languages VERIFIED HERE are claimed by the system (see
``PaddleOCRService.SUPPORTED_LANGS``). Each test renders real script text with
a real font and requires the actual PaddleOCR engine to recognize it.

Verified on this install (paddleocr 3.1.0 / PP-OCRv5, CPU):
* en — English
* hi — Hindi (Devanagari script models auto-download on first use)
* ka — Kannada

Malayalam (``ml``) has NO models in this paddleocr version — the service must
reject it with ``UNSUPPORTED_LANGUAGE`` instead of silently using another
script's models. Tamil/Telugu models exist in the library but are NOT verified
by tests, so they are NOT claimed.

    pytest -m integration tests/test_ocr_languages_integration.py
"""
from __future__ import annotations

import io

import pytest
from PIL import Image, ImageDraw, ImageFont

from app.core.errors import ValidationError
from app.services.ocr.paddle import SUPPORTED_LANGS, PaddleOCRService

pytestmark = pytest.mark.integration

_DEVANAGARI_FONT = r"C:\Windows\Fonts\Nirmala.ttc"

# Simple script text (post-base matras, no conjuncts) so shaping-free Pillow
# rendering stays legible; recognition is still genuinely performed by OCR.
HINDI_LINES = ["देश का उत्पाद भारत", "नेट मात्रा 5 किलो", "एमआरपी 245 रुपये"]
KANNADA_LINES = ["ದೇಶ ಉತ್ಪನ್ನ ಭಾರತ", "ನಿವ್ವಳ ಪ್ರಮಾಣ 5 ಕೆಜಿ"]
ENGLISH_LINES = ["Country of Origin: India", "Net Qty: 250 g"]


def _font(size: int = 48):
    try:
        return ImageFont.truetype(_DEVANAGARI_FONT, size)
    except OSError:
        return ImageFont.truetype("arial.ttf", size)


def _render(lines: list[str]) -> bytes:
    img = Image.new("RGB", (1000, 120 + 120 * len(lines)), (248, 248, 248))
    draw = ImageDraw.Draw(img)
    y = 60
    for text in lines:
        draw.text((60, y), text, fill=(10, 10, 10), font=_font())
        y += 120
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class TestSupportedLanguages:
    def test_english_recognized(self, ocr_en: PaddleOCRService):
        result = ocr_en.extract_text(
            image_bytes=_render(ENGLISH_LINES), storage_key="lang-en", seed="lang-en"
        )
        joined = " ".join(line.text for line in result.lines).lower()
        assert "india" in joined and "250 g" in joined, joined

    def test_hindi_recognized(self, ocr_hi: PaddleOCRService):
        result = ocr_hi.extract_text(
            image_bytes=_render(HINDI_LINES), storage_key="lang-hi", seed="lang-hi"
        )
        assert result.lines, "Hindi engine returned no text"
        # Real Devanagari recognition: a distinctive substring of a rendered
        # line must appear (OCR may merge/drop spaces — compare space-stripped).
        stripped = "".join(line.text for line in result.lines).replace(" ", "")
        assert "भारत" in stripped, f"Hindi not recognized: {stripped!r}"
        for line in result.lines:
            assert line.language == "hi"

    def test_kannada_recognized(self, ocr_ka: PaddleOCRService):
        result = ocr_ka.extract_text(
            image_bytes=_render(KANNADA_LINES), storage_key="lang-ka", seed="lang-ka"
        )
        assert result.lines, "Kannada engine returned no text"
        stripped = "".join(line.text for line in result.lines).replace(" ", "")
        assert "ಭಾರತ" in stripped, f"Kannada not recognized: {stripped!r}"
        for line in result.lines:
            assert line.language == "ka"


class TestUnsupportedLanguages:
    def test_malayalam_rejected_with_explicit_code(self):
        """No models exist for Malayalam in this paddleocr version — the
        service must refuse with UNSUPPORTED_LANGUAGE (never a silent
        fallback to another script's models)."""
        with pytest.raises(ValidationError) as excinfo:
            PaddleOCRService(langs=["ml"])
        assert excinfo.value.code.value == "UNSUPPORTED_LANGUAGE"
        assert "ml" in str(excinfo.value)

    def test_unverified_library_language_rejected(self):
        """Tamil/Telugu models exist in the library but are NOT verified by
        our tests — they must not be claimable."""
        with pytest.raises(ValidationError):
            PaddleOCRService(langs=["ta"])

    def test_supported_set_matches_verified_languages(self):
        assert SUPPORTED_LANGS == frozenset({"en", "hi", "ka"})


# --- engines (module-scoped: one lazy init each) -------------------------------


@pytest.fixture(scope="module")
def ocr_en() -> PaddleOCRService:
    return PaddleOCRService(langs=["en"], timeout_seconds=600.0)


@pytest.fixture(scope="module")
def ocr_hi() -> PaddleOCRService:
    return PaddleOCRService(langs=["hi"], timeout_seconds=600.0)


@pytest.fixture(scope="module")
def ocr_ka() -> PaddleOCRService:
    return PaddleOCRService(langs=["ka"], timeout_seconds=600.0)
