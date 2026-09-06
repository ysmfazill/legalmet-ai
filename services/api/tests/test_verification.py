"""Evidence Planner + verification tests (UI-06).

Covers the contract:

* evidence plan: one row per finding + unreferenced declaration, ✓ existing /
  ⚠ missing derived from REAL persisted data, never fabricated
* gap semantics: NET_QUANTITY → REQUIRED measurement; REVIEW_REQUIRED field →
  RECOMMENDED observation; a gap is NOT a compliance verdict
* task lifecycle: create (reason mandatory, duplicate-guarded, anchor
  validated) → start → record result → complete; invalid transitions 409
* measurement: value > 0 + unit mandatory, stored SEPARATELY from the
  declared value, instrument status only when supplied, nothing evaluates
  declared-vs-measured
* decision gate: open REQUIRED tasks block a final decision; RECOMMENDED
  never do; the gate opens once the required evidence is recorded
* RBAC: anonymous 401, AUDITOR 403 on writes, assignment guard for INSPECTOR
* audit trail: every action lands as an append-only audit event
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.core.enums import (
    AuditEventType,
    UserRole,
    VerificationTaskStatus,
    VerificationTaskType,
)
from app.models import AuditEvent, User

from tests.test_compliance_engine import _FULL_COMPLIANT_FIELDS, _make_inspection

API = "/api/v1"
INSPECTOR_EMAIL = "inspector@legalmet.local"

# The full-compliant package, with the MRP reading made low-confidence so the
# planner surfaces a RECOMMENDED observation gap alongside the REQUIRED
# net-quantity measurement gap.
_FIELDS = [
    (
        {**spec, "confidence": 0.42, "status": "REVIEW_REQUIRED"}
        if spec["type"] == "MRP"
        else spec
    )
    for spec in _FULL_COMPLIANT_FIELDS
]


@pytest.fixture()
def planned(db, services):
    """An evaluated inspection: full-compliant fields, MRP low-confidence."""
    inspection = _make_inspection(db, fields=_FIELDS)
    evaluation = services.compliance.evaluate_inspection(
        db, inspection_id=inspection.id
    )
    db.refresh(evaluation)
    db.refresh(inspection)
    return inspection, evaluation


@pytest.fixture()
def plan(planned, client, inspector_headers):
    inspection, _ = planned
    resp = client.get(
        f"{API}/inspections/{inspection.id}/evidence-plan",
        headers=inspector_headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _inspector(db) -> User:
    return db.execute(
        select(User).where(User.email == INSPECTOR_EMAIL)
    ).scalar_one()


def _net_quantity_row(plan: dict) -> dict:
    rows = [
        i
        for i in plan["items"]
        if any(g["kind"] == "MEASUREMENT" for g in i["gaps"])
        or i["status"] == "VERIFIED"
    ]
    assert rows, "no net-quantity row in the plan"
    return rows[0]


def _finding_row(plan: dict) -> dict:
    rows = [i for i in plan["items"] if i["findingId"] is not None]
    assert rows
    return rows[0]


def _create_task(
    client, headers, inspection_id, row, *, task_type="MEASUREMENT",
    reason="Verify physical net quantity with a calibrated scale",
    requirement_level=None, field_id=None, finding_id=None,
):
    return client.post(
        f"{API}/inspections/{inspection_id}/verifications",
        headers=headers,
        json={
            "type": task_type,
            "reason": reason,
            "requirementLevel": requirement_level,
            "fieldId": field_id if field_id is not None else row.get("fieldId"),
            "findingId": finding_id if finding_id is not None else row.get("findingId"),
        },
    )


# ===========================================================================
# 1. Evidence plan
# ===========================================================================


class TestEvidencePlan:
    def test_every_finding_has_a_row(self, plan, planned):
        _, evaluation = planned
        plan_finding_ids = {i["findingId"] for i in plan["items"]}
        for finding in evaluation.findings:
            assert str(finding.id) in plan_finding_ids
        assert plan["counts"]["total"] == len(plan["items"])
        assert "never converts a declared-vs-measured difference" in plan["boundaryNote"]

    def test_net_quantity_row_requires_measurement(self, plan):
        row = _net_quantity_row(plan)
        gap = next(g for g in row["gaps"] if g["kind"] == "MEASUREMENT")
        assert gap["required"] is True
        assert gap["defaultLevel"] == "REQUIRED"
        assert "DECLARED" in gap["reason"]
        assert row["declaredValue"] == "500"
        assert row["unit"] == "g"
        assert row["status"] == "REQUIRES_VERIFICATION"
        # The counts are keyed by the counts vocabulary, not the status
        # vocabulary — a REQUIRES_VERIFICATION row must land in
        # requiringVerification (regression: status.lower() silently created
        # a phantom "requires_verification" key instead).
        assert plan["counts"]["requiringVerification"] == sum(
            1 for i in plan["items"] if i["status"] == "REQUIRES_VERIFICATION"
        )
        assert plan["counts"]["total"] == len(plan["items"])
        assert "requiresVerification" not in plan["counts"]

    def test_low_confidence_field_gets_recommended_observation(self, plan):
        gaps = [
            g for i in plan["items"] for g in i["gaps"]
            if g["kind"] == "INSPECTOR_OBSERVATION"
        ]
        assert gaps, "no observation gap for the low-confidence MRP field"
        assert all(g["required"] is False for g in gaps)
        assert all(g["defaultLevel"] == "RECOMMENDED" for g in gaps)

    def test_gap_is_not_a_violation(self, plan):
        """Evidence completeness is never framed as a compliance verdict."""
        for item in plan["items"]:
            if item["status"] == "REQUIRES_VERIFICATION":
                assert "NOT a compliance verdict" in item["summary"]

    def test_no_fabricated_evidence(self, plan, planned):
        """The builder attached no OCR/region rows, so every row must report
        them MISSING — the planner never invents a ✓."""
        for item in plan["items"]:
            kinds = {e["kind"]: e for e in item["evidence"]}
            assert kinds["OCR"]["status"] == "MISSING"
            assert kinds["REGION"]["status"] == "MISSING"
            assert kinds["IMAGE"]["status"] == "AVAILABLE"

    def test_every_row_has_an_anchor(self, plan, planned):
        """Each row is anchored to a finding and/or a declaration — nothing
        free-floating."""
        for item in plan["items"]:
            assert item["findingId"] is not None or item["fieldId"] is not None

    def test_unknown_inspection_404(self, client, inspector_headers):
        resp = client.get(
            f"{API}/inspections/{uuid.uuid4()}/evidence-plan",
            headers=inspector_headers,
        )
        assert resp.status_code == 404

    def test_anonymous_401(self, client, planned):
        inspection, _ = planned
        resp = client.get(f"{API}/inspections/{inspection.id}/evidence-plan")
        assert resp.status_code == 401

    def test_auditor_can_read_plan(self, client, auditor_headers, planned):
        inspection, _ = planned
        resp = client.get(
            f"{API}/inspections/{inspection.id}/evidence-plan",
            headers=auditor_headers,
        )
        assert resp.status_code == 200


# ===========================================================================
# 2. Task creation + RBAC
# ===========================================================================


class TestCreateTask:
    def test_create_measurement_task(self, client, inspector_headers, plan, planned):
        inspection, _ = planned
        row = _net_quantity_row(plan)
        resp = _create_task(client, inspector_headers, inspection.id, row)
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["status"] == "PENDING"
        assert body["requirementLevel"] == "REQUIRED"
        assert body["taskType"] == "MEASUREMENT"
        assert body["findingId"] == row["findingId"]
        assert body["extractedFieldId"] == row["fieldId"]
        assert body["reason"].startswith("Verify physical net quantity")

    def test_duplicate_open_task_409(self, client, inspector_headers, plan, planned):
        inspection, _ = planned
        row = _net_quantity_row(plan)
        first = _create_task(client, inspector_headers, inspection.id, row)
        assert first.status_code == 201
        second = _create_task(client, inspector_headers, inspection.id, row)
        assert second.status_code == 409
        assert "already exists" in second.json()["error"]["message"]

    def test_reason_mandatory(self, client, inspector_headers, plan, planned):
        inspection, _ = planned
        row = _net_quantity_row(plan)
        resp = _create_task(client, inspector_headers, inspection.id, row, reason="x")
        assert resp.status_code == 422

    def test_anchor_mandatory(self, client, inspector_headers, planned):
        inspection, _ = planned
        resp = _create_task(
            client, inspector_headers, inspection.id, {},
            field_id=None, finding_id=None,
        )
        assert resp.status_code == 422

    def test_cross_inspection_anchor_rejected(self, client, inspector_headers, planned, db, services):
        inspection, _ = planned
        other = _make_inspection(db, fields=_FIELDS)
        other_eval = services.compliance.evaluate_inspection(
            db, inspection_id=other.id
        )
        db.refresh(other_eval)
        resp = _create_task(
            client, inspector_headers, inspection.id, {},
            finding_id=str(other_eval.findings[0].id),
        )
        assert resp.status_code == 422

    def test_anonymous_401(self, client, planned):
        inspection, _ = planned
        resp = client.post(
            f"{API}/inspections/{inspection.id}/verifications",
            json={"type": "MEASUREMENT", "reason": "nope"},
        )
        assert resp.status_code == 401

    def test_auditor_cannot_create(self, client, auditor_headers, plan, planned):
        inspection, _ = planned
        row = _net_quantity_row(plan)
        resp = _create_task(client, auditor_headers, inspection.id, row)
        assert resp.status_code == 403

    def test_unknown_inspection_404(self, client, inspector_headers, plan):
        resp = _create_task(client, inspector_headers, uuid.uuid4(), {})
        assert resp.status_code == 404


# ===========================================================================
# 3. Lifecycle + measurement recording
# ===========================================================================


class TestLifecycle:
    def test_start_result_complete(self, client, inspector_headers, plan, planned):
        inspection, _ = planned
        row = _net_quantity_row(plan)
        task = _create_task(client, inspector_headers, inspection.id, row).json()

        started = client.post(
            f"{API}/verifications/{task['id']}/start", headers=inspector_headers
        )
        assert started.status_code == 200
        assert started.json()["status"] == "IN_PROGRESS"
        assert started.json()["startedAt"] is not None

        result = client.post(
            f"{API}/verifications/{task['id']}/result",
            headers=inspector_headers,
            json={
                "measuredValue": 492,
                "unit": "g",
                "instrumentId": "SCALE-LM-0142",
                "instrumentVerificationStatus": "Verified until 2027-01-15",
                "notes": "Average of three weighings",
            },
        )
        assert result.status_code == 200, result.text
        body = result.json()
        assert body["status"] == "COMPLETED"
        assert body["completedAt"] is not None
        recorded = body["results"][0]
        assert recorded["measuredValue"] == 492
        assert recorded["unit"] == "g"
        assert recorded["instrumentId"] == "SCALE-LM-0142"
        assert recorded["recordedByName"] is not None

    def test_declared_value_unchanged_after_measurement(
        self, client, inspector_headers, plan, planned
    ):
        """The declared 500 g stays on the field; 492 g lives only in the
        result — the two are never merged or auto-evaluated."""
        inspection, _ = planned
        row = _net_quantity_row(plan)
        task = _create_task(client, inspector_headers, inspection.id, row).json()
        client.post(
            f"{API}/verifications/{task['id']}/result",
            headers=inspector_headers,
            json={"measuredValue": 492, "unit": "g"},
        )
        fresh = client.get(
            f"{API}/inspections/{inspection.id}/evidence-plan",
            headers=inspector_headers,
        ).json()
        updated = _net_quantity_row(fresh)
        assert updated["declaredValue"] == "500"
        assert updated["status"] == "VERIFIED"
        assert updated["verification"]["latestResult"]["measuredValue"] == 492
        assert updated["gaps"] == []
        assert "does not evaluate the difference" in updated["summary"]

    def test_field_only_task_completes_the_finding_row(
        self, client, inspector_headers, plan, planned
    ):
        """A task created via fieldId alone (findingId NULL) must still close
        the gap on the FINDING row of the same declaration. The plan links
        tasks to rows by their shared extracted field, not only by finding id
        (regression: the finding row stayed REQUIRES_VERIFICATION forever
        while the completed task existed, invisible to it)."""
        inspection, _ = planned
        row = _net_quantity_row(plan)
        assert row["findingId"] is not None, "the regression needs a finding row"

        resp = client.post(
            f"{API}/inspections/{inspection.id}/verifications",
            headers=inspector_headers,
            json={
                "type": "MEASUREMENT",
                "reason": "Weigh the physical contents on a calibrated scale",
                "fieldId": row["fieldId"],
            },
        )
        assert resp.status_code == 201, resp.text
        task = resp.json()
        assert task["findingId"] is None  # a field-only anchor is legal

        client.post(
            f"{API}/verifications/{task['id']}/result",
            headers=inspector_headers,
            json={"measuredValue": 492, "unit": "g"},
        )
        fresh = client.get(
            f"{API}/inspections/{inspection.id}/evidence-plan",
            headers=inspector_headers,
        ).json()
        updated = _net_quantity_row(fresh)
        assert updated["status"] == "VERIFIED", updated["status"]
        assert updated["verification"]["id"] == task["id"]
        assert updated["verification"]["latestResult"]["measuredValue"] == 492
        assert updated["gaps"] == []

    def test_measurement_requires_unit(self, client, inspector_headers, plan, planned):
        inspection, _ = planned
        row = _net_quantity_row(plan)
        task = _create_task(client, inspector_headers, inspection.id, row).json()
        resp = client.post(
            f"{API}/verifications/{task['id']}/result",
            headers=inspector_headers,
            json={"measuredValue": 492},
        )
        assert resp.status_code == 422

    def test_measurement_requires_positive_value(
        self, client, inspector_headers, plan, planned
    ):
        inspection, _ = planned
        row = _net_quantity_row(plan)
        task = _create_task(client, inspector_headers, inspection.id, row).json()
        for bad in (0, -5):
            resp = client.post(
                f"{API}/verifications/{task['id']}/result",
                headers=inspector_headers,
                json={"measuredValue": bad, "unit": "g"},
            )
            assert resp.status_code == 422

    def test_measurement_requires_value(self, client, inspector_headers, plan, planned):
        inspection, _ = planned
        row = _net_quantity_row(plan)
        task = _create_task(client, inspector_headers, inspection.id, row).json()
        resp = client.post(
            f"{API}/verifications/{task['id']}/result",
            headers=inspector_headers,
            json={"unit": "g"},
        )
        assert resp.status_code == 422

    def test_observation_task_requires_observation(
        self, client, inspector_headers, plan, planned
    ):
        inspection, _ = planned
        row = next(
            i for i in plan["items"]
            if any(g["kind"] == "INSPECTOR_OBSERVATION" for g in i["gaps"])
        )
        task = _create_task(
            client, inspector_headers, inspection.id, row,
            task_type="INSPECTOR_OBSERVATION", reason="Re-read the MRP marking",
        ).json()
        assert task["requirementLevel"] == "RECOMMENDED"
        resp = client.post(
            f"{API}/verifications/{task['id']}/result",
            headers=inspector_headers,
            json={"measuredValue": 60, "unit": "INR"},
        )
        assert resp.status_code == 422
        ok = client.post(
            f"{API}/verifications/{task['id']}/result",
            headers=inspector_headers,
            json={"observation": "MRP reads ₹ 60.00, matches the declaration."},
        )
        assert ok.status_code == 200
        assert ok.json()["status"] == "COMPLETED"

    def test_result_on_completed_409(self, client, inspector_headers, plan, planned):
        inspection, _ = planned
        row = _net_quantity_row(plan)
        task = _create_task(client, inspector_headers, inspection.id, row).json()
        first = client.post(
            f"{API}/verifications/{task['id']}/result",
            headers=inspector_headers,
            json={"measuredValue": 492, "unit": "g"},
        )
        assert first.status_code == 200
        second = client.post(
            f"{API}/verifications/{task['id']}/result",
            headers=inspector_headers,
            json={"measuredValue": 493, "unit": "g"},
        )
        assert second.status_code == 409
        assert "append-only" in second.json()["error"]["message"]

    def test_cancel_then_recreate(self, client, inspector_headers, plan, planned):
        inspection, _ = planned
        row = _net_quantity_row(plan)
        task = _create_task(client, inspector_headers, inspection.id, row).json()
        no_reason = client.post(
            f"{API}/verifications/{task['id']}/cancel",
            headers=inspector_headers, json={"reason": "x"},
        )
        assert no_reason.status_code == 422
        cancelled = client.post(
            f"{API}/verifications/{task['id']}/cancel",
            headers=inspector_headers,
            json={"reason": "Wrong anchor; superseded by a corrected field."},
        )
        assert cancelled.status_code == 200
        assert cancelled.json()["status"] == "CANCELLED"
        # The anchor is free again.
        again = _create_task(client, inspector_headers, inspection.id, row)
        assert again.status_code == 201

    def test_start_on_completed_409(self, client, inspector_headers, plan, planned):
        inspection, _ = planned
        row = _net_quantity_row(plan)
        task = _create_task(client, inspector_headers, inspection.id, row).json()
        client.post(
            f"{API}/verifications/{task['id']}/result",
            headers=inspector_headers,
            json={"measuredValue": 492, "unit": "g"},
        )
        resp = client.post(
            f"{API}/verifications/{task['id']}/start", headers=inspector_headers
        )
        assert resp.status_code == 409

    def test_get_task_lists_results(self, client, inspector_headers, plan, planned):
        inspection, _ = planned
        row = _net_quantity_row(plan)
        task = _create_task(client, inspector_headers, inspection.id, row).json()
        client.post(
            f"{API}/verifications/{task['id']}/result",
            headers=inspector_headers,
            json={"measuredValue": 492, "unit": "g"},
        )
        listing = client.get(
            f"{API}/inspections/{inspection.id}/verifications",
            headers=inspector_headers,
        )
        assert listing.status_code == 200
        assert len(listing.json()["tasks"]) == 1
        one = client.get(
            f"{API}/verifications/{task['id']}", headers=inspector_headers
        )
        assert one.status_code == 200
        assert one.json()["results"][0]["measuredValue"] == 492

    def test_unknown_task_404(self, client, inspector_headers):
        resp = client.get(f"{API}/verifications/{uuid.uuid4()}", headers=inspector_headers)
        assert resp.status_code == 404


# ===========================================================================
# 4. Decision gate
# ===========================================================================


class TestDecisionGate:
    def test_required_task_blocks_decision(self, client, inspector_headers, plan, planned):
        inspection, _ = planned
        row = _net_quantity_row(plan)
        task = _create_task(client, inspector_headers, inspection.id, row).json()

        status = client.get(
            f"{API}/inspections/{inspection.id}/review-status",
            headers=inspector_headers,
        ).json()
        assert status["verificationTotal"] == 1
        assert status["verificationOpenRequired"] == 1
        assert any(
            "Required verification task" in b for b in status["decisionBlockers"]
        )

        resp = client.post(
            f"{API}/inspections/{inspection.id}/decision",
            headers=inspector_headers,
            json={"decision": "COMPLIANT", "reason": "All good"},
        )
        assert resp.status_code == 409
        assert "Required verification task" in resp.json()["error"]["message"]

    def test_gate_opens_after_completion(
        self, client, inspector_headers, plan, planned
    ):
        inspection, _ = planned
        row = _net_quantity_row(plan)
        task = _create_task(client, inspector_headers, inspection.id, row).json()
        client.post(
            f"{API}/verifications/{task['id']}/result",
            headers=inspector_headers,
            json={"measuredValue": 492, "unit": "g"},
        )
        status = client.get(
            f"{API}/inspections/{inspection.id}/review-status",
            headers=inspector_headers,
        ).json()
        assert status["verificationOpenRequired"] == 0
        assert status["verificationCompleted"] == 1

        resp = client.post(
            f"{API}/inspections/{inspection.id}/decision",
            headers=inspector_headers,
            json={
                "decision": "COMPLIANT",
                "reason": "Measured 492 g against 500 g declared; within the "
                "permissible error I applied.",
            },
        )
        assert resp.status_code == 200, resp.text

    def test_recommended_task_never_blocks(
        self, client, inspector_headers, plan, planned
    ):
        """An AI-recommended verification is advice, not an obligation."""
        inspection, _ = planned
        row = next(
            i for i in plan["items"]
            if any(g["kind"] == "INSPECTOR_OBSERVATION" for g in i["gaps"])
        )
        task = _create_task(
            client, inspector_headers, inspection.id, row,
            task_type="INSPECTOR_OBSERVATION", reason="Re-read the MRP marking",
        ).json()
        assert task["requirementLevel"] == "RECOMMENDED"

        status = client.get(
            f"{API}/inspections/{inspection.id}/review-status",
            headers=inspector_headers,
        ).json()
        assert status["verificationTotal"] == 1
        assert status["verificationOpenRequired"] == 0

        resp = client.post(
            f"{API}/inspections/{inspection.id}/decision",
            headers=inspector_headers,
            json={"decision": "COMPLIANT", "reason": "All good"},
        )
        assert resp.status_code == 200, resp.text


# ===========================================================================
# 5. Audit trail
# ===========================================================================


class TestAuditTrail:
    def test_full_lifecycle_audited(self, client, inspector_headers, plan, planned):
        inspection, _ = planned
        row = _net_quantity_row(plan)
        task = _create_task(client, inspector_headers, inspection.id, row).json()
        client.post(
            f"{API}/verifications/{task['id']}/start", headers=inspector_headers
        )
        client.post(
            f"{API}/verifications/{task['id']}/result",
            headers=inspector_headers,
            json={
                "measuredValue": 492,
                "unit": "g",
                "instrumentId": "SCALE-LM-0142",
            },
        )

        events = client.get(
            f"{API}/inspections/{inspection.id}/audit",
            headers=inspector_headers,
        ).json()
        types = {e["eventType"] for e in events}
        for expected in (
            "VERIFICATION_CREATED",
            "VERIFICATION_STARTED",
            "VERIFICATION_RESULT_RECORDED",
            "VERIFICATION_COMPLETED",
        ):
            assert expected in types
        # The recorded-result event carries the instrument metadata.
        recorded = next(
            e for e in events if e["eventType"] == "VERIFICATION_RESULT_RECORDED"
        )
        assert recorded["payload"]["measuredValue"] == 492
        assert recorded["payload"]["instrumentId"] == "SCALE-LM-0142"


# ===========================================================================
# 6. Service-level: assignment guard + instrument-status honesty
# ===========================================================================


class TestServiceGuards:
    def test_assignment_guard_rejects_outsider(self, db, services, planned):
        """A formally-assigned inspection rejects another inspector, accepts
        the assigned one (and a supervisor would pass too)."""
        from app.core.errors import ForbiddenError
        from app.models import ExtractedField, Package

        inspection, _ = planned
        assigned = User(
            email=f"assigned-{uuid.uuid4().hex[:6]}@legalmet.local",
            hashed_password="x",
            full_name="Assigned Inspector",
            role=UserRole.INSPECTOR.value,
        )
        outsider = User(
            email=f"outsider-{uuid.uuid4().hex[:6]}@legalmet.local",
            hashed_password="x",
            full_name="Outsider Inspector",
            role=UserRole.INSPECTOR.value,
        )
        db.add_all([assigned, outsider])
        db.flush()
        inspection.inspector_id = assigned.id
        db.add(
            AuditEvent(
                event_type=AuditEventType.INSPECTION_ASSIGNED.value,
                entity_type="inspection",
                entity_id=inspection.id,
                actor_id=assigned.id,
                inspection_id=inspection.id,
                payload={},
            )
        )
        db.commit()

        field = db.execute(
            select(ExtractedField)
            .join(Package, Package.id == ExtractedField.package_id)
            .where(
                Package.inspection_id == inspection.id,
                ExtractedField.field_type == "NET_QUANTITY",
            )
        ).scalars().one()

        with pytest.raises(ForbiddenError):
            services.verification.create_task(
                db,
                inspection_id=inspection.id,
                actor=outsider,
                finding_id=None,
                field_id=field.id,
                task_type=VerificationTaskType.MEASUREMENT,
                reason="Outsider attempt",
            )

        task = services.verification.create_task(
            db,
            inspection_id=inspection.id,
            actor=assigned,
            finding_id=None,
            field_id=field.id,
            task_type=VerificationTaskType.MEASUREMENT,
            reason="Verify physical net quantity with a calibrated scale",
        )
        assert task.status == "PENDING"

    def test_instrument_status_never_invented(self, db, services, planned):
        """No instrument verification status supplied → stored as None
        ("not recorded"), never defaulted to "Verified"."""
        from app.models import ExtractedField, Package

        inspection, _ = planned
        actor = _inspector(db)
        field = db.execute(
            select(ExtractedField)
            .join(Package, Package.id == ExtractedField.package_id)
            .where(
                Package.inspection_id == inspection.id,
                ExtractedField.field_type == "NET_QUANTITY",
            )
        ).scalars().one()

        task = services.verification.create_task(
            db,
            inspection_id=inspection.id,
            actor=actor,
            finding_id=None,
            field_id=field.id,
            task_type=VerificationTaskType.MEASUREMENT,
            reason="Verify physical net quantity with a calibrated scale",
        )
        task = services.verification.record_result(
            db,
            task_id=task.id,
            actor=actor,
            measured_value=492,
            unit="g",
            instrument_id="SCALE-LM-0142",
        )
        assert task.status == VerificationTaskStatus.COMPLETED.value
        result = task.latest_result
        assert result is not None
        assert result.instrument_verification_status is None
        assert result.measured_value == 492
        # The declared value on the field is untouched.
        db.refresh(field)
        assert field.normalized_value == "500"
        assert field.corrected_value is None
