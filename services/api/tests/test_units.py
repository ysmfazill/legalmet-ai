"""Unit vocabulary + normalization tests (UI-07).

Covers the contract (spec §5–§6):

* only mg/g/kg (mass) and ml/L (volume) are supported; anything else is an
  error — the unit is NEVER assumed
* 500 g vs 0.492 kg normalize to the same base and compare correctly
* mass vs volume are different dimensions: incomparable, never converted
* the observed difference is arithmetic in the DECLARED unit, labelled
  "observed" — never a legal deficiency
* no scientific notation ever reaches a human ('3E+1' regression)
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.core.errors import ValidationError
from app.services.verification.units import (
    normalize_quantity,
    normalize_unit,
    observed_difference,
    parse_declared_quantity,
    plain_decimal,
)


class TestNormalizeUnit:
    def test_supported_units_case_insensitive(self):
        assert normalize_unit("g") == "g"
        assert normalize_unit("KG") == "kg"
        assert normalize_unit(" Kg. ") == "kg"
        assert normalize_unit("ML") == "ml"
        assert normalize_unit("L") == "l"
        assert normalize_unit("lt") == "l"
        assert normalize_unit("Mg") == "mg"

    @pytest.mark.parametrize("unit", ["lb", "oz", "gm", "pcs", "µg", "", "g per"])
    def test_unsupported_unit_raises(self, unit):
        with pytest.raises(ValidationError) as exc:
            normalize_unit(unit)
        # The message must state the unit is never assumed (spec §5).
        assert "never assumed" in str(exc.value)

    def test_error_lists_supported_units(self):
        with pytest.raises(ValidationError) as exc:
            normalize_unit("lb")
        assert "mg" in str(exc.value) and "kg" in str(exc.value)


class TestNormalizeQuantity:
    def test_kg_normalizes_to_base_exactly(self):
        normalized = normalize_quantity("0.492", "kg")
        assert normalized.value == Decimal("492")
        assert normalized.base_unit == "g"
        assert normalized.dimension == "mass"

    def test_mg_normalizes_to_base(self):
        assert normalize_quantity(500, "mg").value == Decimal("0.5")

    def test_liters_normalize_to_ml(self):
        normalized = normalize_quantity("1.5", "L")
        assert normalized.value == Decimal("1500")
        assert normalized.dimension == "volume"

    def test_unsupported_unit_never_normalized(self):
        with pytest.raises(ValidationError):
            normalize_quantity(500, "lb")


class TestParseDeclaredQuantity:
    @pytest.mark.parametrize(
        ("text", "value", "unit"),
        [
            ("500 g", "500", "g"),
            ("500g", "500", "g"),
            ("0.492 kg", "0.492", "kg"),
            ("1,000 g", "1000", "g"),
            (" 250 ML ", "250", "ml"),
        ],
    )
    def test_parseable_pairs(self, text, value, unit):
        assert parse_declared_quantity(text) == (Decimal(value), unit)

    @pytest.mark.parametrize("text", ["500", "g", "abc g", "", None, "500 g net", "-"])
    def test_unparseable_returns_none(self, text):
        # None is a fact to surface, never an exception, never a guess.
        assert parse_declared_quantity(text) is None


class TestObservedDifference:
    def test_kg_measurement_against_g_declaration(self):
        observed = observed_difference("500 g", "0.492", "kg")
        assert observed["comparable"] is True
        # Difference expressed in the DECLARED unit.
        assert observed["difference"] == "-8"
        assert observed["percentDifference"] == "-1.6"
        assert observed["declared"]["normalized"] == "500 g"
        assert observed["measured"]["normalized"] == "492 g"
        assert "NOT a legal deficiency" in observed["note"]

    def test_surplus_measured_is_positive(self):
        observed = observed_difference("500 g", 505, "g")
        assert observed["comparable"] is True
        assert observed["difference"] == "5"
        assert observed["percentDifference"] == "1"

    def test_mass_vs_volume_is_incomparable(self):
        observed = observed_difference("500 g", "0.492", "L")
        assert observed["comparable"] is False
        assert "cannot be compared" in observed["reason"]
        assert "difference" not in observed

    def test_unparseable_declaration_is_incomparable(self):
        observed = observed_difference("approx half kilo", 492, "g")
        assert observed["comparable"] is False
        assert "parseable" in observed["reason"]

    def test_unsupported_measured_unit_is_incomparable(self):
        observed = observed_difference("500 g", 1.1, "lb")
        assert observed["comparable"] is False
        # The unit error is surfaced, never silently converted.
        assert "Unsupported quantity unit" in observed["reason"]

    def test_zero_declaration_has_no_percent(self):
        observed = observed_difference("0 g", 5, "g")
        assert observed["comparable"] is False
        assert "percent difference" in observed["reason"]


class TestPlainDecimal:
    def test_no_scientific_notation(self):
        # Decimal('30').normalize() is '3E+1' — humans must never see that.
        assert plain_decimal(Decimal(30)) == "30"
        assert plain_decimal(Decimal("22.50")) == "22.5"
        assert plain_decimal(Decimal("0.492") * Decimal("1000")) == "492"
