"""Deterministic regulatory evaluation of measurements (UI-07).

Covers the contract (spec §2, §9–§11):

* DECLARED and MEASURED stay separate; the evaluation is a rule result, never
  an automatic violation — 492 g vs 500 g alone decides nothing
* when no permissible-error procedure is configured: UNAVAILABLE with the
  exact reason "Applicable permissible error/procedure is not configured."
  and "Inspector review required." — the system NEVER guesses a tolerance
* a configured PERCENT/ABSOLUTE procedure evaluates deterministically against
  the version resolved with the compliance engine's window semantics
* every evaluation is FROZEN on its result row: a later procedure change can
  never rewrite what an earlier measurement was evaluated against (§10)
* the declaration is value+unit: the extracted field's unit column is
  recombined, never assumed
"""
from __future__ import annotations

from contextlib import contextmanager

import pytest
from sqlalchemy import delete, select

from app.core.enums import (
    FieldType,
    VerificationTaskType,
    MeasurementEvaluationStatus,
    MeasurementOutcome,
    RegulationVersionStatus,
    RegulatoryProcedureKind,
)
from app.db.base import utcnow
from app.models import (
    ExtractedField,
    MeasurementEvaluation,
    Package,
    Regulation,
    RegulatoryProcedure,
    User,
)
from app.services.compliance.resolvers import RequirementResolver
from app.services.regulatory.service import RegulatoryService
from app.services.verification.measurement_eval import (
    INSPECTOR_REVIEW_NOTE,
    UNAVAILABLE_REASON,
    declared_text_for_task,
)

from tests.test_compliance_engine import _FULL_COMPLIANT_FIELDS, _make_inspection

API = "/api/v1"
INSPECTOR_EMAIL = "inspector@legalmet.local"

# The full-compliant field set gives a NET_QUANTITY declaration "500" + unit "g".
_FIELDS = _FULL_COMPLIANT_FIELDS


def _inspector(db) -> User:
    return db.execute(
        select(User).where(User.email == INSPECTOR_EMAIL)
    ).scalar_one()


def _net_quantity_field(db, inspection) -> ExtractedField:
    return db.execute(
        select(ExtractedField)
        .join(Package, Package.id == ExtractedField.package_id)
        .where(
            Package.inspection_id == inspection.id,
            ExtractedField.field_type == FieldType.NET_QUANTITY.value,
        )
    ).scalar_one()


def _active_version(db):
    """The non-demo ACTIVE version the resolver finds for 'now'."""
    resolution = RequirementResolver(RegulatoryService()).resolve_version(
        db, at=utcnow()
    )
    assert resolution.version is not None, "seed must provide an ACTIVE version"
    return resolution.version


@contextmanager
def _procedure(db, *, code, configuration):
    """Seed a tolerance procedure on the applicable version; remove it after
    so the shared session DB stays as the regulatory seed left it."""
    procedure = RegulatoryProcedure(
        regulation_version_id=_active_version(db).id,
        kind=RegulatoryProcedureKind.MEASUREMENT_TOLERANCE.value,
        code=code,
        title=f"[TEST] {code}",
        configuration=configuration,
        active=True,
        is_demo=False,
    )
    db.add(procedure)
    db.commit()
    try:
        yield procedure
    finally:
        db.execute(
            delete(RegulatoryProcedure).where(RegulatoryProcedure.id == procedure.id)
        )
        db.commit()


def _record(db, services, *, value, unit, reason="Physical verification of net quantity."):
    """Fresh inspection + field-anchored MEASUREMENT task + one result.

    The evaluation (if any) is frozen on the result at record time, exactly as
    production does. Returns the task."""
    inspection = _make_inspection(db, fields=_FIELDS)
    task = services.verification.create_task(
        db,
        inspection_id=inspection.id,
        actor=_inspector(db),
        finding_id=None,
        field_id=_net_quantity_field(db, inspection).id,
        task_type=VerificationTaskType.MEASUREMENT,
        reason=reason,
    )
    task = services.verification.record_result(
        db, task_id=task.id, actor=_inspector(db), measured_value=value, unit=unit
    )
    db.refresh(task)
    return task


def _evaluation(db, task) -> MeasurementEvaluation:
    evaluation = db.execute(
        select(MeasurementEvaluation).where(
            MeasurementEvaluation.verification_result_id == task.results[-1].id
        )
    ).scalar_one()
    db.refresh(evaluation)
    return evaluation


class TestDeclaredText:
    def test_field_unit_is_recombined(self, db, services):
        task = _record(db, services, value=492, unit="g")
        # The stored declaration is "500" + unit column "g" — the comparison
        # text must be the parseable pair, never a bare number.
        assert declared_text_for_task(task) == "500 g"

    def test_corrected_value_wins(self, db, services):
        task = _record(db, services, value=492, unit="g")
        task.extracted_field.corrected_value = "0.5 kg"
        db.flush()
        assert declared_text_for_task(task) == "0.5 kg"

    def test_unparseable_declaration_stays_verbatim(self, db, services):
        task = _record(db, services, value=492, unit="g")
        task.extracted_field.corrected_value = "approx half"
        task.extracted_field.unit = None
        db.flush()
        # Never invented: an unparseable declaration surfaces as-is.
        assert declared_text_for_task(task) == "approx half"


