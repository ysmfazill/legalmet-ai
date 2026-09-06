"""Deterministic declared-vs-measured regulatory evaluation (UI-07).

Runs ONCE per recorded verification result, at recording time, and freezes:

* the applicable regulation version (resolved with the same window semantics
  as the compliance engine),
* the permissible-error procedure that was configured for that version,
* the exact inputs (declared text, measured value/unit, normalized values,
  observed difference) and the computed tolerance.

HISTORICAL SAFETY: everything is stored on the ``MeasurementEvaluation`` row —
a later procedure update can never rewrite what an earlier measurement was
evaluated against.

LEGAL SAFETY: when no permissible-error procedure is configured (or the
configuration is malformed), the evaluation is UNAVAILABLE with the exact
reason — the system NEVER guesses a tolerance. Even an evaluated outcome
(WITHIN_TOLERANCE / EXCEEDS_TOLERANCE) is a rule result, not a violation: it
never changes a finding, a decision, or a lot status by itself.
"""
from __future__ import annotations

import uuid
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import (
    MeasurementEvaluationStatus,
    MeasurementOutcome,
    RegulatoryProcedureKind,
)
from app.db.base import utcnow
from app.models import MeasurementEvaluation, RegulatoryProcedure
from app.services.compliance.resolvers import RequirementResolver
from app.services.regulatory.service import RegulatoryService
from app.services.verification.units import (
    observed_difference,
    parse_declared_quantity,
    plain_decimal,
)

UNAVAILABLE_REASON = (
    "Applicable permissible error/procedure is not configured."
)
INSPECTOR_REVIEW_NOTE = "Inspector review required."

_MALFORMED_REASON = (
    "The configured permissible-error procedure could not be interpreted "
    "deterministically (malformed configuration)."
)


def declared_text_for_task(task) -> str | None:
    """The DECLARED value a task's measurement is compared against.

    Finding/declaration-anchored tasks read the extracted field (corrected
    value wins — that is what a human confirmed); lot-anchored tasks read the
    lot's immutable declared_value. The text is preserved verbatim when it
    already parses; the extracted field keeps its unit in a SEPARATE column,
    so a bare value ("500") is recombined with that unit ("500 g") — the unit
    is the declaration's own, never an assumption.
    """
    if task.lot_package_id is not None and task.lot_package is not None:
        return task.lot_package.lot.declared_value
    field = task.extracted_field
    if field is None:
        return None
    value = field.corrected_value or field.normalized_value
    if value is None:
        return None
    if parse_declared_quantity(value) is None and field.unit:
        candidate = f"{value} {field.unit}"
        if parse_declared_quantity(candidate) is not None:
            return candidate
    return value


