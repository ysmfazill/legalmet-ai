"""Deterministic declaration-field extraction (Prompt 4).

Rule-based candidate extraction from OCR text: keyword anchors + regex value
patterns (price, quantity, dates, phone, email, batch token) plus one
conservative typography heuristic for the product name. NO LLM, NO invented
values — when the evidence is weak the candidate is emitted with
status REVIEW_REQUIRED or NOT_EXTRACTED so a human can decide.

Every candidate is a *perception* claim ("this text looks like an MRP reading
₹499"). Whether any field is legally required or sufficient is decided much
later by the regulatory layer — never here.

Confidence model
----------------
candidate.confidence = ocr_line.confidence × pattern_weight

OCR confidence is the engine's own recognition score (OCR CONFIDENCE — never
"legal confidence"). The pattern weight discounts fuzzy heuristics. Candidates
below ``review_threshold`` become REVIEW_REQUIRED; keyword hits whose value
pattern found nothing become NOT_EXTRACTED.
"""
from __future__ import annotations

import re

from app.core.enums import ExtractionStatus, FieldType, ModelServiceType
from app.services.interfaces import (
    FieldCandidate,
    FieldExtractionProvider,
    OcrResult,
    ServiceDescriptor,
)
from app.services.perception.normalize import normalize_ocr_text

# --- value patterns ----------------------------------------------------------

_PRICE_RE = re.compile(r"(₹|rs\.?|inr)\s*([\d,]+(?:\.\d{1,2})?)", re.IGNORECASE)
_QUANTITY_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(kg|g|mg|l|ml|pcs|packs?|units?|count|nos)\b", re.IGNORECASE
)
_DATE_RE = re.compile(
    r"\d{1,2}\s*/\s*\d{1,2}\s*/\s*\d{2,4}"  # 03/06/2026
    r"|\d{1,2}\s*-\s*\d{1,2}\s*-\s*\d{2,4}"  # 03-06-2026
    r"|\d{1,2}\s*/\s*\d{2,4}"  # 03/2026 (MM/YYYY)
    r"|\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{2,4}"
    r"|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2},?\s+\d{2,4}"
    r"|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{4}",
    re.IGNORECASE,
)
_DURATION_RE = re.compile(r"\d+\s*(?:day|month|year)s?\b", re.IGNORECASE)
_PHONE_RE = re.compile(
    r"(?:\+91[\s-]?)?\d{5}[\s-]\d{5}"  # 98765 43210
    r"|1800[\s-]?\d{3}[\s-]?\d{4}"  # 1800-123-4567
    r"|0\d{2,4}[\s-]?\d{6,8}"  # landlines 022-28123456
    r"|\b\d{10}\b",  # 9876543210
)
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_BATCH_TOKEN_RE = re.compile(
    r"\b[A-Za-z][A-Za-z0-9]*[0-9][A-Za-z0-9/-]*\b|\b[A-Z0-9][A-Z0-9/-]{2,}\b"
)


def _kw(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.IGNORECASE)


# --- keyword anchors ----------------------------------------------------------
# (field type, anchor regex, pattern weight, method label)
_KEYWORD_RULES: list[tuple[FieldType, re.Pattern[str], float, str]] = [
    (FieldType.MRP, _kw(r"\b(?:m\.?\s*r\.?\s*p\.?|maximum\s+retail\s+price)\b"), 1.0, "regex:mrp"),
    (FieldType.NET_QUANTITY, _kw(r"\bnet\s+(?:qty|quantity|wt|weight|contents?)\b"), 1.0,
     "regex:net-quantity"),
    (FieldType.BATCH_NUMBER,
     _kw(r"\b(?:batch(?:\s*(?:no|number))?|lot(?:\s*(?:no|number))?|b\.?\s*no)\b"), 0.95,
     "regex:batch"),
    (FieldType.MANUFACTURER_DETAILS, _kw(r"\b(?:mfd\.?|mfg\.?|manufactur\w*|made\s+by)\b"), 0.9,
     "regex:manufacturer"),
    (FieldType.PACKER_DETAILS, _kw(r"\b(?:packer|packed\s+by|packaged\s+by)\b"), 0.9,
     "regex:packer"),
    (FieldType.IMPORTER_DETAILS, _kw(r"\b(?:importer|imported\s+by)\b"), 0.9, "regex:importer"),
    (FieldType.ADDRESS, _kw(r"\b(?:factory\s+address|address\s+of|registered\s+office)\b"), 0.7,
     "regex:address"),
    (FieldType.COUNTRY_OF_ORIGIN, _kw(r"\bcountry\s+of\s+origin\b|\borigin\b"), 0.95,
     "regex:origin"),
    (FieldType.BRAND_NAME, _kw(r"\bbrand(?:\s*name)?\s*[:\-]"), 0.9, "regex:brand"),
]