class TestUnavailableWhenNotConfigured:
    def test_no_procedure_is_unavailable_never_guessed(self, db, services):
        task = _record(db, services, value=492, unit="g")
        evaluation = _evaluation(db, task)
        assert evaluation.status == MeasurementEvaluationStatus.UNAVAILABLE.value
        assert evaluation.outcome is None
        assert evaluation.detail["reason"] == UNAVAILABLE_REASON
        assert evaluation.detail["note"] == INSPECTOR_REVIEW_NOTE
        # 492 < 500 decides NOTHING by itself (spec §2).
        assert "non_compliant" not in (evaluation.detail or {}).get("reason", "").lower()

    def test_history_carries_unavailable_evaluation(
        self, client, inspector_headers, db, services
    ):
        inspection = _make_inspection(db, fields=_FIELDS)
        task = services.verification.create_task(
            db,
            inspection_id=inspection.id,
            actor=_inspector(db),
            finding_id=None,
            field_id=_net_quantity_field(db, inspection).id,
            task_type=VerificationTaskType.MEASUREMENT,
            reason="Physical verification of the declared net quantity.",
        )
        task = services.verification.record_result(
            db,
            task_id=task.id,
            actor=_inspector(db),
            measured_value=492,
            unit="g",
            instrument_id="SCALE-01",
        )
        resp = client.get(
            f"{API}/inspections/{inspection.id}/measurements",
            headers=inspector_headers,
        )
        assert resp.status_code == 200, resp.text
        rows = resp.json()["measurements"]
        assert len(rows) == 1
        row = rows[0]
        assert row["declaredValue"] == "500 g"
        assert row["measuredValue"] == 492
        assert row["unit"] == "g"
        assert row["observed"]["comparable"] is True
        assert row["observed"]["difference"] == "-8"
        assert row["evaluation"]["status"] == "UNAVAILABLE"
        assert row["evaluation"]["detail"]["reason"] == UNAVAILABLE_REASON
        assert row["instrumentId"] == "SCALE-01"
        # Absent status means "not recorded", never "verified" (spec §7).
        assert row["instrumentVerificationStatus"] is None
        assert row["recordedByName"]  # the inspector, resolved for the UI