def evaluate_measurement(
    db: Session,
    *,
    result,
    task,
    regulatory: RegulatoryService,
) -> MeasurementEvaluation:
    """Create (and return) the frozen evaluation for ONE recorded result.

    Called from ``VerificationService.record_result`` inside the same
    transaction. Deterministic: same DB state + same inputs → same row.
    """
    declared = declared_text_for_task(task)
    evaluated_at = utcnow()

    resolution = RequirementResolver(regulatory).resolve_version(
        db, at=evaluated_at
    )

    procedure: RegulatoryProcedure | None = None
    if resolution.version is not None:
        procedure = db.execute(
            select(RegulatoryProcedure)
            .where(
                RegulatoryProcedure.regulation_version_id == resolution.version.id,
                RegulatoryProcedure.kind == RegulatoryProcedureKind.MEASUREMENT_TOLERANCE.value,
                RegulatoryProcedure.active.is_(True),
                RegulatoryProcedure.is_demo.is_(False),
            )
            .order_by(RegulatoryProcedure.code.asc())
            .limit(1)
        ).scalar_one_or_none()

    provenance: dict = {
        "versionStatus": resolution.status,
        "versionLabel": (
            resolution.version.version_label if resolution.version else None
        ),
        "regulationCode": (
            resolution.document.code if resolution.document else None
        ),
        "evaluatedAt": evaluated_at.isoformat(),
        "engineNote": (
            "Version resolved with the same [effective_from, effective_until) "
            "window semantics as the compliance engine."
        ),
    }

    diff_block = (
        observed_difference(declared, result.measured_value, result.unit or "")
        if (result.measured_value is not None and result.unit)
        else None
    )

    # ------------------------------------------------- no procedure configured
    if procedure is None:
        reason = (
            UNAVAILABLE_REASON
            if resolution.version is not None
            else (
                "No applicable regulation version is in force, so no "
                "permissible-error procedure can be resolved."
            )
        )
        evaluation = MeasurementEvaluation(
            verification_result_id=result.id,
            inspection_id=task.inspection_id,
            status=MeasurementEvaluationStatus.UNAVAILABLE.value,
            outcome=None,
            rule_code=None,
            rule_version_id=resolution.version.id if resolution.version else None,
            provenance=provenance,
            detail={
                "reason": reason,
                "note": INSPECTOR_REVIEW_NOTE,
                "declared": declared,
                "measuredValue": result.measured_value,
                "measuredUnit": result.unit,
                "observed": diff_block,
            },
            evaluated_at=evaluated_at,
        )
        db.add(evaluation)
        return evaluation

    provenance["procedureCode"] = procedure.code
    provenance["procedureTitle"] = procedure.title
    provenance["sourceReference"] = procedure.source_reference

    # --------------------------------------------------- deterministic outcome
    tolerance = _permissible_error(procedure)
    if tolerance is None or diff_block is None or not diff_block.get("comparable"):
        evaluation = MeasurementEvaluation(
            verification_result_id=result.id,
            inspection_id=task.inspection_id,
            status=MeasurementEvaluationStatus.UNAVAILABLE.value,
            outcome=None,
            rule_code=procedure.code,
            rule_version_id=resolution.version.id,
            provenance=provenance,
            detail={
                "reason": (
                    _MALFORMED_REASON
                    if tolerance is None
                    else (
                        (diff_block or {}).get(
                            "reason",
                            "The declared and measured values cannot be "
                            "compared deterministically.",
                        )
                    )
                ),
                "note": INSPECTOR_REVIEW_NOTE,
                "declared": declared,
                "measuredValue": result.measured_value,
                "measuredUnit": result.unit,
                "observed": diff_block,
            },
            evaluated_at=evaluated_at,
        )
        db.add(evaluation)
        return evaluation

    tolerance_type, tolerance_value = tolerance
    try:
        magnitude = abs(Decimal(diff_block["difference"]))
        declared_number = Decimal(diff_block["declared"]["value"])
    except (InvalidOperation, KeyError) as exc:  # pragma: no cover — defensive
        raise ValueError(
            f"Non-decimal values reached the tolerance comparison: {exc}"
        ) from exc

    if tolerance_type == "PERCENT":
        limit = abs(declared_number) * tolerance_value / Decimal("100")
    else:  # ABSOLUTE — already in the declared unit
        limit = tolerance_value
    within = magnitude <= limit

    evaluation = MeasurementEvaluation(
        verification_result_id=result.id,
        inspection_id=task.inspection_id,
        status=MeasurementEvaluationStatus.EVALUATED.value,
        outcome=(
            MeasurementOutcome.WITHIN_TOLERANCE.value
            if within
            else MeasurementOutcome.EXCEEDS_TOLERANCE.value
        ),
        rule_code=procedure.code,
        rule_version_id=resolution.version.id,
        provenance=provenance,
        detail={
            "declared": declared,
            "measuredValue": result.measured_value,
            "measuredUnit": result.unit,
            "observed": diff_block,
            "tolerance": {
                "type": tolerance_type,
                "value": plain_decimal(tolerance_value),
                "limitInDeclaredUnit": plain_decimal(limit),
                "observedMagnitude": plain_decimal(magnitude),
            },
            "note": (
                "Deterministic evaluation of the configured permissible "
                "error. This is a rule result, not a violation — the "
                "inspector weighs it in the final decision."
            ),
        },
        evaluated_at=evaluated_at,
    )
    db.add(evaluation)
    return evaluation


def _permissible_error(procedure: RegulatoryProcedure) -> tuple[str, Decimal] | None:
    """Interpret ``{"permissibleError": {"type": ..., "value": ...}}``.

    Returns None for anything that is not EXACTLY the supported shape —
    never a default tolerance.
    """
    config = procedure.configuration or {}
    block = config.get("permissibleError")
    if not isinstance(block, dict):
        return None
    error_type = block.get("type")
    if error_type not in ("PERCENT", "ABSOLUTE"):
        return None
    try:
        value = Decimal(str(block.get("value")))
    except (InvalidOperation, TypeError):
        return None
    if value < 0:
        return None
    return error_type, value


def evaluation_out(evaluation) -> dict | None:
    """Read-model shape of a frozen MeasurementEvaluation (camelCase keys).

    Shared by the verification read models (measurement history, plan rows)
    and the lot read model — one shape, defined once.
    """
    if evaluation is None:
        return None
    return {
        "id": evaluation.id,
        "status": evaluation.status,
        "outcome": evaluation.outcome,
        "rule_code": evaluation.rule_code,
        "rule_version_id": evaluation.rule_version_id,
        "provenance": evaluation.provenance,
        "detail": evaluation.detail,
        "evaluated_at": evaluation.evaluated_at,
    }


def evaluations_for_results(
    db: Session, result_ids: list[uuid.UUID]
) -> dict[uuid.UUID, MeasurementEvaluation]:
    """Bulk lookup: result id → its frozen evaluation (read models)."""
    if not result_ids:
        return {}
    rows = db.execute(
        select(MeasurementEvaluation).where(
            MeasurementEvaluation.verification_result_id.in_(result_ids)
        )
    ).scalars()
    return {row.verification_result_id: row for row in rows}
