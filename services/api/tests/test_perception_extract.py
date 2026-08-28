"""Unit tests for deterministic field extraction + OCR normalization (Prompt 4).

These are pure-function tests: no database, no AI engines, no network. They
pin the behaviour of:

* :func:`app.services.perception.normalize.normalize_ocr_text` — the derived
  tidy-up (raw text is immutable evidence and must survive verbatim),
* :class:`app.services.perception.extract.DeterministicFieldExtractor` — the
  regex/keyword/typography rules that turn OCR lines into field candidates.

Guardrails asserted throughout: candidates are *perception* claims only —
DETECTED / REVIEW_REQUIRED / NOT_EXTRACTED — and confidence is always
``ocr_confidence × pattern_weight`` (OCR confidence, never legal confidence).
"""
from __future__ import annotations

from app.core.enums import ExtractionStatus, FieldType, ModelServiceType
from app.services.interfaces import BBox, OcrLine, OcrResult, ServiceDescriptor
from app.services.perception.extract import DeterministicFieldExtractor
from app.services.perception.normalize import normalize_ocr_text


def _line(text: str, *, y: float = 0.5, h: float = 0.05, conf: float = 0.95) -> OcrLine:
    return OcrLine(text=text, bbox=BBox(0.1, y, 0.6, h), confidence=conf)


def _ocr(lines: list[OcrLine]) -> OcrResult:
    mean = round(sum(line.confidence for line in lines) / len(lines), 4) if lines else 0.0
    return OcrResult(
        lines=lines,
        mean_confidence=mean,
        descriptor=ServiceDescriptor(
            service_type=ModelServiceType.OCR, name="fake-ocr", version="1.0.0", provider="fake"
        ),
        width=1200,
        height=1600,
    )


def _extract(lines: list[OcrLine]):
    return DeterministicFieldExtractor().extract(ocr=_ocr(lines))


def _by_type(candidates, field_type: FieldType):
    return [c for c in candidates if c.field_type == field_type]


# --- normalize_ocr_text -------------------------------------------------------


class TestNormalizeOcrText:
    def test_collapses_whitespace(self):
        assert normalize_ocr_text("  Net   Qty: \n 500\tg  ") == "Net Qty: 500 g"

    def test_currency_space_removed_after_rupee_sign(self):
        assert normalize_ocr_text("MRP ₹ 499.00") == "MRP ₹499.00"

    def test_currency_space_removed_after_rs(self):
        assert normalize_ocr_text("Rs . 199.00") == "Rs. 199.00"

    def test_inr_keeps_space(self):
        assert normalize_ocr_text("INR 199.00 only") == "INR 199.00 only"

    def test_numberish_token_letter_confusions_fixed(self):
        assert normalize_ocr_text("1O0 g") == "100 g"
        assert normalize_ocr_text("Batch l23") == "Batch 123"

    def test_words_are_never_digit_mangled(self):
        # No digits inside these tokens -> the fixer must leave them alone.
        assert normalize_ocr_text("Oil and Iol") == "Oil and Iol"

    def test_empty_and_blank(self):
        assert normalize_ocr_text("") == ""
        assert normalize_ocr_text("   ") == ""

    def test_nfc_unicode_normalization(self):
        # Decomposed "e" + combining acute must collapse to the composed form.
        assert normalize_ocr_text("café") == "café"


# --- descriptor ---------------------------------------------------------------


class TestExtractorDescriptor:
    def test_descriptor_identity(self):
        extractor = DeterministicFieldExtractor()
        d = extractor.descriptor
        assert d.service_type == ModelServiceType.FIELD_EXTRACTOR
        assert d.name == "deterministic-regex"
        assert d.provider == "legalmet"

    def test_review_threshold_property(self):
        assert DeterministicFieldExtractor().review_threshold == 0.6


# --- keyword-anchored extraction ----------------------------------------------