class TestConfiguredProcedure:
    def test_percent_within_tolerance(self, db, services):
        with _procedure(
            db,
            code="TEST-TOL-PERCENT",
            configuration={"permissibleError": {"type": "PERCENT", "value": "4.5"}},
        ):
            task = _record(db, services, value=492, unit="g")
            evaluation = _evaluation(db, task)
            # 492 vs 500 = -1.6% — within the flat 4.5% procedure.
            assert evaluation.status == MeasurementEvaluationStatus.EVALUATED.value
            assert evaluation.outcome == MeasurementOutcome.WITHIN_TOLERANCE.value
            assert evaluation.rule_code == "TEST-TOL-PERCENT"
            tol = evaluation.detail["tolerance"]
            assert tol["type"] == "PERCENT"
            assert tol["value"] == "4.5"
            assert tol["limitInDeclaredUnit"] == "22.5"
            assert tol["observedMagnitude"] == "8"
            assert evaluation.rule_version_id == _active_version(db).id

    def test_percent_exceeds_tolerance(self, db, services):
        with _procedure(
            db,
            code="TEST-TOL-PERCENT",
            configuration={"permissibleError": {"type": "PERCENT", "value": "1"}},
        ):
            task = _record(db, services, value=470, unit="g")
            evaluation = _evaluation(db, task)
            # -6% exceeds the 1% limit — a RULE result, never an automatic
            # violation: the finding and the decision stay with the inspector.
            assert evaluation.outcome == MeasurementOutcome.EXCEEDS_TOLERANCE.value
            assert evaluation.detail["tolerance"]["limitInDeclaredUnit"] == "5"

    def test_absolute_tolerance_in_declared_unit(self, db, services):
        with _procedure(
            db,
            code="TEST-TOL-ABS",
            configuration={"permissibleError": {"type": "ABSOLUTE", "value": "10"}},
        ):
            task = _record(db, services, value=492, unit="g")
            evaluation = _evaluation(db, task)
            # |−8| ≤ 10 → within.
            assert evaluation.outcome == MeasurementOutcome.WITHIN_TOLERANCE.value
            assert evaluation.detail["tolerance"]["limitInDeclaredUnit"] == "10"

    def test_kg_measurement_evaluated_against_g_declaration(self, db, services):
        with _procedure(
            db,
            code="TEST-TOL-PERCENT",
            configuration={"permissibleError": {"type": "PERCENT", "value": "4.5"}},
        ):
            # 0.492 kg ≡ 492 g — normalization happens BEFORE comparison (§5).
            task = _record(db, services, value=0.492, unit="kg")
            evaluation = _evaluation(db, task)
            assert evaluation.outcome == MeasurementOutcome.WITHIN_TOLERANCE.value
            assert evaluation.detail["observed"]["difference"] == "-8"

    def test_malformed_configuration_is_unavailable(self, db, services):
        with _procedure(
            db,
            code="TEST-TOL-BAD",
            configuration={"permissibleError": {"type": "MYSTERY"}},
        ):
            task = _record(db, services, value=492, unit="g")
            evaluation = _evaluation(db, task)
            assert evaluation.status == MeasurementEvaluationStatus.UNAVAILABLE.value
            assert "malformed" in evaluation.detail["reason"]
            assert evaluation.detail["note"] == INSPECTOR_REVIEW_NOTE

    def test_incomparable_dimensions_are_unavailable(self, db, services):
        with _procedure(
            db,
            code="TEST-TOL-PERCENT",
            configuration={"permissibleError": {"type": "PERCENT", "value": "4.5"}},
        ):
            inspection = _make_inspection(db, fields=_FIELDS)
            field = _net_quantity_field(db, inspection)
            field.normalized_value = "500"  # volume declaration
            field.unit = "ml"
            db.flush()
            task = services.verification.create_task(
                db,
                inspection_id=inspection.id,
                actor=_inspector(db),
                finding_id=None,
                field_id=field.id,
                task_type=VerificationTaskType.MEASUREMENT,
                reason="Verification with the calibrated scale.",
            )
            # 500 ml declared vs 492 g measured: different dimensions — no
            # conversion is invented, no tolerance is guessed.
            task = services.verification.record_result(
                db, task_id=task.id, actor=_inspector(db), measured_value=492, unit="g"
            )
            evaluation = _evaluation(db, task)
            assert evaluation.status == MeasurementEvaluationStatus.UNAVAILABLE.value
            assert "cannot be compared" in evaluation.detail["reason"]

    def test_evaluation_is_audited(self, db, services):
        from app.core.enums import AuditEventType
        from app.models import AuditEvent

        with _procedure(
            db,
            code="TEST-TOL-PERCENT",
            configuration={"permissibleError": {"type": "PERCENT", "value": "4.5"}},
        ):
            task = _record(db, services, value=492, unit="g")
            event = db.execute(
                select(AuditEvent).where(
                    AuditEvent.entity_type == "measurement_evaluation",
                    AuditEvent.inspection_id == task.inspection_id,
                )
            ).scalar_one()
            assert event.event_type == AuditEventType.MEASUREMENT_EVALUATED.value
            assert event.payload["status"] == "EVALUATED"
            assert event.payload["outcome"] == "WITHIN_TOLERANCE"
            assert event.payload["resultId"] == str(task.results[-1].id)


class TestFrozenHistory:
    def test_later_procedure_change_never_rewrites(self, db, services):
        with _procedure(
            db,
            code="TEST-TOL-PERCENT",
            configuration={"permissibleError": {"type": "PERCENT", "value": "1"}},
        ):
            task = _record(db, services, value=492, unit="g")
            evaluation = _evaluation(db, task)
            # -1.6% exceeds the 1% limit.
            assert evaluation.outcome == MeasurementOutcome.EXCEEDS_TOLERANCE.value
            original_limit = evaluation.detail["tolerance"]["limitInDeclaredUnit"]

            # The procedure is later widened to 10%…
            procedure = db.execute(
                select(RegulatoryProcedure).where(
                    RegulatoryProcedure.code == "TEST-TOL-PERCENT"
                )
            ).scalar_one()
            procedure.configuration = {
                "permissibleError": {"type": "PERCENT", "value": "10"}
            }
            db.commit()

            # …the recorded evaluation stays exactly as it was (spec §10).
            db.refresh(evaluation)
            assert evaluation.outcome == MeasurementOutcome.EXCEEDS_TOLERANCE.value
            assert evaluation.detail["tolerance"]["limitInDeclaredUnit"] == (
                original_limit
            )

    def test_one_evaluation_per_result(self, db, services):
        task = _record(db, services, value=492, unit="g")
        # The unique constraint makes the freeze physical, not conventional.
        with pytest.raises(Exception):
            db.add(
                MeasurementEvaluation(
                    verification_result_id=task.results[-1].id,
                    inspection_id=task.inspection_id,
                    status=MeasurementEvaluationStatus.UNAVAILABLE.value,
                )
            )
            db.flush()
        db.rollback()


def test_seed_version_is_real_and_active(db):
    """The ACTIVE seed version the evaluations bind to is real (non-demo)."""
    version = _active_version(db)
    assert version.status == RegulationVersionStatus.ACTIVE.value
    document = db.get(Regulation, version.regulation_id)
    assert document.is_demo is False
