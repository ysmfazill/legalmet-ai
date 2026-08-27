"""Deterministic rule engine.

This is the ONLY component that produces compliance conclusions, and it does so
deterministically — no LLM, no learned model in this path. It consumes verified
rule specs (resolved to a specific version by the regulatory service) plus
perception observations, applies the referenced validator, and then applies a
**confidence & quality policy** so the system never asserts a legal conclusion
it cannot support:

    image quality insufficient  -> IMAGE_QUALITY_INSUFFICIENT
    perception confidence low   -> LOW_CONFIDENCE
    validator indeterminate     -> REVIEW_REQUIRED
    validator failed + poor img -> REVIEW_REQUIRED  (never assert violation)
    validator failed            -> POTENTIAL_VIOLATION
    validator passed            -> COMPLIANT
"""
from __future__ import annotations

from app.core.enums import ComplianceStatus, ImageQualityStatus, ModelServiceType
from app.services.interfaces import (
    FieldObservation,
    FindingResult,
    ImageQualityResult,
    RuleEngine,
    RuleSpec,
    ServiceDescriptor,
)
from app.services.rules.validators import get_validator

_DEGRADED_QUALITY = {
    ImageQualityStatus.BLURRY,
    ImageQualityStatus.GLARE,
    ImageQualityStatus.LOW_RESOLUTION,
}


class DeterministicRuleEngine(RuleEngine):
    @property
    def descriptor(self) -> ServiceDescriptor:
        return ServiceDescriptor(
            service_type=ModelServiceType.RULE_ENGINE,
            name="deterministic-rule-engine",
            version="0.1.0",
            provider="legalmet",
        )

    def validate(
        self,
        *,
        observations: list[FieldObservation],
        rules: list[RuleSpec],
        quality: ImageQualityResult,
        confidence_threshold: float,
    ) -> list[FindingResult]:
        results: list[FindingResult] = []
        quality_insufficient = quality.status == ImageQualityStatus.INSUFFICIENT
        quality_degraded = quality.status in _DEGRADED_QUALITY

        for spec in rules:
            validator = get_validator(spec.validation_logic_ref)
            if validator is None:
                results.append(
                    FindingResult(
                        rule_id=spec.rule_id,
                        rule_version_id=spec.rule_version_id,
                        field_type=spec.target_field_type,
                        status=ComplianceStatus.REVIEW_REQUIRED,
                        confidence=0.3,
                        rationale=(
                            f"[{spec.rule_code}] No validator registered for "
                            f"'{spec.validation_logic_ref}'. Manual review required."
                        ),
                        validator_output={"validator": spec.validation_logic_ref, "known": False},
                    )
                )
                continue

            outcome = validator(observations, spec)
            perception_conf = outcome.confidence
            status, confidence = self._decide(
                outcome_passed=outcome.passed,
                perception_conf=perception_conf,
                threshold=confidence_threshold,
                quality_insufficient=quality_insufficient,
                quality_degraded=quality_degraded,
                quality_score=quality.score,
            )

            rationale = self._explain(spec, outcome.message, status, confidence, quality)
            results.append(
                FindingResult(
                    rule_id=spec.rule_id,
                    rule_version_id=spec.rule_version_id,
                    field_type=spec.target_field_type,
                    status=status,
                    confidence=round(confidence, 3),
                    rationale=rationale,
                    matched_field_ids=list(outcome.matched_field_ids),
                    validator_output={
                        "validator": spec.validation_logic_ref,
                        "passed": outcome.passed,
                        "message": outcome.message,
                        **outcome.data,
                    },
                )
            )
        return results

    @staticmethod
    def _decide(
        *,
        outcome_passed: bool | None,
        perception_conf: float,
        threshold: float,
        quality_insufficient: bool,
        quality_degraded: bool,
        quality_score: float,
    ) -> tuple[ComplianceStatus, float]:
        if quality_insufficient:
            return ComplianceStatus.IMAGE_QUALITY_INSUFFICIENT, quality_score
        # A *present* but low-confidence observation must not drive a conclusion.
        if outcome_passed is not None and perception_conf < threshold:
            return ComplianceStatus.LOW_CONFIDENCE, perception_conf
        if outcome_passed is None:
            return ComplianceStatus.REVIEW_REQUIRED, min(perception_conf, 0.5)
        if outcome_passed:
            return ComplianceStatus.COMPLIANT, perception_conf
        # Failed the check.
        if quality_degraded:
            return ComplianceStatus.REVIEW_REQUIRED, min(perception_conf, quality_score)
        return ComplianceStatus.POTENTIAL_VIOLATION, perception_conf

    @staticmethod
    def _explain(
        spec: RuleSpec,
        validator_message: str,
        status: ComplianceStatus,
        confidence: float,
        quality: ImageQualityResult,
    ) -> str:
        parts = [
            f"[{spec.rule_code}] {spec.requirement_summary}",
            f"Validator ({spec.validation_logic_ref}): {validator_message}",
            f"Outcome: {status.value} at {confidence:.0%} confidence.",
        ]
        if quality.status != ImageQualityStatus.OK:
            parts.append(f"Image quality: {quality.status.value} ({quality.notes}).")
        parts.append("DEMO DATA — NOT LEGAL ADVICE.")
        return " ".join(parts)
