"""The ComplianceEngine — deterministic orchestrator of the evaluation pipeline.

Contract (Prompt 6):

    INPUTS   inspection (with packages/images/perception fields),
             regulatory version in force at the inspection context date,
             deterministic rules bound to that version's requirements
    OUTPUT   one ComplianceEvaluation row + one EvaluationFinding per
             (requirement, detected-field) pair, each with status, severity,
             detected/expected values, explanation, evidence references and a
             frozen provenance snapshot

GUARANTEES (each enforced below, each tested):

1. Determinism — same inputs → same findings, byte-for-byte explanations.
2. No LLM — no model call anywhere; failure to evaluate is recorded, never
   guessed. An engine failure NEVER becomes COMPLIANT.
3. COMPLIANT / NON_COMPLIANT only with adequate valid evidence AND positive
   applicability; insufficient evidence → REVIEW_REQUIRED; not extracted →
   NOT_DETECTED; ambiguity → REVIEW_REQUIRED (never a guess).
4. FIELD_NOT_FOUND ≠ FIELD_CONFIRMED_ABSENT — missing OCR is never converted
   into legal non-compliance.
5. History is never overwritten — every run is a new evaluation row; past
   results (and their regulatory versions) remain reproducible.
6. No fake scores — the summary contains COUNTS ONLY, never a percentage or
   "legal confidence".

Compliance findings are system-generated decision-support outputs. They are
not, by themselves, legal enforcement determinations — the inspector remains
responsible for the final enforcement decision.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import (
    AbsenceReason,
    ApplicabilityOutcome,
    AuditEventType,
    ComplianceErrorCode,
    EngineFindingStatus,
    EvaluationStatus,
    FindingSeverity,
)
from app.db.base import utcnow
from app.models import (
    ComplianceEvaluation,
    EvaluationFinding,
    Inspection,
    Regulation,
    RegulationVersion,
    RegulatorySource,
    Rule,
)
from app.services.compliance.applicability import (
    ApplicabilityInput,
    ApplicabilityResolver,
)
from app.services.compliance.evaluators import get_evaluator
from app.services.compliance.resolvers import (
    EvidenceResolver,
    RequirementResolver,
    RuleResolver,
    VersionResolution,
)
from app.services.regulatory.service import RegulatoryService

ENGINE_VERSION = "1.0.0"

# Findings whose deterministic status maps to the review queue. The queue shows
# "System finding — inspector decision pending"; final approval is Prompt 8.
_REVIEW_STATUSES = frozenset(
    {
        EngineFindingStatus.REVIEW_REQUIRED,
        EngineFindingStatus.NOT_DETECTED,
        EngineFindingStatus.NOT_EVALUATED,
    }
)

# Severity is a triage label only — assigned deterministically from the rule
# type and status, never a legal penalty.
_SEVERITY_BY_STATUS = {
    EngineFindingStatus.NON_COMPLIANT: FindingSeverity.MAJOR,
    EngineFindingStatus.COMPLIANT: FindingSeverity.INFO,
    EngineFindingStatus.REVIEW_REQUIRED: FindingSeverity.UNKNOWN,
    EngineFindingStatus.NOT_DETECTED: FindingSeverity.MINOR,
    EngineFindingStatus.NOT_APPLICABLE: FindingSeverity.INFO,
    EngineFindingStatus.NOT_EVALUATED: FindingSeverity.UNKNOWN,
}


@dataclass
class EvaluationRunResult:
    """In-memory outcome of one run (persisted rows are also returned)."""

    evaluation: ComplianceEvaluation
    findings: list[EvaluationFinding] = field(default_factory=list)


class ComplianceEngine:
    """Runs one deterministic compliance evaluation over an inspection."""

    def __init__(
        self,
        regulatory: RegulatoryService,
        audit=None,
    ) -> None:
        self._regulatory = regulatory
        self._audit = audit
        self._applicability = ApplicabilityResolver()
        self._requirements = RequirementResolver(regulatory)
        self._rules = RuleResolver()
        self._evidence = EvidenceResolver()

    # ------------------------------------------------------------------ API

    def evaluate(
        self,
        db: Session,
        *,
        inspection_id: uuid.UUID,
        actor_id: uuid.UUID | None = None,
    ) -> ComplianceEvaluation:
        """Evaluate one inspection. Creates a NEW evaluation (never overwrites).

        Failures raise nothing structural: they are recorded on the evaluation
        row (status=FAILED + error code) because a failed run is itself an
        auditable artifact.
        """
        inspection = db.get(Inspection, inspection_id)
        if inspection is None:
            from app.core.errors import NotFoundError

            raise NotFoundError(f"Inspection not found: {inspection_id}")

        started_at = utcnow()
        context_date = inspection.context_date or inspection.created_at or started_at
        evaluation = ComplianceEvaluation(
            inspection_id=inspection.id,
            status=EvaluationStatus.EVALUATING.value,
            engine_version=ENGINE_VERSION,
            context_date=context_date,
            started_at=started_at,
            actor_id=actor_id,
        )
        db.add(evaluation)
        db.flush()
        self._record_audit(
            db,
            AuditEventType.COMPLIANCE_EVALUATION_STARTED,
            evaluation,
            actor_id,
            {"engineVersion": ENGINE_VERSION, "contextDate": context_date.isoformat()},
        )

        findings: list[EvaluationFinding] = []
        try:
            findings = self._run(db, inspection, evaluation)
        except _EngineFailure as exc:
            evaluation.status = EvaluationStatus.FAILED.value
            evaluation.error = {
                "code": exc.code,
                "message": exc.message,
            }
            evaluation.completed_at = utcnow()
            db.flush()
            self._record_audit(
                db,
                AuditEventType.COMPLIANCE_EVALUATION_FAILED,
                evaluation,
                actor_id,
                {"code": exc.code, "message": exc.message},
            )
            db.commit()
            return evaluation

        # Transparent summary: COUNTS ONLY. No percentage, no confidence score.
        counts: dict[str, int] = {s.value: 0 for s in EngineFindingStatus}
        for finding in findings:
            counts[finding.status] = counts.get(finding.status, 0) + 1
        evaluation.summary = {
            "totalFindings": len(findings),
            "byStatus": counts,
            "reviewQueueCount": sum(
                counts.get(s.value, 0) for s in _REVIEW_STATUSES
            ),
            "requirementsEvaluated": len(
                {f.requirement_id for f in findings}
            ),
        }
        if any(f.status == EngineFindingStatus.NOT_EVALUATED.value for f in findings):
            evaluation.status = EvaluationStatus.PARTIAL.value
        elif any(f.status in _REVIEW_STATUSES for f in findings):
            evaluation.status = EvaluationStatus.REVIEW_REQUIRED.value
        elif not findings:
            evaluation.status = EvaluationStatus.NO_APPLICABLE_REQUIREMENT.value
        else:
            evaluation.status = EvaluationStatus.COMPLETED.value
        evaluation.completed_at = utcnow()
        db.flush()
        self._record_audit(
            db,
            AuditEventType.COMPLIANCE_EVALUATION_COMPLETED,
            evaluation,
            actor_id,
            {"status": evaluation.status, "totalFindings": len(findings)},
        )
        db.commit()
        return evaluation

    # ------------------------------------------------------------------ core

    def _run(
        self,
        db: Session,
        inspection: Inspection,
        evaluation: ComplianceEvaluation,
    ) -> list[EvaluationFinding]:
        # 1) Version resolution — deterministic, never a silent fallback.
        resolution: VersionResolution = self._requirements.resolve_version(
            db, at=evaluation.context_date
        )
        if resolution.status == "NO_REGULATORY_DATA":
            raise _EngineFailure(
                ComplianceErrorCode.REGULATORY_DATA_UNAVAILABLE,
                "No non-demo regulatory documents exist — the engine refuses to "
                "evaluate against an empty regulatory dataset.",
            )
        if resolution.status == "NO_APPLICABLE_VERSION":
            evaluation.regulatory_version_id = None
            raise _EngineFailure(
                ComplianceErrorCode.NO_APPLICABLE_VERSION,
                "No regulatory version is in force at the evaluation context date "
                f"({evaluation.context_date.date().isoformat()}).",
            )
        evaluation.regulatory_version_id = resolution.version.id
        db.flush()

        version = resolution.version
        document = resolution.document
        source = (
            db.get(RegulatorySource, document.source_id) if document.source_id else None
        )

        # 2) Requirements in force at this version, with their rules.
        requirements = self._requirements.requirements_for_version(db, version.id)
        if not requirements:
            raise _EngineFailure(
                ComplianceErrorCode.NO_APPLICABLE_REQUIREMENT,
                "The version in force carries no active requirements with a "
                "checkable field key.",
            )

        # 3) Package facts for applicability.
        package_input = self._package_input(db, inspection)

        findings: list[EvaluationFinding] = []
        for requirement in requirements:
            # Applicability first — NO means "recorded, not violated".
            applicability = self._applicability.evaluate(
                requirement.applicability_definition or {}, package_input
            )
            if applicability.outcome is ApplicabilityOutcome.NO:
                findings.append(
                    self._build_not_applicable(db, evaluation, requirement, version,
                                               document, source, applicability)
                )
                continue

            # Evidence resolution — which fields speak to this requirement?
            bundle = self._evidence.evidence_for(
                db, inspection_id=inspection.id, field_key=requirement.field_key
            )

            rules = self._rules.rules_for_requirement(db, requirement.id)
            if not rules:
                # A requirement with no configured rule is NOT_EVALUATED — the
                # engine never invents a check that was not configured.
                findings.append(
                    self._build_not_evaluated(
                        db, evaluation, requirement, version, document, source,
                        applicability, bundle,
                        ComplianceErrorCode.RULE_EXECUTION_FAILED,
                        "No active deterministic rule is configured for this "
                        "requirement.",
                    )
                )
                continue

            if applicability.outcome is ApplicabilityOutcome.UNKNOWN:
                # Requirement MAY apply but the package facts are missing —
                # every finding for it is REVIEW_REQUIRED, never a violation.
                findings.append(
                    self._build_review(
                        db, evaluation, requirement, version, document, source,
                        applicability, bundle,
                        f"Applicability could not be determined: {applicability.reason}",
                    )
                )
                continue

            # One finding per requirement, evaluated over its rules.
            findings.append(
                self._evaluate_requirement(
                    db, evaluation, requirement, rules, bundle, version,
                    document, source, applicability,
                )
            )

        # Uncheckable requirements (no field key) are recorded honestly as
        # NOT_EVALUATED rather than silently dropped.
        for requirement in self._requirements.unchecked_requirements(db, version.id):
            findings.append(
                self._build_not_evaluated(
                    db, evaluation, requirement, version, document, source,
                    None, None,
                    ComplianceErrorCode.NO_APPLICABLE_REQUIREMENT,
                    "The requirement has no field key mapped to perception "
                    "evidence — the engine cannot check it deterministically yet.",
                )
            )
        return findings

    def _evaluate_requirement(
        self,
        db: Session,
        evaluation: ComplianceEvaluation,
        requirement: Rule,
        rules,
        bundle,
        version: RegulationVersion,
        document: Regulation,
        source,
        applicability,
    ) -> EvaluationFinding:
        """Run each configured rule over the best evidence; aggregate honestly."""
        outcomes = []
        gate = self._evidence_quality_gate(bundle.best)
        if gate is not None:
            # Phase 2: COMPLIANT / NON_COMPLIANT require enough valid evidence.
            # The gate applies to EVERY requirement uniformly — independent of
            # which rule types happen to be bound — so a low-confidence read
            # can never produce a positive finding through the back door.
            outcomes.append(gate)
        for rule in rules:
            evaluator = get_evaluator(rule.rule_type)
            if evaluator is None:
                outcomes.append(
                    {
                        "ruleCode": rule.rule_code,
                        "ruleType": rule.rule_type,
                        "passed": None,
                        "reason": (
                            f"Unknown rule type '{rule.rule_type}' — the engine has "
                            "no evaluator for it."
                        ),
                        "errorCode": ComplianceErrorCode.RULE_EXECUTION_FAILED.value,
                    }
                )
                continue
            try:
                outcome = evaluator(bundle.best, rule.configuration or {})
            except Exception as exc:  # noqa: BLE001 — recorded, never swallowed
                outcomes.append(
                    {
                        "ruleCode": rule.rule_code,
                        "ruleType": rule.rule_type,
                        "passed": None,
                        "reason": f"Rule execution raised an error: {exc}",
                        "errorCode": ComplianceErrorCode.RULE_EXECUTION_FAILED.value,
                    }
                )
                continue
            entry = {
                "ruleCode": rule.rule_code,
                "ruleType": rule.rule_type,
                "passed": outcome.passed,
                "reason": outcome.reason,
            }
            if outcome.expected is not None:
                entry["expected"] = outcome.expected
            if outcome.detail:
                entry.update(outcome.detail)
            outcomes.append(entry)

        # Aggregate: any hard fail → NON_COMPLIANT; any indeterminate →
        # REVIEW_REQUIRED; all pass → COMPLIANT. An engine failure never
        # becomes COMPLIANT (a failed rule forces REVIEW_REQUIRED or worse).
        failed = [o for o in outcomes if o["passed"] is False]
        indeterminate = [o for o in outcomes if o["passed"] is None]

        best = bundle.best

        if failed:
            status = EngineFindingStatus.NON_COMPLIANT
            headline = failed[0]["reason"]
        elif best is None and not bundle.fields:
            # Phase 5: no field of this type was extracted AT ALL — the honest
            # status is NOT_DETECTED (the declaration was not perceived), which
            # is explicitly NOT a statement that it is absent or non-compliant.
            status = EngineFindingStatus.NOT_DETECTED
            headline = indeterminate[0]["reason"] if indeterminate else (
                "No field of this type was extracted by perception."
            )
        elif indeterminate:
            status = EngineFindingStatus.REVIEW_REQUIRED
            headline = indeterminate[0]["reason"]
            if any(o.get("errorCode") for o in indeterminate):
                headline = (
                    f"{indeterminate[0]['reason']} "
                    f"(code: {indeterminate[0].get('errorCode')})"
                )
        else:
            status = EngineFindingStatus.COMPLIANT
            headline = outcomes[0]["reason"] if outcomes else "No rules evaluated."
        detected = None
        if best is not None:
            detected = (
                getattr(best, "normalized_value", None)
                or getattr(best, "raw_text", None)
            )

        # Absence bookkeeping — FIELD_NOT_FOUND is never treated as absence.
        absence = AbsenceReason.FIELD_NOT_FOUND.value if best is None else None

        explanation = self._explain(
            requirement=requirement,
            version=version,
            document=document,
            source=source,
            applicability=applicability,
            bundle=bundle,
            status=status,
            headline=headline,
            outcomes=outcomes,
        )

        finding = EvaluationFinding(
            evaluation_id=evaluation.id,
            requirement_id=requirement.id,
            rule_id=rules[0].id if len(rules) == 1 else None,
            extracted_field_id=getattr(best, "id", None),
            evidence_region_id=getattr(best, "image_region_id", None),
            image_id=getattr(best, "image_id", None),
            status=status.value,
            severity=_SEVERITY_BY_STATUS.get(status, FindingSeverity.UNKNOWN).value,
            applicability=applicability.outcome.value,
            detected_value=str(detected) if detected is not None else None,
            expected_value=self._expected_value(requirement, outcomes),
            explanation=explanation,
            provenance=self._provenance_snapshot(
                requirement, version, document, source
            ),
            detail={
                "rules": outcomes,
                "evidenceFieldIds": [str(f.id) for f in bundle.fields],
                "searchedRunIds": [str(r) for r in bundle.searched_run_ids],
                "fieldKey": bundle.field_key,
                "evidenceCount": len(bundle.fields),
                **({"absence": absence} if absence else {}),
            },
        )
        db.add(finding)
        db.flush()
        self._record_audit(
            db,
            AuditEventType.COMPLIANCE_FINDING_CREATED,
            evaluation,
            None,
            {"findingId": str(finding.id), "status": finding.status,
             "requirement": requirement.rule_code},
        )
        return finding

    # ------------------------------------------------------------ builders

    def _build_not_applicable(
        self, db, evaluation, requirement, version, document, source, applicability
    ) -> EvaluationFinding:
        finding = EvaluationFinding(
            evaluation_id=evaluation.id,
            requirement_id=requirement.id,
            status=EngineFindingStatus.NOT_APPLICABLE.value,
            severity=FindingSeverity.INFO.value,
            applicability=ApplicabilityOutcome.NO.value,
            explanation=(
                f"Requirement {requirement.rule_code} does not apply to this package: "
                f"{applicability.reason} No non-compliance finding is created; the "
                "applicability decision is recorded for the audit trail."
            ),
            provenance=self._provenance_snapshot(requirement, version, document, source),
            detail={"applicabilityReason": applicability.reason},
        )
        db.add(finding)
        db.flush()
        self._record_audit(
            db,
            AuditEventType.COMPLIANCE_FINDING_CREATED,
            evaluation,
            None,
            {"findingId": str(finding.id), "status": finding.status,
             "requirement": requirement.rule_code},
        )
        return finding

    def _build_review(
        self, db, evaluation, requirement, version, document, source, applicability,
        bundle, reason,
    ) -> EvaluationFinding:
        finding = EvaluationFinding(
            evaluation_id=evaluation.id,
            requirement_id=requirement.id,
            status=EngineFindingStatus.REVIEW_REQUIRED.value,
            severity=FindingSeverity.UNKNOWN.value,
            applicability=applicability.outcome.value,
            detected_value=None,
            explanation=(
                f"Requirement {requirement.rule_code}: {reason} A human must "
                "determine applicability before any conclusion is drawn."
            ),
            provenance=self._provenance_snapshot(requirement, version, document, source),
            detail={"applicabilityReason": applicability.reason,
                    "fieldKey": bundle.field_key if bundle else None},
        )
        db.add(finding)
        db.flush()
        self._record_audit(
            db,
            AuditEventType.COMPLIANCE_FINDING_CREATED,
            evaluation,
            None,
            {"findingId": str(finding.id), "status": finding.status,
             "requirement": requirement.rule_code},
        )
        return finding

    def _build_not_evaluated(
        self, db, evaluation, requirement, version, document, source, applicability,
        bundle, code, message,
    ) -> EvaluationFinding:
        finding = EvaluationFinding(
            evaluation_id=evaluation.id,
            requirement_id=requirement.id,
            status=EngineFindingStatus.NOT_EVALUATED.value,
            severity=FindingSeverity.UNKNOWN.value,
            applicability=(
                applicability.outcome.value if applicability else ApplicabilityOutcome.UNKNOWN.value
            ),
            explanation=(
                f"Requirement {requirement.rule_code} could not be evaluated: "
                f"{message} (code: {code.value})"
            ),
            provenance=self._provenance_snapshot(requirement, version, document, source),
            detail={"errorCode": code.value, "message": message,
                    "fieldKey": bundle.field_key if bundle else None},
        )
        db.add(finding)
        db.flush()
        self._record_audit(
            db,
            AuditEventType.COMPLIANCE_FINDING_CREATED,
            evaluation,
            None,
            {"findingId": str(finding.id), "status": finding.status,
             "requirement": requirement.rule_code},
        )
        return finding

    # ------------------------------------------------------------ helpers

    def _package_input(self, db: Session, inspection: Inspection) -> ApplicabilityInput:
        """Deterministic package facts for applicability.

        Imported status: a package is imported when importer details were
        detected. If no importer evidence exists the status is UNKNOWN — never
        guessed as "not imported" (that would silently waive the
        country-of-origin requirement for imports whose importer field was
        simply not yet read).
        """
        from sqlalchemy import exists

        from app.models import ExtractedField, Package

        category = inspection.product.category if inspection.product else None
        imported: bool | None = None
        package_ids = list(
            db.execute(
                select(Package.id).where(Package.inspection_id == inspection.id)
            ).scalars()
        )
        if package_ids:
            has_importer = db.execute(
                select(
                    exists().where(
                        ExtractedField.package_id.in_(package_ids),
                        ExtractedField.field_type == "IMPORTER_DETAILS",
                    )
                )
            ).scalar()
            if has_importer:
                imported = True
        return ApplicabilityInput(category=category, imported=imported)

    # Minimum OCR confidence for evidence to support a positive conclusion.
    # Below it the finding is REVIEW_REQUIRED regardless of what the rules say.
    EVIDENCE_CONFIDENCE_FLOOR = 0.6

    def _evidence_quality_gate(self, best) -> dict | None:
        """Phase 2 evidence gate — enough valid evidence before any conclusion.

        Returns an indeterminate outcome entry when the best evidence field is
        flagged for review (perception status) or its OCR confidence is below
        the floor; None when the evidence is strong enough to evaluate. The
        gate never fails a requirement — it only routes it to a human.
        """
        if best is None:
            return None
        status = getattr(best, "status", None)
        confidence = getattr(best, "confidence", None)
        low = confidence is not None and confidence < self.EVIDENCE_CONFIDENCE_FLOOR
        unreliable = status in ("REVIEW_REQUIRED", "NOT_EXTRACTED")
        if not unreliable and not low:
            return None
        value = getattr(best, "normalized_value", None) or getattr(best, "raw_text", None)
        reason = (
            f"The best evidence for this requirement was read as '{value}' but "
            f"perception marked it unreliable (status={status}, OCR confidence="
            f"{confidence}). No conclusion is drawn until an inspector confirms "
            "the value (INSUFFICIENT_EVIDENCE)."
        )
        entry = {
            "ruleCode": "EVIDENCE_QUALITY",
            "ruleType": "EVIDENCE_GATE",
            "passed": None,
            "reason": reason,
            "errorCode": ComplianceErrorCode.INSUFFICIENT_EVIDENCE.value,
        }
        return entry

    def _expected_value(self, requirement: Rule, outcomes: list[dict]) -> str | None:
        for outcome in outcomes:
            if outcome.get("expected"):
                return str(outcome["expected"])
        return requirement.expected_format

    def _explain(
        self, *, requirement, version, document, source, applicability, bundle,
        status, headline, outcomes,
    ) -> str:
        """Deterministic explanation answering the seven questions."""
        detected = bundle.best
        detected_value = (
            getattr(detected, "normalized_value", None)
            or getattr(detected, "raw_text", None)
        )
        detected_desc = (
            f"detected value '{detected_value}' "
            f"(raw: '{getattr(detected, 'raw_text', None)}')"
            if detected is not None
            else "no field of this type was detected (FIELD_NOT_FOUND)"
        )
        rule_desc = "; ".join(
            f"{o['ruleCode']} ({o['ruleType']}): {o['reason']}" for o in outcomes
        )
        return (
            f"Requirement {requirement.rule_code} ('{requirement.title}') from "
            f"{document.title} version '{version.version_label}' "
            f"(in force {self._fmt_date(version.effective_from)} → "
            f"{self._fmt_date(version.effective_until)}), source "
            f"'{source.name if source else 'unknown'}' "
            f"({source.verification_status if source else 'unknown'}): "
            f"applicability {applicability.outcome.value} — {applicability.reason} "
            f"Evidence: {detected_desc}. "
            f"Rules: {rule_desc}. "
            f"Deterministic outcome: {status.value} — {headline} "
            "This is a system-generated decision-support output, not a legal "
            "enforcement determination."
        )

    @staticmethod
    def _fmt_date(value: datetime | None) -> str:
        return value.date().isoformat() if value else "open"

    def _provenance_snapshot(
        self, requirement: Rule, version, document, source
    ) -> dict:
        """Frozen provenance — later regulatory edits cannot rewrite history."""
        return {
            "requirementCode": requirement.rule_code,
            "requirementTitle": requirement.title,
            "requirementReference": requirement.source_reference,
            "versionId": str(version.id),
            "versionLabel": version.version_label,
            "effectiveFrom": version.effective_from.isoformat()
            if version.effective_from
            else None,
            "effectiveUntil": version.effective_until.isoformat()
            if version.effective_until
            else None,
            "documentTitle": document.title if document else None,
            "documentIdentifier": document.document_identifier if document else None,
            "sourceName": source.name if source else None,
            "sourceVerificationStatus": source.verification_status if source else None,
        }

    def _record_audit(self, db, event_type, evaluation, actor_id, payload: dict) -> None:
        if self._audit is None:
            return
        self._audit.record(
            db,
            event_type=event_type,
            entity_type="compliance_evaluation",
            entity_id=evaluation.id,
            actor_id=actor_id,
            inspection_id=evaluation.inspection_id,
            payload=payload,
        )


class _EngineFailure(Exception):
    """Internal control-flow for structural engine failures (recorded, raised)."""

    def __init__(self, code: ComplianceErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
