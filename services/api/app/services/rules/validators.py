"""Deterministic validators referenced by rules via ``validation_logic_ref``.

These are GENERIC, structural validators (presence, non-empty, numeric,
pattern) — deliberately NOT encodings of any specific legal requirement. A rule
row in the Regulatory Knowledge System points at one of these by name and
supplies its parameters. This keeps *rule data* (which can change via
amendments) fully separate from *validation code*.

Real, verified legal validators will be added the same way in a later phase.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from uuid import UUID

from app.services.interfaces import FieldObservation, RuleSpec


@dataclass
class ValidatorResult:
    # True = satisfied, False = not satisfied, None = cannot determine.
    passed: bool | None
    confidence: float
    message: str
    matched_field_ids: list[UUID] = field(default_factory=list)
    data: dict = field(default_factory=dict)


Validator = Callable[[list[FieldObservation], RuleSpec], ValidatorResult]

_NUMBER_RE = re.compile(r"[-+]?\d*\.?\d+")


def _find(observations: list[FieldObservation], spec: RuleSpec) -> FieldObservation | None:
    if spec.target_field_type is None:
        return None
    for obs in observations:
        if obs.field_type == spec.target_field_type:
            return obs
    return None


def _to_number(value: str | None) -> float | None:
    if not value:
        return None
    match = _NUMBER_RE.search(value)
    return float(match.group()) if match else None


def field_present(observations: list[FieldObservation], spec: RuleSpec) -> ValidatorResult:
    obs = _find(observations, spec)
    if obs is None:
        return ValidatorResult(False, 0.9, "Expected declaration was not detected on the label.")
    value = (obs.normalized_value or obs.raw_text or "").strip()
    if not value:
        return ValidatorResult(False, obs.confidence, "Declaration detected but value is empty.",
                               matched_field_ids=[obs.id])
    return ValidatorResult(True, obs.confidence, "Declaration is present.", matched_field_ids=[obs.id])


def non_empty_text(observations: list[FieldObservation], spec: RuleSpec) -> ValidatorResult:
    obs = _find(observations, spec)
    if obs is None:
        return ValidatorResult(None, 0.5, "Declaration not detected; cannot evaluate text content.")
    min_len = int(spec.params.get("min_length", 2))
    value = (obs.normalized_value or obs.raw_text or "").strip()
    passed = len(value) >= min_len
    return ValidatorResult(
        passed, obs.confidence,
        "Text content meets minimum length." if passed else "Text content too short.",
        matched_field_ids=[obs.id],
    )


def numeric_positive(observations: list[FieldObservation], spec: RuleSpec) -> ValidatorResult:
    obs = _find(observations, spec)
    if obs is None:
        return ValidatorResult(None, 0.5, "Value not detected; cannot evaluate numerically.")
    number = _to_number(obs.normalized_value or obs.raw_text)
    if number is None:
        return ValidatorResult(None, obs.confidence, "Detected value is not numeric.",
                               matched_field_ids=[obs.id])
    passed = number > 0
    return ValidatorResult(
        passed, obs.confidence,
        f"Numeric value {number} is positive." if passed else f"Numeric value {number} is not positive.",
        matched_field_ids=[obs.id], data={"value": number},
    )


def pattern_match(observations: list[FieldObservation], spec: RuleSpec) -> ValidatorResult:
    obs = _find(observations, spec)
    if obs is None:
        return ValidatorResult(None, 0.5, "Value not detected; cannot evaluate pattern.")
    pattern = spec.params.get("pattern")
    if not pattern:
        return ValidatorResult(None, 0.4, "No pattern configured for this rule.")
    text = obs.normalized_value or obs.raw_text or ""
    passed = re.search(pattern, text) is not None
    return ValidatorResult(
        passed, obs.confidence,
        "Value matches the expected format." if passed else "Value does not match the expected format.",
        matched_field_ids=[obs.id],
    )


_REGISTRY: dict[str, Validator] = {
    "field_present": field_present,
    "non_empty_text": non_empty_text,
    "numeric_positive": numeric_positive,
    "pattern_match": pattern_match,
}


def get_validator(ref: str) -> Validator | None:
    return _REGISTRY.get(ref)


def registered_validators() -> list[str]:
    return sorted(_REGISTRY)