class TestKeywordExtraction:
    def test_mrp_detected(self):
        (candidate,) = _extract([_line("M.R.P. Rs. 199.00 (incl. of all taxes)")])
        assert candidate.field_type == FieldType.MRP
        assert candidate.normalized_value == "Rs 199.00"
        assert candidate.unit is None
        assert candidate.status == ExtractionStatus.DETECTED
        assert candidate.method == "regex:mrp"
        assert candidate.confidence == 0.95  # ocr_conf 0.95 x weight 1.0
        assert candidate.source_index == 0

    def test_rupee_symbol_mrp(self):
        (candidate,) = _extract([_line("MRP ₹ 499", conf=0.9)])
        assert candidate.field_type == FieldType.MRP
        assert candidate.normalized_value == "₹499"
        assert candidate.status == ExtractionStatus.DETECTED

    def test_net_quantity_detected(self):
        (candidate,) = _extract([_line("Net Qty: 500 g")])
        assert candidate.field_type == FieldType.NET_QUANTITY
        assert candidate.normalized_value == "500 g"
        assert candidate.status == ExtractionStatus.DETECTED
        assert candidate.method == "regex:net-quantity"

    def test_batch_number_after_colon(self):
        (candidate,) = _extract([_line("Batch No: DMO-2231")])
        assert candidate.field_type == FieldType.BATCH_NUMBER
        assert candidate.normalized_value == "DMO-2231"
        assert candidate.status == ExtractionStatus.DETECTED

    def test_manufacturer_free_text(self):
        (candidate,) = _extract([_line("Mfd by: Sunrise Foods Pvt Ltd, Kochi")])
        assert candidate.field_type == FieldType.MANUFACTURER_DETAILS
        assert candidate.normalized_value == "Sunrise Foods Pvt Ltd, Kochi"
        assert candidate.status == ExtractionStatus.DETECTED

    def test_country_of_origin(self):
        (candidate,) = _extract([_line("Country of Origin: India")])
        assert candidate.field_type == FieldType.COUNTRY_OF_ORIGIN
        assert candidate.normalized_value == "India"
        assert candidate.status == ExtractionStatus.DETECTED

    def test_consumer_care_line_with_email(self):
        (candidate,) = _extract([_line("Customer Care: care@example.com")])
        assert candidate.field_type == FieldType.CONSUMER_CARE
        assert candidate.normalized_value == "care@example.com"
        assert candidate.status == ExtractionStatus.DETECTED
        assert candidate.method == "regex:consumer-care"

    def test_bare_email_detected(self):
        (candidate,) = _extract([_line("write to feedback@brand.in today")])
        assert candidate.field_type == FieldType.CONSUMER_CARE
        assert candidate.normalized_value == "feedback@brand.in"
        assert candidate.status == ExtractionStatus.DETECTED
        assert candidate.method == "regex:email"

    def test_date_keyword_takes_priority_over_manufacturer(self):
        # "Mfg Date" must resolve to DATE_OF_MANUFACTURE, not manufacturer.
        (candidate,) = _extract([_line("Mfg Date: 03/06/2026")])
        assert candidate.field_type == FieldType.DATE_OF_MANUFACTURE
        assert candidate.normalized_value == "03/06/2026"
        assert candidate.method == "regex:date-of-manufacture"

    def test_manufactured_on_is_a_date(self):
        (candidate,) = _extract([_line("Manufactured on 12 Jan 2026")])
        assert candidate.field_type == FieldType.DATE_OF_MANUFACTURE
        assert candidate.normalized_value == "12 Jan 2026"

    def test_best_before_duration(self):
        (candidate,) = _extract([_line("Best Before: 9 months from packaging")])
        assert candidate.field_type == FieldType.BEST_BEFORE
        assert candidate.normalized_value == "9 months"

    def test_expiry_month_year(self):
        (candidate,) = _extract([_line("EXP 03/2027")])
        assert candidate.field_type == FieldType.EXPIRY_DATE
        assert candidate.normalized_value == "03/2027"

    def test_language_tag_is_propagated(self):
        line = OcrLine(
            text="Net Qty: 250 g",
            bbox=BBox(0.1, 0.5, 0.4, 0.05),
            confidence=0.9,
            language="en",
        )
        (candidate,) = DeterministicFieldExtractor().extract(ocr=_ocr([line]))
        assert candidate.language == "en"


# --- uncertainty paths --------------------------------------------------------


class TestUncertaintyPaths:
    def test_keyword_without_value_is_not_extracted(self):
        (candidate,) = _extract([_line("MRP :")])
        assert candidate.field_type == FieldType.MRP
        assert candidate.normalized_value is None
        assert candidate.status == ExtractionStatus.NOT_EXTRACTED

    def test_low_ocr_confidence_becomes_review_required(self):
        (candidate,) = _extract([_line("Net Qty: 500 g", conf=0.55)])
        assert candidate.field_type == FieldType.NET_QUANTITY
        # 0.55 x 1.0 = 0.55 < 0.6 -> human review, never silently asserted.
        assert candidate.status == ExtractionStatus.REVIEW_REQUIRED

    def test_unlabeled_price_is_review_required(self):
        (candidate,) = _extract([_line("₹499")])
        assert candidate.field_type == FieldType.MRP
        assert candidate.normalized_value == "₹499"
        assert candidate.unit == "INR"
        # 0.95 x 0.5 = 0.475 < 0.6
        assert candidate.status == ExtractionStatus.REVIEW_REQUIRED
        assert candidate.method == "regex:price-unlabeled"

    def test_phone_number_is_review_required(self):
        (candidate,) = _extract([_line("1800-123-4567")])
        assert candidate.field_type == FieldType.CONSUMER_CARE
        assert candidate.status == ExtractionStatus.REVIEW_REQUIRED
        assert candidate.method == "regex:phone"

    def test_product_name_heuristic_is_always_review(self):
        candidates = _extract(
            [
                _line("SUNRISE CRUNCHY MASALA", y=0.05, h=0.09),
                _line("Net Qty: 500 g", y=0.4, h=0.04),
            ]
        )
        names = _by_type(candidates, FieldType.PRODUCT_NAME)
        assert len(names) == 1
        candidate = names[0]
        assert candidate.raw_text == "SUNRISE CRUNCHY MASALA"
        assert candidate.status == ExtractionStatus.REVIEW_REQUIRED
        assert candidate.method == "heuristic:typography"
        # Heuristics never claim DETECTED even with a high OCR score.
        assert candidate.confidence == round(0.95 * 0.5, 4)

    def test_claimed_line_is_not_reused_as_product_name(self):
        # The tall line IS claimed by a keyword rule, and the remaining line is
        # too short (0.05 < 0.75 * 0.09) to qualify — no product-name candidate.
        candidates = _extract(
            [
                _line("Net Qty: 500 g", y=0.05, h=0.09),  # tall AND claimed
                _line("PLAIN TEXT", y=0.2, h=0.05),
            ]
        )
        assert _by_type(candidates, FieldType.PRODUCT_NAME) == []

    def test_no_candidates_from_noise(self):
        assert _extract([_line("          ")]) == []
        assert _extract([]) == []


# --- confidence model ---------------------------------------------------------


class TestConfidenceModel:
    def test_confidence_is_ocr_times_weight(self):
        candidates = _extract([_line("Country of Origin: India", conf=0.8)])
        assert candidates[0].confidence == round(0.8 * 0.95, 4)

    def test_confidence_never_exceeds_one(self):
        candidates = _extract([_line("Net Qty: 500 g", conf=1.0)])
        assert candidates[0].confidence == 1.0
