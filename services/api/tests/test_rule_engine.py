"""Deterministic rule engine — the ONLY component that concludes compliance.

These tests pin the confidence & image-quality policy that keeps the system
from asserting a legal conclusion it cannot support. They are fully
deterministic (no DB, no mocks with randomness).
"""
from __future__ import annotations

import uuid

import pytest

from app.core.enums import ComplianceStatus, FieldType, ImageQualityStatus
from app.services.interfaces import FieldObservation, ImageQualityResult, RuleSpec
from app.services.rules.engine import DeterministicRuleEngine
from app.services.rules.validators import (
    field_present,
    numeric_positive,
    pattern_match,
    registered_validators,
)

THRESHOLD = 0.6


def _spec(validator: str, field_type: FieldType | None, **params) -> RuleSpec:
    return RuleSpec(
        rule_id=uuid.uuid4(),
        rule_version_id=uuid.uuid4(),
        rule_code="DEMO-TEST",
        requirement_summary="DEMO requirement (not a real legal rule).",
        validation_logic_ref=validator,
        target_field_type=field_type,
        params=params,
    )


def _obs(field_type: FieldType, text: str, confidence: float) -> FieldObservation:
    return FieldObservation(
        id=uuid.uuid4(), field_type=field_type, raw_text=text, confidence=confidence
    )


def _quality(status: ImageQualityStatus, score: float = 0.9) -> ImageQualityResult:
    return ImageQualityResult(status=status, score=score)


@pytest.fixture()
def engine() -> DeterministicRuleEngine:
    return DeterministicRuleEngine()


def _run(engine, observations, spec, quality):
    return engine.validate(
        observations=observations,
        rules=[spec],
        quality=quality,
        confidence_threshold=THRESHOLD,
    )[0]


def test_present_high_confidence_ok_quality_is_compliant(engine):
    obs = [_obs(FieldType.MRP, "MRP Rs 199", 0.95)]
    result = _run(engine, obs, _spec("field_present", FieldType.MRP), _quality(ImageQualityStatus.OK))
    assert result.status == ComplianceStatus.COMPLIANT


def test_missing_declaration_is_potential_violation(engine):
    result = _run(engine, [], _spec("field_present", FieldType.NET_QUANTITY), _quality(ImageQualityStatus.OK))
    assert result.status == ComplianceStatus.POTENTIAL_VIOLATION


def test_low_confidence_never_asserts_a_conclusion(engine):
    obs = [_obs(FieldType.MRP, "MRP Rs 199", 0.40)]  # below threshold
    result = _run(engine, obs, _spec("field_present", FieldType.MRP), _quality(ImageQualityStatus.OK))
    assert result.status == ComplianceStatus.LOW_CONFIDENCE


def test_insufficient_image_quality_overrides_everything(engine):
    obs = [_obs(FieldType.MRP, "MRP Rs 199", 0.95)]
    result = _run(
        engine, obs, _spec("field_present", FieldType.MRP),
        _quality(ImageQualityStatus.INSUFFICIENT, 0.25),
    )
    assert result.status == ComplianceStatus.IMAGE_QUALITY_INSUFFICIENT


def test_failed_check_on_degraded_image_defers_to_review(engine):
    # A missing field (fails) but on a glare-degraded image must NOT be asserted
    # as a violation — it becomes REVIEW_REQUIRED.
    result = _run(
        engine, [], _spec("field_present", FieldType.NET_QUANTITY),
        _quality(ImageQualityStatus.GLARE, 0.5),
    )
    assert result.status == ComplianceStatus.REVIEW_REQUIRED


def test_indeterminate_validator_requires_review(engine):
    # non_empty_text with no observation -> passed is None -> REVIEW_REQUIRED.
    result = _run(engine, [], _spec("non_empty_text", FieldType.GENERIC_NAME), _quality(ImageQualityStatus.OK))
    assert result.status == ComplianceStatus.REVIEW_REQUIRED


def test_unknown_validator_ref_is_safe(engine):
    result = _run(engine, [], _spec("no_such_validator", FieldType.MRP), _quality(ImageQualityStatus.OK))
    assert result.status == ComplianceStatus.REVIEW_REQUIRED
    assert result.validator_output.get("known") is False


def test_rationale_carries_demo_marker(engine):
    obs = [_obs(FieldType.MRP, "MRP Rs 199", 0.95)]
    result = _run(engine, obs, _spec("field_present", FieldType.MRP), _quality(ImageQualityStatus.OK))
    assert "DEMO DATA — NOT LEGAL ADVICE" in result.rationale


# --- Validator units -------------------------------------------------------


def test_field_present_variants():
    spec = _spec("field_present", FieldType.MRP)
    assert field_present([_obs(FieldType.MRP, "Rs 10", 0.9)], spec).passed is True
    assert field_present([], spec).passed is False
    empty = field_present([_obs(FieldType.MRP, "   ", 0.9)], spec)
    assert empty.passed is False


def test_numeric_positive_variants():
    spec = _spec("numeric_positive", FieldType.NET_QUANTITY)
    assert numeric_positive([_obs(FieldType.NET_QUANTITY, "500", 0.9)], spec).passed is True
    assert numeric_positive([_obs(FieldType.NET_QUANTITY, "abc", 0.9)], spec).passed is None
    assert numeric_positive([], spec).passed is None


def test_pattern_match_uses_configured_pattern():
    spec = _spec("pattern_match", FieldType.BATCH_NUMBER, pattern=r"^[A-Z]{3}-\d+$")
    assert pattern_match([_obs(FieldType.BATCH_NUMBER, "DMO-2231", 0.9)], spec).passed is True
    assert pattern_match([_obs(FieldType.BATCH_NUMBER, "nope", 0.9)], spec).passed is False


def test_validator_registry_is_generic_only():
    # The registry holds generic structural validators, not encoded legal rules.
    assert set(registered_validators()) == {
        "field_present",
        "non_empty_text",
        "numeric_positive",
        "pattern_match",
    }