# Date-keyword families: keyword -> field type. "date"/"on" is REQUIRED so
# that "Mfd by:" / "Mfg by:" fall through to the manufacturer keyword rule
# instead of being misread as date lines.
_DATE_RULES: list[tuple[re.Pattern[str], FieldType, str]] = [
    (_kw(r"\b(?:mfg\.?|mfd\.?|manufactur\w*)\s*(?:date|on)\b"),
     FieldType.DATE_OF_MANUFACTURE, "regex:date-of-manufacture"),
    (_kw(r"\b(?:pack\w*)\s*(?:date|on)\b|\bdate\s+of\s+pack\w*\b"),
     FieldType.DATE_OF_PACKING, "regex:date-of-packing"),
    (_kw(r"\bbest\s+before\b|\buse\s+by\b"), FieldType.BEST_BEFORE, "regex:best-before"),
    (_kw(r"\bexp(?:iry)?\b|\bexpires?\s+on\b"), FieldType.EXPIRY_DATE, "regex:expiry"),
]

_CARE_RE = _kw(r"\b(?:consumer\s+care|customer\s+care|toll[\s-]?free|helpline|contact\s+us)\b")


def _value_after_anchor(anchor: re.Match[str], text: str) -> str | None:
    """Text after an 'anchor: value' or 'anchor value' boundary, or None."""
    rest = text[anchor.end():].lstrip(" :=-–—\t")
    return rest.strip() or None


def _after_colon(text: str) -> str | None:
    if ":" in text:
        rest = text.split(":", 1)[1].strip(" -–—\t")
        return rest or None
    return None


