"""Quantity unit handling for physical measurements (UI-07).

Deterministic, Decimal-safe unit vocabulary + normalization. Principles:

* Only the units the application already uses for quantity declarations are
  accepted (mg / g / kg — mass; ml / L — volume). Anything else is an error,
  never a silent assumption.
* Mass and volume are DIFFERENT dimensions: "500 g" vs "0.492 L" is not a
  comparable pair and is reported as such, never guessed.
* Observed difference is pure arithmetic on normalized values — it is labelled
  "observed", never a legal deficiency (that judgement needs the regulatory
  evaluation + the inspector).
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import NamedTuple

from app.core.errors import ValidationError

# unit → (dimension, base unit, factor to base). Kept as exact Decimals so
# normalization is reproducible (0.492 kg → 492 g exactly, never 491.9999…).
_SUPPORTED_UNITS: dict[str, tuple[str, str, Decimal]] = {
    "mg": ("mass", "g", Decimal("0.001")),
    "g": ("mass", "g", Decimal("1")),
    "kg": ("mass", "g", Decimal("1000")),
    "ml": ("volume", "ml", Decimal("1")),
    "l": ("volume", "ml", Decimal("1000")),
}

SUPPORTED_QUANTITY_UNITS = sorted(_SUPPORTED_UNITS)


class NormalizedQuantity(NamedTuple):
    value: Decimal
    base_unit: str
    dimension: str


def normalize_unit(unit: str) -> str:
    """Canonical spelling of a supported unit (case-insensitive)."""
    candidate = (unit or "").strip().lower().rstrip(".")
    if candidate == "lt":
        candidate = "l"
    if candidate not in _SUPPORTED_UNITS:
        raise ValidationError(
            f"Unsupported quantity unit '{unit}'. Supported units: "
            f"{', '.join(SUPPORTED_QUANTITY_UNITS)}. The unit is never assumed."
        )
    return candidate


def normalize_quantity(value, unit: str) -> NormalizedQuantity:
    """Normalize (value, unit) to its dimension's base unit (Decimal-safe)."""
    canonical = normalize_unit(unit)
    dimension, base, factor = _SUPPORTED_UNITS[canonical]
    try:
        number = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValidationError(
            f"'{value}' is not a deterministically parseable quantity."
        ) from exc
    return NormalizedQuantity(number * factor, base, dimension)


# "500 g" / "500g" / "500 gm"(unsupported gm → error later) / "0.492 kg"
_DECLARED_RE = re.compile(
    r"^\s*(-?[\d,]+(?:\.\d+)?)\s*([a-zA-Zµμ.]+)\s*$"
)


def parse_declared_quantity(text: str | None) -> tuple[Decimal, str] | None:
    """Deterministically split a declared value like ``500 g``.

    Returns ``(number, unit)`` or None when the text is not a clean
    quantity+unit pair (e.g. no unit at all, or several tokens). Commas are
    treated as thousands separators. The unit is NOT validated here — callers
    decide what an unparseable or unsupported declaration means for them.
    """
    if not text:
        return None
    match = _DECLARED_RE.match(str(text).strip())
    if match is None:
        return None
    try:
        number = Decimal(match.group(1).replace(",", ""))
    except InvalidOperation:
        return None
    return number, match.group(2).lower().rstrip(".")


def observed_difference(
    declared_text: str | None, measured_value, measured_unit: str
) -> dict | None:
    """The OBSERVED difference between a declaration and a measurement.

    Pure arithmetic, computed on normalized values so ``500 g`` vs
    ``0.492 kg`` compares correctly. Returns a dict with the difference in
    the DECLARED unit, the percent difference relative to the declaration,
    and the honesty label — or None when the pair cannot be compared
    deterministically (unparseable declaration / dimension mismatch), in
    which case ``reason`` explains why. Never raises: an incomparable pair is
    a fact to surface, not an error.
    """
    parsed = parse_declared_quantity(declared_text)
    if parsed is None:
        return {
            "comparable": False,
            "reason": (
                f"The declared value '{declared_text}' is not a deterministically "
                "parseable quantity+unit pair — no difference is computed."
            ),
        }
    declared_number, declared_unit_raw = parsed
    try:
        declared_unit = normalize_unit(declared_unit_raw)
        measured = normalize_quantity(measured_value, measured_unit)
        declared = normalize_quantity(declared_number, declared_unit)
    except ValidationError as exc:
        return {"comparable": False, "reason": str(exc)}
    if declared.dimension != measured.dimension:
        return {
            "comparable": False,
            "reason": (
                f"The declaration is in a {declared.dimension} unit "
                f"({declared_unit}) and the measurement in a {measured.dimension} "
                f"unit ({measured_unit}) — the two cannot be compared and the "
                "system does not assume a conversion."
            ),
        }
    if declared.value == 0:
        return {
            "comparable": False,
            "reason": "The declared quantity is zero — a percent difference "
                      "cannot be computed.",
        }
    # Express the difference in the DECLARED unit so the inspector reads it
    # against the label they photographed.
    _, declared_base, declared_factor = _SUPPORTED_UNITS[declared_unit]
    difference = (measured.value - declared.value) / declared_factor
    percent = (measured.value - declared.value) / declared.value * Decimal("100")
    return {
        "comparable": True,
        "declared": {
            "value": str(declared_number),
            "unit": declared_unit,
            "normalized": f"{plain_decimal(declared.value)} {declared_base}",
        },
        "measured": {
            "value": str(Decimal(str(measured_value))),
            "unit": normalize_unit(measured_unit),
            "normalized": f"{plain_decimal(measured.value)} {measured_base(measured_unit)}",
        },
        "difference": plain_decimal(difference),
        "percentDifference": plain_decimal(
            percent.quantize(Decimal("0.01"))
        ),
        "note": (
            "Observed difference — arithmetic only. This is NOT a legal "
            "deficiency; only the regulatory evaluation and the inspector "
            "may draw a conclusion."
        ),
    }


def measured_base(unit: str) -> str:
    return _SUPPORTED_UNITS[normalize_unit(unit)][1]


def plain_decimal(value: Decimal) -> str:
    """Canonical string form: trailing zeros stripped, never scientific
    notation (Decimal('30').normalize() is '3E+1' — unreadable for humans)."""
    return format(value.normalize(), "f")
