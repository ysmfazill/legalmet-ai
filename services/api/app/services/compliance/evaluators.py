"""Deterministic rule-type evaluators (Prompt 6, Phase 4/7/8).

One function per ``DeterministicRuleType``. Contract:

    evaluate_*(field, configuration) -> EvaluatorOutcome

``field`` is the ExtractedField evidence (or None — absence), with its
RAW / NORMALIZED / UNIT / CONFIDENCE preserved verbatim. The evaluators NEVER
repair a value, never invent a value, and never call any model. Ambiguous
values return ``AMBIGUOUS`` which the engine converts to REVIEW_REQUIRED.

All numeric handling is decimal-safe: money and quantities are parsed via
``decimal.Decimal`` — floats are never used for comparisons.

Every evaluator answers with a deterministic outcome + a human-readable reason
fragment used verbatim in the finding explanation.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from app.core.enums import DeterministicRuleType

# ---------------------------------------------------------------------------
# Outcome vocabulary — deliberately closed. PASS/FAIL alone are never enough:
# the engine must distinguish "checked and passed", "checked and failed",
# "could not check" and "value too ambiguous to check".
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EvaluatorOutcome:
    passed: bool | None  # None → indeterminate (INSUFFICIENT/AMBIGUOUS/ERROR)
    reason: str
    expected: str | None = None
    detail: dict[str, Any] | None = None


def _outcome(
    passed: bool | None, reason: str, expected: str | None = None, **detail: Any
) -> EvaluatorOutcome:
    return EvaluatorOutcome(
        passed=passed, reason=reason, expected=expected, detail=detail or None
    )


# --- shared deterministic parsing helpers -----------------------------------


_MRP_RE = re.compile(
    r"(?:mrp|maximum\s+retail\s+price|retail\s+price)?\s*"
    r"(?:₹|rs\.?|inr)\s*([\d,]+(?:\.\d{1,2})?)"
    r"(?:\s*(?:inclusive\s+of|incl\.?|incl)\s*(?:all\s+)?taxes?)?",
    re.IGNORECASE,
)
_INCLUSIVE_RE = re.compile(r"inclusive\s+of\s*(?:all\s+)?taxes?", re.IGNORECASE)
_DATE_RE = re.compile(
    r"(\d{1,2})[/\-.](\d{1,2}|[A-Za-z]{3,})[/\-.](\d{2,4})"
    r"|(\d{1,2}|[A-Za-z]{3,})[/\-.](\d{4})"
    r"|([A-Za-z]{3,})[\s\-]+(\d{4})"
    r"|(\d{1,2})[\s\-]+([A-Za-z]{3,})",
    re.IGNORECASE,
)
_PHONE_RE = re.compile(r"(?:\+91[\s-]?)?[6-9]\d{4}[\s-]?\d{5}")
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_COUNTRY_TOKEN_RE = re.compile(
    r"country\s+of\s+origin\s*[:\-]?\s*([A-Za-z][A-Za-z\s]{1,40})", re.IGNORECASE
)


def _decimal(value: str | None) -> Decimal | None:
    """Decimal-safe parse; returns None when the text is not a clean number."""
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def _text(field) -> str | None:
    """Best deterministic text of a field: human correction, else normalized, else raw.

    Prompt 8: when an inspector has corrected the value, the correction IS the
    verified reading of the label and therefore what evaluation consumes. The
    original AI values remain untouched on the field record.
    """
    if field is None:
        return None
    value = (
        getattr(field, "corrected_value", None)
        or getattr(field, "normalized_value", None)
        or getattr(field, "raw_text", None)
    )
    return str(value).strip() if value else None


def _raw(field) -> str | None:
    """Raw reading consumed by evaluation — the human correction when one exists.

    Format checks (e.g. MRP wording) must evaluate the corrected reading after
    an inspector correction, because the correction is what the human verified
    on the label. The ORIGINAL OCR raw text is never overwritten on the field.
    """
    if field is None:
        return None
    corrected = getattr(field, "corrected_value", None)
    raw = corrected if corrected is not None else getattr(field, "raw_text", None)
    return str(raw).strip() if raw else None


def _human_corrected(field) -> bool:
    """True when a human correction has been recorded for this field."""
    return field is not None and getattr(field, "corrected_value", None) is not None


def _field_confidence(field) -> float | None:
    return getattr(field, "confidence", None) if field is not None else None


# --- evaluators ---------------------------------------------------------------
# NOTE: every evaluator receives `field=None` when NO field of the requirement's
# field_key was extracted at all — that is the FIELD_NOT_FOUND path handled by
# the engine (PRESENCE/REQUIRED types report it; nothing else may guess).


def evaluate_presence(field, config: dict) -> EvaluatorOutcome:
    """FIELD_REQUIRED / PRESENCE — is the declaration present and non-empty?"""
    if field is None:
        return _outcome(
            None,
            "No field of this type was extracted from any image — the declaration "
            "was not found by perception (FIELD_NOT_FOUND). This is not evidence "
            "that the declaration is absent from the package.",
            expected="A detected declaration of this type.",
            absence="FIELD_NOT_FOUND",
        )
    status = getattr(field, "status", None)
    if status == "NOT_EXTRACTED":
        return _outcome(
            None,
            "Perception located this declaration type but could not read a usable "
            "value (NOT_EXTRACTED). Missing OCR is never treated as absence.",
            expected="A readable value for the declaration.",
            absence="FIELD_NOT_FOUND",
        )
    text = _text(field)
    if not text:
        return _outcome(
            None,
            "The field exists but carries no usable value (empty after "
            "normalization) — insufficient evidence to conclude either way.",
            expected="A non-empty declaration value.",
            outcome_code="INSUFFICIENT_EVIDENCE",
        )
    if _human_corrected(field):
        # Prompt 8: a human-confirmed correction IS verified evidence — the
        # perception confidence/review flags describe the ORIGINAL AI reading
        # and no longer gate this requirement.
        return _outcome(
            True,
            f"Declaration detected with value '{text}' "
            "(human-confirmed correction).",
        )
    conf = _field_confidence(field)
    if status == "REVIEW_REQUIRED" or (conf is not None and conf < 0.6):
        return _outcome(
            None,
            f"A value was read ('{text}') but perception marked it for review "
            f"(status={status}, OCR confidence={conf}) — a human must confirm the "
            "value before any conclusion.",
            expected="A confidently-read declaration value.",
            outcome_code="INSUFFICIENT_EVIDENCE",
        )
    return _outcome(True, f"Declaration detected with value '{text}'.")


def evaluate_field_required(field, config: dict) -> EvaluatorOutcome:
    """FIELD_REQUIRED — mandatory declaration must be present."""
    return evaluate_presence(field, config)


def evaluate_field_not_required(field, config: dict) -> EvaluatorOutcome:
    """FIELD_NOT_REQUIRED — the declaration must NOT carry this field."""
    if field is None:
        return _outcome(True, "No such field was extracted — as expected.")
    text = _text(field)
    if not text:
        return _outcome(True, "The field carries no usable value — as expected.")
    return _outcome(False, f"An unexpected value was found: '{text}'.")


def evaluate_text_match(field, config: dict) -> EvaluatorOutcome:
    """TEXT_MATCH — detected text must equal the configured expected text."""
    expected = config.get("expected")
    if not expected:
        return _outcome(None, "Rule configuration is missing 'expected' — the rule "
                              "cannot be evaluated.", outcome_code="RULE_EXECUTION_FAILED")
    text = _text(field)
    if field is None or not text:
        return _outcome(
            None,
            "No usable text was detected for this requirement.",
            expected=str(expected),
            outcome_code="INSUFFICIENT_EVIDENCE",
        )
    ok = text.strip().casefold() == str(expected).strip().casefold()
    return _outcome(
        ok,
        f"Detected '{text}' "
        f"{'matches' if ok else 'does not match'} the required text '{expected}'.",
        expected=str(expected),
    )


def evaluate_text_pattern(field, config: dict) -> EvaluatorOutcome:
    """TEXT_PATTERN — detected text must match a configured regular expression."""
    pattern = config.get("pattern")
    if not pattern:
        return _outcome(None, "Rule configuration is missing 'pattern' — the rule "
                              "cannot be evaluated.", outcome_code="RULE_EXECUTION_FAILED")
    text = _text(field)
    if field is None or not text:
        return _outcome(
            None,
            "No usable text was detected for this requirement.",
            expected=f"Text matching /{pattern}/",
            outcome_code="INSUFFICIENT_EVIDENCE",
        )
    try:
        matched = re.search(str(pattern), text, re.IGNORECASE) is not None
    except re.error as exc:
        return _outcome(
            None,
            f"The configured pattern could not be compiled ({exc}) — the rule "
            "cannot be evaluated.",
            outcome_code="RULE_EXECUTION_FAILED",
        )
    return _outcome(
        matched,
        f"Detected text '{text}' "
        f"{'matches' if matched else 'does not match'} the required pattern.",
        expected=f"Text matching /{pattern}/",
    )


def evaluate_numeric_value(field, config: dict) -> EvaluatorOutcome:
    """NUMERIC_VALUE — the declared number must be present and parseable.

    Decimal-safe: the value is compared as ``Decimal``, never as float. A value
    that cannot be parsed deterministically is AMBIGUOUS, not wrong.
    """
    text = _text(field)
    if field is None or not text:
        return _outcome(
            None,
            "No usable value was detected for this requirement.",
            expected="A numeric value.",
            outcome_code="INSUFFICIENT_EVIDENCE",
        )
    number = _decimal(text)
    if number is None:
        return _outcome(
            None,
            f"The detected value '{text}' is not a deterministically parseable "
            "number (AMBIGUOUS_VALUE) — it is neither accepted nor rejected.",
            expected="A numeric value.",
            outcome_code="AMBIGUOUS_VALUE",
        )
    return _outcome(
        True,
        f"A numeric value was detected: {number} (raw '{text}').",
        detected_number=str(number),
    )


def evaluate_unit_match(field, config: dict) -> EvaluatorOutcome:
    """UNIT_MATCH — the declared unit must be one of the configured units."""
    units = config.get("units")
    if not units:
        return _outcome(None, "Rule configuration is missing 'units' — the rule "
                              "cannot be evaluated.", outcome_code="RULE_EXECUTION_FAILED")
    unit = getattr(field, "unit", None) if field is not None else None
    if not unit:
        # Deterministic fallback: look for a trailing unit token in the RAW
        # text (the normalized value is often just the number).
        raw_text = _raw(field) or ""
        match = re.search(r"\b(k?g|ml|l|pcs|units?)\b", raw_text, re.IGNORECASE)
        if match:
            unit = match.group(1).lower()
    if not unit:
        return _outcome(
            None,
            "No unit could be determined from the detected value.",
            expected=f"One of: {', '.join(map(str, units))}",
            outcome_code="INSUFFICIENT_EVIDENCE",
        )
    norm = str(unit).strip().lower().rstrip(".")
    allowed = [str(u).strip().lower() for u in units]
    ok = norm in allowed
    return _outcome(
        ok,
        f"Detected unit '{norm}' "
        f"{'is' if ok else 'is not'} one of the accepted units {allowed}.",
        expected=f"One of: {', '.join(allowed)}",
    )


def evaluate_mrp_format(field, config: dict) -> EvaluatorOutcome:
    """MRP_FORMAT — 'MRP ₹__ (inclusive of all taxes)' shape, deterministically.

    Never invents a price: the check is purely structural (currency symbol +
    parseable decimal amount; the 'inclusive of all taxes' wording is checked
    on the RAW text because wording cannot be reconstructed from a number).
    """
    raw = _raw(field)
    if field is None or not raw:
        return _outcome(
            None,
            "No MRP text was detected for this requirement.",
            expected="MRP ₹__ (inclusive of all taxes)",
            outcome_code="INSUFFICIENT_EVIDENCE",
        )
    match = _MRP_RE.search(raw)
    if match is None:
        # A price marker (₹ / Rs / MRP) with unreadable digits is AMBIGUOUS —
        # the label declares a price, OCR just failed to read it. No marker at
        # all is a structural fail of the declaration format.
        marker = re.search(r"(₹|rs\.?|inr|mrp)", raw, re.IGNORECASE)
        if marker is not None:
            return _outcome(
                None,
                f"The text '{raw}' declares a price but the amount could not be "
                "read deterministically (AMBIGUOUS_VALUE).",
                expected="MRP ₹__ (inclusive of all taxes)",
                outcome_code="AMBIGUOUS_VALUE",
            )
        return _outcome(
            False,
            f"The detected text '{raw}' does not contain a deterministically "
            "parseable price (currency symbol + amount).",
            expected="MRP ₹__ (inclusive of all taxes)",
        )
    amount = match.group(1)
    number = _decimal(amount)
    if number is None:
        return _outcome(
            None,
            f"A price-like token '{amount}' was found but is not a deterministically "
            "parseable number (AMBIGUOUS_VALUE).",
            expected="MRP ₹__ (inclusive of all taxes)",
            outcome_code="AMBIGUOUS_VALUE",
        )
    inclusive = _INCLUSIVE_RE.search(raw) is not None
    if not inclusive:
        return _outcome(
            False,
            f"An MRP of {number} was read from '{raw}', but the text does not state "
            "'inclusive of all taxes'.",
            expected="MRP ₹__ (inclusive of all taxes)",
            detected_amount=str(number),
        )
    return _outcome(
        True,
        f"MRP {number} declared with 'inclusive of all taxes' wording (raw: '{raw}').",
        expected="MRP ₹__ (inclusive of all taxes)",
        detected_amount=str(number),
    )


def evaluate_date_format(field, config: dict) -> EvaluatorOutcome:
    """DATE_FORMAT — month/year (or full date) in a recognized deterministic shape."""
    text = _text(field)
    if field is None or not text:
        return _outcome(
            None,
            "No date text was detected for this requirement.",
            expected="A month-and-year (or full) date declaration.",
            outcome_code="INSUFFICIENT_EVIDENCE",
        )
    match = _DATE_RE.search(text)
    if match is None:
        return _outcome(
            False,
            f"The detected text '{text}' does not match a recognized date shape "
            "(dd/mm/yyyy, 'Mon YYYY', 'dd Mon').",
            expected="A month-and-year (or full) date declaration.",
        )
    return _outcome(
        True,
        f"A date-shaped declaration was detected: '{match.group(0)}' "
        f"(from '{text}').",
        expected="A month-and-year (or full) date declaration.",
        matched=match.group(0),
    )


def evaluate_contact_format(field, config: dict) -> EvaluatorOutcome:
    """CONTACT_FORMAT — a phone number AND an e-mail address must be present.

    Rule 6(2) consumer-care declarations need name/address/phone/e-mail; this
    evaluator checks the two machine-checkable channels deterministically.
    """
    text = _text(field)
    raw = _raw(field)
    if field is None or not (text or raw):
        return _outcome(
            None,
            "No consumer-care text was detected for this requirement.",
            expected="Telephone number and e-mail address.",
            outcome_code="INSUFFICIENT_EVIDENCE",
        )
    haystack = f"{text or ''} {raw or ''}"
    has_phone = _PHONE_RE.search(haystack) is not None
    has_email = _EMAIL_RE.search(haystack) is not None
    if has_phone and has_email:
        return _outcome(
            True,
            "Both a telephone number and an e-mail address were detected in the "
            f"text '{text}'.",
            expected="Telephone number and e-mail address.",
        )
    missing = []
    if not has_phone:
        missing.append("telephone number")
    if not has_email:
        missing.append("e-mail address")
    return _outcome(
        False,
        f"The consumer-care text '{text}' does not contain a recognizable "
        f"{' or '.join(missing)}.",
        expected="Telephone number and e-mail address.",
    )


def evaluate_declaration_format(field, config: dict) -> EvaluatorOutcome:
    """DECLARATION_FORMAT — non-empty text of at least the configured length.

    Used for free-form declarations (manufacturer name/address, generic name)
    where the law requires a plain, legible statement rather than a number.
    """
    min_words = int(config.get("minWords", 2))
    text = _text(field)
    if field is None or not text:
        return _outcome(
            None,
            "No declaration text was detected for this requirement.",
            expected=f"A plain declaration of at least {min_words} words.",
            outcome_code="INSUFFICIENT_EVIDENCE",
        )
    words = [w for w in re.split(r"\s+", text) if w]
    if len(words) < min_words:
        return _outcome(
            False,
            f"The declaration '{text}' has {len(words)} word(s) — fewer than the "
            f"{min_words} expected for a plain name/address statement.",
            expected=f"A plain declaration of at least {min_words} words.",
        )
    return _outcome(
        True,
        f"A {len(words)}-word declaration was detected: '{text}'.",
        expected=f"A plain declaration of at least {min_words} words.",
    )


def evaluate_range(field, config: dict) -> EvaluatorOutcome:
    """RANGE — a numeric value must lie within [min, max] (Decimal-safe)."""
    if "min" not in config and "max" not in config:
        return _outcome(None, "Rule configuration has neither 'min' nor 'max' — the "
                              "rule cannot be evaluated.", outcome_code="RULE_EXECUTION_FAILED")
    text = _text(field)
    if field is None or not text:
        return _outcome(
            None,
            "No usable value was detected for this requirement.",
            expected=f"A value in [{config.get('min', '−∞')}, {config.get('max', '+∞')}].",
            outcome_code="INSUFFICIENT_EVIDENCE",
        )
    number = _decimal(text)
    if number is None:
        # Numbers may hide inside a longer declaration — extract the first
        # numeric token deterministically.
        token = re.search(r"-?[\d,]+(?:\.\d+)?", text)
        if token is None:
            return _outcome(
                None,
                f"The detected value '{text}' contains no deterministically "
                "parseable number (AMBIGUOUS_VALUE).",
                outcome_code="AMBIGUOUS_VALUE",
            )
        number = _decimal(token.group(0))
    minimum = _decimal(str(config["min"])) if "min" in config else None
    maximum = _decimal(str(config["max"])) if "max" in config else None
    ok = True
    if minimum is not None and number < minimum:
        ok = False
    if maximum is not None and number > maximum:
        ok = False
    return _outcome(
        ok,
        f"Detected numeric value {number} is "
        f"{'within' if ok else 'outside'} the range "
        f"[{minimum if minimum is not None else '−∞'}, "
        f"{maximum if maximum is not None else '+∞'}].",
        expected=f"A value in [{minimum if minimum is not None else '−∞'}, "
                 f"{maximum if maximum is not None else '+∞'}].",
    )


def evaluate_comparison(field, config: dict) -> EvaluatorOutcome:
    """COMPARISON — value OPERATOR threshold (Decimal-safe), e.g. price > 0."""
    operator = str(config.get("operator", "")).strip()
    threshold = _decimal(str(config.get("value"))) if config.get("value") is not None else None
    if operator not in {"<", "<=", ">", ">=", "=", "==", "!="} or threshold is None:
        return _outcome(
            None,
            "Rule configuration is missing a valid 'operator'/'value' — the rule "
            "cannot be evaluated.",
            outcome_code="RULE_EXECUTION_FAILED",
        )
    text = _text(field)
    if field is None or not text:
        return _outcome(
            None,
            "No usable value was detected for this requirement.",
            expected=f"{operator} {threshold}",
            outcome_code="INSUFFICIENT_EVIDENCE",
        )
    number = _decimal(text)
    if number is None:
        # Numbers may hide inside a longer declaration (currency symbols,
        # units) — extract the first numeric token deterministically, exactly
        # like RANGE does.
        token = re.search(r"-?[\d,]+(?:\.\d+)?", text)
        if token is None:
            return _outcome(
                None,
                f"The detected value '{text}' is not a deterministically parseable "
                "number (AMBIGUOUS_VALUE).",
                expected=f"{operator} {threshold}",
                outcome_code="AMBIGUOUS_VALUE",
            )
        number = _decimal(token.group(0))
        if number is None:
            return _outcome(
                None,
                f"The detected value '{text}' is not a deterministically parseable "
                "number (AMBIGUOUS_VALUE).",
                expected=f"{operator} {threshold}",
                outcome_code="AMBIGUOUS_VALUE",
            )
    ops = {
        "<": lambda a, b: a < b,
        "<=": lambda a, b: a <= b,
        ">": lambda a, b: a > b,
        ">=": lambda a, b: a >= b,
        "=": lambda a, b: a == b,
        "==": lambda a, b: a == b,
        "!=": lambda a, b: a != b,
    }
    ok = ops[operator](number, threshold)
    return _outcome(
        ok,
        f"Detected value {number} {'satisfies' if ok else 'does not satisfy'} "
        f"{operator} {threshold}.",
        expected=f"{operator} {threshold}",
    )


_EVALUATORS = {
    DeterministicRuleType.PRESENCE.value: evaluate_presence,
    DeterministicRuleType.FIELD_REQUIRED.value: evaluate_field_required,
    DeterministicRuleType.FIELD_NOT_REQUIRED.value: evaluate_field_not_required,
    DeterministicRuleType.TEXT_MATCH.value: evaluate_text_match,
    DeterministicRuleType.TEXT_PATTERN.value: evaluate_text_pattern,
    DeterministicRuleType.NUMERIC_VALUE.value: evaluate_numeric_value,
    DeterministicRuleType.UNIT_MATCH.value: evaluate_unit_match,
    DeterministicRuleType.MRP_FORMAT.value: evaluate_mrp_format,
    DeterministicRuleType.DATE_FORMAT.value: evaluate_date_format,
    DeterministicRuleType.CONTACT_FORMAT.value: evaluate_contact_format,
    DeterministicRuleType.DECLARATION_FORMAT.value: evaluate_declaration_format,
    DeterministicRuleType.RANGE.value: evaluate_range,
    DeterministicRuleType.COMPARISON.value: evaluate_comparison,
}

assert set(_EVALUATORS) == {t.value for t in DeterministicRuleType}, (
    "every DeterministicRuleType must have exactly one evaluator"
)


def get_evaluator(rule_type: str):
    """Return the evaluator for a rule type, or None if the type is unknown."""
    return _EVALUATORS.get(rule_type)


def registered_rule_types() -> list[str]:
    return sorted(_EVALUATORS)