class DeterministicFieldExtractor(FieldExtractionProvider):
    """Regex/keyword/typography extraction — deterministic by design."""

    def __init__(self, *, review_threshold: float = 0.6) -> None:
        self._review_threshold = review_threshold

    @property
    def review_threshold(self) -> float:
        return self._review_threshold

    @property
    def descriptor(self) -> ServiceDescriptor:
        return ServiceDescriptor(
            service_type=ModelServiceType.FIELD_EXTRACTOR,
            name="deterministic-regex",
            version="1.0.0",
            provider="legalmet",
        )

    def extract(self, *, ocr: OcrResult) -> list[FieldCandidate]:
        candidates: list[FieldCandidate] = []
        claimed_indices: set[int] = set()

        for index, line in enumerate(ocr.lines):
            candidate = self._extract_line(
                index, line.text, line.bbox, line.confidence, line.language
            )
            if candidate is not None:
                candidates.append(candidate)
                claimed_indices.add(index)

        candidates.extend(self._product_name_heuristic(ocr, claimed_indices))
        return candidates

    # --- per-line rules ------------------------------------------------------

    def _extract_line(
        self,
        index: int,
        raw_text: str,
        bbox,
        ocr_confidence: float,
        language: str | None,
    ) -> FieldCandidate | None:
        text = normalize_ocr_text(raw_text)
        if not text:
            return None
        lowered = text.lower()

        # Date keywords first: "Mfg Date" must not be swallowed by the
        # manufacturer rule.
        for keyword_re, field_type, method in _DATE_RULES:
            match = keyword_re.search(lowered)
            if match is None:
                continue
            value_match = _DATE_RE.search(text) or _DURATION_RE.search(text)
            return self._candidate(
                field_type=field_type,
                index=index,
                raw_text=raw_text,
                bbox=bbox,
                ocr_confidence=ocr_confidence,
                weight=0.95,
                method=method,
                normalized_value=value_match.group(0).strip() if value_match else None,
                language=language,
            )

        for field_type, keyword_re, weight, method in _KEYWORD_RULES:
            match = keyword_re.search(lowered)
            if match is None:
                continue
            normalized = self._value_for(field_type, text, match)
            return self._candidate(
                field_type=field_type,
                index=index,
                raw_text=raw_text,
                bbox=bbox,
                ocr_confidence=ocr_confidence,
                weight=weight,
                method=method,
                normalized_value=normalized,
                language=language,
            )

        if _CARE_RE.search(lowered):
            care_anchor = _CARE_RE.search(lowered)
            rest = _after_colon(text) or _value_after_anchor(care_anchor, lowered) or text
            return self._candidate(
                field_type=FieldType.CONSUMER_CARE,
                index=index,
                raw_text=raw_text,
                bbox=bbox,
                ocr_confidence=ocr_confidence,
                weight=0.95,
                method="regex:consumer-care",
                normalized_value=rest,
                language=language,
            )

        # Unanchored but distinctive tokens: emails are safe to claim, phones
        # and bare prices are plausible-but-uncertain (REVIEW_REQUIRED).
        email = _EMAIL_RE.search(text)
        if email is not None:
            return self._candidate(
                field_type=FieldType.CONSUMER_CARE,
                index=index,
                raw_text=raw_text,
                bbox=bbox,
                ocr_confidence=ocr_confidence,
                weight=0.95,
                method="regex:email",
                normalized_value=email.group(0),
                language=language,
            )
        phone = _PHONE_RE.search(text)
        if phone is not None:
            return self._candidate(
                field_type=FieldType.CONSUMER_CARE,
                index=index,
                raw_text=raw_text,
                bbox=bbox,
                ocr_confidence=ocr_confidence,
                weight=0.5,
                method="regex:phone",
                normalized_value=phone.group(0),
                language=language,
            )
        price = _PRICE_RE.search(text)
        if price is not None:
            return self._candidate(
                field_type=FieldType.MRP,
                index=index,
                raw_text=raw_text,
                bbox=bbox,
                ocr_confidence=ocr_confidence,
                weight=0.5,
                method="regex:price-unlabeled",
                normalized_value=self._format_price(price),
                unit="INR",
                language=language,
            )
        return None

    # --- helpers --------------------------------------------------------------

    @staticmethod
    def _value_for(field_type: FieldType, text: str, anchor: re.Match[str]) -> str | None:
        """Pull the normalized value for a keyword-anchored field."""
        if field_type == FieldType.MRP:
            match = _PRICE_RE.search(text)
            if match is None:
                return None
            return DeterministicFieldExtractor._format_price(match)
        if field_type == FieldType.NET_QUANTITY:
            match = _QUANTITY_RE.search(text)
            if match is None:
                return None
            return f"{match.group(1)} {match.group(2).lower()}"
        if field_type == FieldType.BATCH_NUMBER:
            rest = _after_colon(text)
            if rest is not None:
                return rest
            match = _BATCH_TOKEN_RE.search(text[anchor.end():])
            return match.group(0) if match else None
        # Free-text fields (manufacturer/packer/importer/address/origin/brand).
        return _after_colon(text) or _value_after_anchor(anchor, text)

    @staticmethod
    def _format_price(match: re.Match[str]) -> str:
        symbol, amount = match.group(1), match.group(2).replace(",", "")
        prefix = "₹" if symbol in ("₹", "₨") else f"{symbol.rstrip('.')} "
        return f"{prefix}{amount}"

    def _candidate(
        self,
        *,
        field_type: FieldType,
        index: int,
        raw_text: str,
        bbox,
        ocr_confidence: float,
        weight: float,
        method: str,
        normalized_value: str | None,
        language: str | None,
        unit: str | None = None,
    ) -> FieldCandidate:
        confidence = round(min(1.0, ocr_confidence * weight), 4)
        if normalized_value is None:
            status = ExtractionStatus.NOT_EXTRACTED
        elif confidence < self._review_threshold:
            status = ExtractionStatus.REVIEW_REQUIRED
        else:
            status = ExtractionStatus.DETECTED
        return FieldCandidate(
            field_type=field_type,
            raw_text=raw_text,
            confidence=confidence,
            bbox=bbox,
            normalized_value=normalized_value,
            unit=unit,
            status=status,
            source_index=index,
            method=method,
            language=language,
        )

    def _product_name_heuristic(
        self, ocr: OcrResult, claimed_indices: set[int]
    ) -> list[FieldCandidate]:
        """Largest text in the top part of the label is *probably* the product
        name. This is a typography heuristic, so the candidate is always
        REVIEW_REQUIRED — never asserted as fact."""
        if not ocr.lines:
            return []
        tallest = max(line.bbox.height for line in ocr.lines)
        best = None
        for index, line in enumerate(ocr.lines):
            if index in claimed_indices:
                continue
            if line.bbox.height >= 0.75 * tallest and line.bbox.y < 0.4:
                if best is None or line.bbox.height > ocr.lines[best].bbox.height:
                    best = index
        if best is None:
            return []
        line = ocr.lines[best]
        candidate = self._candidate(
            field_type=FieldType.PRODUCT_NAME,
            index=best,
            raw_text=line.text,
            bbox=line.bbox,
            ocr_confidence=line.confidence,
            weight=0.5,
            method="heuristic:typography",
            normalized_value=normalize_ocr_text(line.text),
            language=line.language,
        )
        # Heuristics never claim DETECTED regardless of the arithmetic.
        return [
            FieldCandidate(
                field_type=candidate.field_type,
                raw_text=candidate.raw_text,
                confidence=candidate.confidence,
                bbox=candidate.bbox,
                normalized_value=candidate.normalized_value,
                unit=candidate.unit,
                status=ExtractionStatus.REVIEW_REQUIRED,
                source_index=candidate.source_index,
                method=candidate.method,
                language=candidate.language,
            )
        ]
