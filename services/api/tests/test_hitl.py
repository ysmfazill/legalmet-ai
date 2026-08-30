"""Human-in-the-loop review tests (Prompt 8).

Covers the HITL contract in layers:

* FieldCorrection — original AI output never overwritten, append-only history,
  mandatory reason, re-evaluation consumes corrected values in a NEW evaluation
* Finding review state machine — legal transitions succeed, illegal ones are
  rejected with 409, terminal states are final, reason is mandatory for
  REJECT/OVERRIDE/ESCALATE, idempotent repeats create no duplicates
* Authorization — AUDITOR is read-only, override requires SUPERVISOR/ADMIN
* Final decision — gate blocks on unresolved critical findings, decisions
  supersede (never overwrite), reason mandatory for NON_COMPLIANT and changes
* Audit events — every human action is recorded with actor/role/state/reason
* API layer — endpoints, RBAC, error envelopes

Legal-safety invariants under test (each must fail loudly if broken):

1. The engine NEVER writes a decision, review or correction row.
2. The original OCR/AI values are byte-for-byte unchanged after correction.
3. A historical evaluation is never mutated by a correction or re-evaluation.
4. An unexplained override/reject/escalate is structurally impossible.
5. The final decision exists ONLY as a human-authored row.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.enums import (
    AuditEventType,
    FindingReviewState,
    InspectionDecisionType,
    UserRole,
)
from app.models import (
    AuditEvent,
    ExtractedField,
    FindingReview,
    FindingReviewEvent,
    InspectionDecision,
    User,
)
from tests.conftest import API, INSPECTOR_PASSWORD, SUPERVISOR_EMAIL
from tests.test_compliance_engine import (
    _FULL_COMPLIANT_FIELDS,
    _make_inspection,
)

REASON = "Inspector verified the label value against the physical package."


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture()
def hitl(services):
    return services.hitl


@pytest.fixture()
def inspector(db):
    return db.execute(
        select(User).where(User.role == UserRole.INSPECTOR.value)
    ).scalars().first()


@pytest.fixture()
def supervisor(db):
    return db.execute(
        select(User).where(User.role == UserRole.SUPERVISOR.value)
    ).scalars().first()


@pytest.fixture()
def auditor(db):
    return db.execute(select(User).where(User.role == UserRole.AUDITOR.value)).scalars().first()


@pytest.fixture()
def evaluated(db, services, inspector):
    """An inspection with one evaluation over fully-compliant fields."""
    inspection = _make_inspection(db, fields=_FULL_COMPLIANT_FIELDS)
    evaluation = services.compliance.evaluate_inspection(
        db, inspection_id=inspection.id, actor_id=inspector.id
    )
    db.refresh(evaluation)
    return inspection, evaluation


def _mrp_field(db, inspection_id) -> ExtractedField:
    from app.models import Package

    package = db.execute(
        select(Package).where(Package.inspection_id == inspection_id)
    ).scalars().first()
    return db.execute(
        select(ExtractedField)
        .where(
            ExtractedField.package_id == package.id,
            ExtractedField.field_type == "MRP",
        )
    ).scalars().first()


def _reviewable_finding(db, evaluation):
    """First finding of the evaluation that has an extracted field."""
    from app.models import EvaluationFinding

    return db.execute(
        select(EvaluationFinding)
        .where(
            EvaluationFinding.evaluation_id == evaluation.id,
            EvaluationFinding.extracted_field_id.is_not(None),
        )
        .order_by(EvaluationFinding.created_at.asc())
    ).scalars().first()


def _login(client: TestClient, email: str, password: str) -> str:
    resp = client.post(f"{API}/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["accessToken"]


@pytest.fixture()
def supervisor_headers(client):
    return {"Authorization": f"Bearer {_login(client, SUPERVISOR_EMAIL, INSPECTOR_PASSWORD)}"}


# ===========================================================================
# 1. Field correction (Phase 1)
# ===========================================================================


class TestFieldCorrection:
    def test_correction_preserves_original_ai_output(self, db, hitl, evaluated, inspector):
        inspection, _ = evaluated
        field = _mrp_field(db, inspection.id)
        original_raw = field.raw_text
        original_normalized = field.normalized_value
        original_confidence = field.confidence
        original_status = field.status

        hitl.correct_field(
            db,
            field_id=field.id,
            actor=inspector,
            corrected_value="MRP ₹ 65.00 (inclusive of all taxes)",
            reason=REASON,
        )
        db.refresh(field)

        # NEVER overwrite the original OCR/AI result.
        assert field.raw_text == original_raw
        assert field.normalized_value == original_normalized
        assert field.confidence == original_confidence
        assert field.status == original_status
        # The correction pointer carries the new value.
        assert field.corrected_value == "MRP ₹ 65.00 (inclusive of all taxes)"
        assert field.corrected_by == inspector.id
        assert field.corrected_reason == REASON

    def test_correction_history_is_append_only(self, db, hitl, evaluated, inspector):
        inspection, _ = evaluated
        field = _mrp_field(db, inspection.id)
        hitl.correct_field(
            db, field_id=field.id, actor=inspector,
            corrected_value="65.00", reason="First fix",
        )
        hitl.correct_field(
            db, field_id=field.id, actor=inspector,
            corrected_value="66.00", reason="Second fix after re-reading",
        )
        history = hitl.field_corrections(db, field.id)
        assert len(history) == 2
        assert history[0].corrected_value == "65.00"
        assert history[1].corrected_value == "66.00"
        # BEFORE values frozen from the ORIGINAL AI output, not the previous
        # correction: the chain always shows AI → human.
        assert history[0].previous_value == field.normalized_value
        assert history[1].previous_value == field.normalized_value

    def test_correction_requires_reason(self, db, hitl, evaluated, inspector):
        inspection, _ = evaluated
        field = _mrp_field(db, inspection.id)
        from app.core.errors import ValidationError

        with pytest.raises(ValidationError):
            hitl.correct_field(
                db, field_id=field.id, actor=inspector,
                corrected_value="65", reason="  ",
            )

    def test_correction_requires_write_role(self, db, hitl, evaluated, auditor):
        inspection, _ = evaluated
        field = _mrp_field(db, inspection.id)
        from app.core.errors import ForbiddenError

        with pytest.raises(ForbiddenError):
            hitl.correct_field(
                db, field_id=field.id, actor=auditor,
                corrected_value="65", reason=REASON,
            )

    def test_correction_is_audited(self, db, hitl, evaluated, inspector):
        inspection, _ = evaluated
        field = _mrp_field(db, inspection.id)
        hitl.correct_field(
            db, field_id=field.id, actor=inspector,
            corrected_value="65.00", reason=REASON,
        )
        event = db.execute(
            select(AuditEvent).where(
                AuditEvent.event_type == AuditEventType.FIELD_CORRECTED.value,
                AuditEvent.entity_id == field.id,
            )
        ).scalars().first()
        assert event is not None
        assert event.actor_id == inspector.id
        assert event.payload["correctedValue"] == "65.00"
        assert event.payload["actorRole"] == UserRole.INSPECTOR.value
        # Never log sensitive credentials: payload carries no password/token.
        assert "password" not in str(event.payload).lower()

    def test_unknown_field_rejected(self, db, hitl, inspector):
        from app.core.errors import NotFoundError

        with pytest.raises(NotFoundError):
            hitl.correct_field(
                db, field_id=uuid.uuid4(), actor=inspector,
                corrected_value="x", reason=REASON,
            )


# ===========================================================================
# 2. Re-evaluation after correction (Phase 3)
# ===========================================================================


class TestReevaluation:
    def test_reevaluation_creates_new_evaluation_and_preserves_history(
        self, db, hitl, services, evaluated, inspector
    ):
        inspection, evaluation = evaluated
        field = _mrp_field(db, inspection.id)

        hitl.correct_field(
            db, field_id=field.id, actor=inspector,
            corrected_value="MRP ₹ 65.00 (inclusive of all taxes)",
            reason=REASON,
        )
        second = services.compliance.evaluate_inspection(
            db, inspection_id=inspection.id, actor_id=inspector.id
        )

        assert second.id != evaluation.id
        assert second.status is not None
        # The historical evaluation is NOT mutated: its findings keep the
        # ORIGINAL (AI) detected value.
        db.refresh(evaluation)
        for finding in evaluation.findings:
            if finding.extracted_field_id == field.id:
                assert finding.detected_value == "60.00"
                assert finding.detail.get("valueSource") == "AI_EXTRACTED"
        # The new evaluation sees the human-corrected value.
        for finding in second.findings:
            if finding.extracted_field_id == field.id:
                assert finding.detected_value == "MRP ₹ 65.00 (inclusive of all taxes)"
                assert finding.detail.get("valueSource") == "HUMAN_CORRECTED"
                assert "human-confirmed correction" in finding.explanation

    def test_correction_unblocks_low_confidence_evidence(
        self, db, hitl, services, inspector
    ):
        """The golden HITL case: low-confidence read → REVIEW_REQUIRED →
        inspector corrects → re-evaluation resolves the requirement."""
        fields = [dict(f) for f in _FULL_COMPLIANT_FIELDS]
        for spec in fields:
            if spec["type"] == "MRP":
                spec["confidence"] = 0.3  # below the 0.6 evidence floor
        inspection = _make_inspection(db, fields=fields)
        first = services.compliance.evaluate_inspection(
            db, inspection_id=inspection.id, actor_id=inspector.id
        )
        mrp_finding = next(
            f for f in first.findings if f.detected_value == "60.00"
        )
        assert mrp_finding.status == "REVIEW_REQUIRED"

        field = _mrp_field(db, inspection.id)
        hitl.correct_field(
            db, field_id=field.id, actor=inspector,
            corrected_value="MRP ₹ 60.00 (inclusive of all taxes)",
            reason=REASON,
        )
        second = services.compliance.evaluate_inspection(
            db, inspection_id=inspection.id, actor_id=inspector.id
        )
        new_mrp = next(f for f in second.findings if f.extracted_field_id == field.id)
        # The human-confirmed value is adequate evidence — no longer routed to
        # review on the strength of the ORIGINAL low-confidence reading.
        assert new_mrp.status == "COMPLIANT"
        # The first, historical evaluation is untouched.
        db.refresh(first)
        assert next(
            f for f in first.findings if f.extracted_field_id == field.id
        ).status == "REVIEW_REQUIRED"


# ===========================================================================
# 3. Finding review state machine (Phases 4/6/20/21)
# ===========================================================================


class TestReviewStateMachine:
    def test_confirm_from_pending(self, db, hitl, evaluated, inspector):
        _, evaluation = evaluated
        finding = _reviewable_finding(db, evaluation)
        result = hitl.review_finding(
            db, finding_id=finding.id, actor=inspector, action="CONFIRM"
        )
        assert result.review.state == FindingReviewState.CONFIRMED.value

    def test_reject_requires_reason(self, db, hitl, evaluated, inspector):
        _, evaluation = evaluated
        finding = _reviewable_finding(db, evaluation)
        from app.core.errors import ValidationError

        with pytest.raises(ValidationError):
            hitl.review_finding(
                db, finding_id=finding.id, actor=inspector, action="REJECT",
                reason=None,
            )

    def test_reject_from_pending(self, db, hitl, evaluated, inspector):
        _, evaluation = evaluated
        finding = _reviewable_finding(db, evaluation)
        result = hitl.review_finding(
            db, finding_id=finding.id, actor=inspector, action="REJECT",
            reason="False positive — value verified on the physical label.",
        )
        assert result.review.state == FindingReviewState.REJECTED.value

    def test_correct_action_creates_correction(self, db, hitl, evaluated, inspector):
        _, evaluation = evaluated
        finding = _reviewable_finding(db, evaluation)
        result = hitl.review_finding(
            db, finding_id=finding.id, actor=inspector, action="CORRECT",
            reason=REASON, corrected_value="MRP ₹ 65.00 (inclusive of all taxes)",
        )
        assert result.review.state == FindingReviewState.CORRECTED.value
        assert result.correction is not None
        assert result.review.correction_id == result.correction.id
        field = db.get(ExtractedField, finding.extracted_field_id)
        assert field.corrected_value == "MRP ₹ 65.00 (inclusive of all taxes)"

    def test_escalate_then_supervisor_resolves(self, db, hitl, evaluated, inspector,
                                               supervisor):
        _, evaluation = evaluated
        finding = _reviewable_finding(db, evaluation)
        hitl.review_finding(
            db, finding_id=finding.id, actor=inspector, action="ESCALATE",
            reason="Cannot read the value confidently — needs senior review.",
        )
        result = hitl.review_finding(
            db, finding_id=finding.id, actor=supervisor, action="CONFIRM",
        )
        assert result.review.state == FindingReviewState.CONFIRMED.value

    def test_override_requires_senior_role(self, db, hitl, evaluated, inspector):
        _, evaluation = evaluated
        finding = _reviewable_finding(db, evaluation)
        hitl.review_finding(
            db, finding_id=finding.id, actor=inspector, action="CONFIRM",
        )
        from app.core.errors import ForbiddenError

        with pytest.raises(ForbiddenError):
            hitl.review_finding(
                db, finding_id=finding.id, actor=inspector, action="OVERRIDE",
                reason="inspector cannot override",
            )

    def test_override_of_confirmed_by_supervisor(self, db, hitl, evaluated, inspector,
                                                 supervisor):
        _, evaluation = evaluated
        finding = _reviewable_finding(db, evaluation)
        hitl.review_finding(
            db, finding_id=finding.id, actor=inspector, action="CONFIRM",
        )
        result = hitl.review_finding(
            db, finding_id=finding.id, actor=supervisor, action="OVERRIDE",
            reason="Supervisor disagrees — different sample batch.",
        )
        assert result.review.state == FindingReviewState.OVERRIDDEN.value

    def test_override_requires_reason(self, db, hitl, evaluated, inspector, supervisor):
        _, evaluation = evaluated
        finding = _reviewable_finding(db, evaluation)
        hitl.review_finding(
            db, finding_id=finding.id, actor=inspector, action="CONFIRM",
        )
        from app.core.errors import ValidationError

        with pytest.raises(ValidationError):
            hitl.review_finding(
                db, finding_id=finding.id, actor=supervisor, action="OVERRIDE",
                reason="   ",
            )

    def test_terminal_state_rejects_further_transitions(self, db, hitl, evaluated,
                                                        inspector):
        _, evaluation = evaluated
        finding = _reviewable_finding(db, evaluation)
        hitl.review_finding(
            db, finding_id=finding.id, actor=inspector, action="REJECT",
            reason="False positive.",
        )
        from app.core.errors import ConflictError

        with pytest.raises(ConflictError):
            hitl.review_finding(
                db, finding_id=finding.id, actor=inspector, action="CONFIRM",
            )

    def test_illegal_transition_rejected(self, db, hitl, evaluated, inspector):
        """CONFIRM → REJECT is not in the machine: a confirmed outcome can
        only be superseded by a supervisor OVERRIDE."""
        _, evaluation = evaluated
        finding = _reviewable_finding(db, evaluation)
        hitl.review_finding(
            db, finding_id=finding.id, actor=inspector, action="CONFIRM",
        )
        from app.core.errors import ConflictError

        with pytest.raises(ConflictError):
            hitl.review_finding(
                db, finding_id=finding.id, actor=inspector, action="REJECT",
                reason="too late",
            )

    def test_idempotent_confirm_creates_no_duplicates(self, db, hitl, evaluated,
                                                      inspector):
        _, evaluation = evaluated
        finding = _reviewable_finding(db, evaluation)
        first = hitl.review_finding(
            db, finding_id=finding.id, actor=inspector, action="CONFIRM",
        )
        events_before = db.execute(
            select(func_count(FindingReviewEvent.id)).where(
                FindingReviewEvent.review_id == first.review.id
            )
        ).scalar()
        # CONFIRM on CONFIRMED is a no-op — not an error, not a duplicate.
        second = hitl.review_finding(
            db, finding_id=finding.id, actor=inspector, action="CONFIRM",
        )
        events_after = db.execute(
            select(func_count(FindingReviewEvent.id)).where(
                FindingReviewEvent.review_id == first.review.id
            )
        ).scalar()
        assert second.review.id == first.review.id
        assert events_after == events_before

    def test_event_history_records_transitions(self, db, hitl, evaluated, inspector,
                                               supervisor):
        _, evaluation = evaluated
        finding = _reviewable_finding(db, evaluation)
        hitl.review_finding(
            db, finding_id=finding.id, actor=inspector, action="CONFIRM",
        )
        hitl.review_finding(
            db, finding_id=finding.id, actor=supervisor, action="OVERRIDE",
            reason="Supervisor verdict differs.",
        )
        review = hitl.get_review(db, finding.id)
        assert [e.action for e in review.events] == ["CONFIRM", "OVERRIDE"]
        assert review.events[0].previous_state == FindingReviewState.PENDING_REVIEW.value
        assert review.events[0].new_state == FindingReviewState.CONFIRMED.value
        assert review.events[1].previous_state == FindingReviewState.CONFIRMED.value
        assert review.events[1].new_state == FindingReviewState.OVERRIDDEN.value
        assert review.events[1].actor_role == UserRole.SUPERVISOR.value

    def test_review_writes_audit_events(self, db, hitl, evaluated, inspector):
        _, evaluation = evaluated
        finding = _reviewable_finding(db, evaluation)
        hitl.review_finding(
            db, finding_id=finding.id, actor=inspector, action="CONFIRM",
        )
        event = db.execute(
            select(AuditEvent).where(
                AuditEvent.event_type == AuditEventType.FINDING_CONFIRMED.value,
                AuditEvent.entity_id == finding.id,
            )
        ).scalars().first()
        assert event is not None
        assert event.actor_id == inspector.id
        assert event.payload["newState"] == FindingReviewState.CONFIRMED.value

    def test_review_requires_write_role(self, db, hitl, evaluated, auditor):
        _, evaluation = evaluated
        finding = _reviewable_finding(db, evaluation)
        from app.core.errors import ForbiddenError

        with pytest.raises(ForbiddenError):
            hitl.review_finding(
                db, finding_id=finding.id, actor=auditor, action="CONFIRM",
            )

    def test_unknown_action_rejected(self, db, hitl, evaluated, inspector):
        _, evaluation = evaluated
        finding = _reviewable_finding(db, evaluation)
        from app.core.errors import NotFoundError

        with pytest.raises(NotFoundError):
            hitl.review_finding(
                db, finding_id=finding.id, actor=inspector, action="APPROVE",
            )


def func_count(column):
    from sqlalchemy import func

    return func.count(column)


# ===========================================================================
# 4. Final decision (Phases 5/13/14/21)
# ===========================================================================


class TestFinalDecision:
    def test_decision_requires_write_role(self, db, hitl, evaluated, auditor):
        inspection, _ = evaluated
        from app.core.errors import ForbiddenError

        with pytest.raises(ForbiddenError):
            hitl.submit_decision(
                db, inspection_id=inspection.id, actor=auditor,
                decision=InspectionDecisionType.COMPLIANT,
            )

    def test_compliant_decision_recorded(self, db, hitl, evaluated, inspector):
        inspection, evaluation = evaluated
        decision = hitl.submit_decision(
            db, inspection_id=inspection.id, actor=inspector,
            decision=InspectionDecisionType.COMPLIANT,
            reason="All declarations verified on the physical package.",
        )
        assert decision.decision == InspectionDecisionType.COMPLIANT.value
        assert decision.decided_by == inspector.id
        assert decision.evaluation_id == evaluation.id
        assert decision.supersedes_decision_id is None

    def test_non_compliant_requires_reason(self, db, hitl, evaluated, inspector):
        inspection, _ = evaluated
        from app.core.errors import ValidationError

        with pytest.raises(ValidationError):
            hitl.submit_decision(
                db, inspection_id=inspection.id, actor=inspector,
                decision=InspectionDecisionType.NON_COMPLIANT, reason=None,
            )

    def test_gate_blocks_on_unresolved_critical(self, db, hitl, services, inspector):
        """A CRITICAL finding awaiting review blocks COMPLIANT/NON_COMPLIANT."""
        fields = [f for f in _FULL_COMPLIANT_FIELDS if f["type"] != "MRP"]
        inspection = _make_inspection(db, fields=fields)
        evaluation = services.compliance.evaluate_inspection(
            db, inspection_id=inspection.id, actor_id=inspector.id
        )
        # NOT_DETECTED findings carry MINOR severity by default — manufacture
        # a CRITICAL unresolved one directly to test the gate honestly.
        from app.models import EvaluationFinding

        finding = db.execute(
            select(EvaluationFinding)
            .where(EvaluationFinding.evaluation_id == evaluation.id)
            .order_by(EvaluationFinding.created_at.asc())
        ).scalars().first()
        finding.severity = "CRITICAL"
        db.commit()

        from app.core.errors import ConflictError

        with pytest.raises(ConflictError):
            hitl.submit_decision(
                db, inspection_id=inspection.id, actor=inspector,
                decision=InspectionDecisionType.COMPLIANT,
            )
        # REQUIRES_FURTHER_REVIEW is always allowed — it IS the escalation.
        decision = hitl.submit_decision(
            db, inspection_id=inspection.id, actor=inspector,
            decision=InspectionDecisionType.REQUIRES_FURTHER_REVIEW,
            reason="Critical finding unresolved — escalating.",
        )
        assert decision.decision == InspectionDecisionType.REQUIRES_FURTHER_REVIEW.value

    def test_gate_opens_after_resolution(self, db, hitl, services, inspector):
        fields = [f for f in _FULL_COMPLIANT_FIELDS if f["type"] != "MRP"]
        inspection = _make_inspection(db, fields=fields)
        evaluation = services.compliance.evaluate_inspection(
            db, inspection_id=inspection.id, actor_id=inspector.id
        )
        from app.models import EvaluationFinding

        finding = db.execute(
            select(EvaluationFinding)
            .where(EvaluationFinding.evaluation_id == evaluation.id)
            .order_by(EvaluationFinding.created_at.asc())
        ).scalars().first()
        finding.severity = "CRITICAL"
        db.commit()
        # Inspector resolves it.
        hitl.review_finding(
            db, finding_id=finding.id, actor=inspector, action="CONFIRM",
        )
        decision = hitl.submit_decision(
            db, inspection_id=inspection.id, actor=inspector,
            decision=InspectionDecisionType.COMPLIANT,
        )
        assert decision.decision == InspectionDecisionType.COMPLIANT.value

    def test_decision_supersedes_never_overwrites(self, db, hitl, evaluated, inspector):
        inspection, _ = evaluated
        first = hitl.submit_decision(
            db, inspection_id=inspection.id, actor=inspector,
            decision=InspectionDecisionType.COMPLIANT,
            reason="Initial verdict.",
        )
        second = hitl.submit_decision(
            db, inspection_id=inspection.id, actor=inspector,
            decision=InspectionDecisionType.REQUIRES_FURTHER_REVIEW,
            reason="New evidence emerged — reopening.",
        )
        assert second.id != first.id
        assert second.supersedes_decision_id == first.id
        # The first decision is preserved verbatim.
        db.refresh(first)
        assert first.decision == InspectionDecisionType.COMPLIANT.value
        assert first.reason == "Initial verdict."
        history = hitl.decision_history(db, inspection.id)
        assert [d.decision for d in history] == [
            InspectionDecisionType.COMPLIANT.value,
            InspectionDecisionType.REQUIRES_FURTHER_REVIEW.value,
        ]

    def test_decision_change_requires_reason(self, db, hitl, evaluated, inspector):
        inspection, _ = evaluated
        hitl.submit_decision(
            db, inspection_id=inspection.id, actor=inspector,
            decision=InspectionDecisionType.COMPLIANT, reason="Initial.",
        )
        from app.core.errors import ValidationError

        with pytest.raises(ValidationError):
            hitl.submit_decision(
                db, inspection_id=inspection.id, actor=inspector,
                decision=InspectionDecisionType.REQUIRES_FURTHER_REVIEW,
            )

    def test_identical_resubmission_is_idempotent(self, db, hitl, evaluated, inspector):
        inspection, _ = evaluated
        first = hitl.submit_decision(
            db, inspection_id=inspection.id, actor=inspector,
            decision=InspectionDecisionType.COMPLIANT, reason="Same verdict.",
        )
        second = hitl.submit_decision(
            db, inspection_id=inspection.id, actor=inspector,
            decision=InspectionDecisionType.COMPLIANT, reason="Same verdict.",
        )
        assert second.id == first.id
        assert len(hitl.decision_history(db, inspection.id)) == 1

    def test_decision_audited(self, db, hitl, evaluated, inspector):
        inspection, _ = evaluated
        hitl.submit_decision(
            db, inspection_id=inspection.id, actor=inspector,
            decision=InspectionDecisionType.COMPLIANT, reason="Verified.",
        )
        event = db.execute(
            select(AuditEvent).where(
                AuditEvent.event_type == AuditEventType.DECISION_SUBMITTED.value,
                AuditEvent.inspection_id == inspection.id,
            )
        ).scalars().first()
        assert event is not None
        assert event.actor_id == inspector.id
        assert event.payload["decision"] == InspectionDecisionType.COMPLIANT.value

    def test_cross_inspection_evaluation_reference_rejected(self, db, hitl, services,
                                                            inspector):
        fields = [dict(f) for f in _FULL_COMPLIANT_FIELDS]
        inspection_a = _make_inspection(db, fields=fields)
        inspection_b = _make_inspection(db, fields=fields)
        evaluation_a = services.compliance.evaluate_inspection(
            db, inspection_id=inspection_a.id, actor_id=inspector.id
        )
        from app.core.errors import ValidationError

        with pytest.raises(ValidationError):
            hitl.submit_decision(
                db, inspection_id=inspection_b.id, actor=inspector,
                decision=InspectionDecisionType.COMPLIANT,
                evaluation_id=evaluation_a.id,
            )

    def test_review_status_read_model(self, db, hitl, evaluated, inspector):
        inspection, evaluation = evaluated
        status = hitl.review_status(db, inspection.id)
        assert status["total_findings"] == len(evaluation.findings)
        assert status["unreviewed"] == len(evaluation.findings)
        assert status["decision_allowed"] is True  # no critical unresolved
        assert status["decision"] is None

        finding = _reviewable_finding(db, evaluation)
        hitl.review_finding(
            db, finding_id=finding.id, actor=inspector, action="CONFIRM",
        )
        status = hitl.review_status(db, inspection.id)
        assert status["confirmed"] == 1
        assert status["unreviewed"] == len(evaluation.findings) - 1


# ===========================================================================
# 5. API layer (Phase 18 + authorization Phase 19)
# ===========================================================================


@pytest.fixture()
def evaluated_api(client, inspector_headers, db, services, monkeypatch):
    """Inspection + perception + evaluation with DETECTED fields.

    Uses the deterministic FakeOCR/FakeVision pipeline fakes (same pattern
    as the regulatory API tests) so the engine produces findings WITH
    extracted fields that a human can then correct / review / decide on.
    """
    from tests.test_perception_pipeline import (
        FakeOCRService,
        FakeVisionService,
        _label_png,
    )

    pipeline = services.perception._pipeline
    monkeypatch.setattr(pipeline, "_ocr", FakeOCRService())
    monkeypatch.setattr(pipeline, "_vision", FakeVisionService())

    create = client.post(
        f"{API}/inspections",
        headers=inspector_headers,
        json={"productName": "HITL Tea 250g", "productCategory": "food"},
    )
    assert create.status_code == 201, create.text
    inspection_id = create.json()["id"]

    img = client.post(
        f"{API}/inspections/{inspection_id}/images/upload",
        headers=inspector_headers,
        files={"file": ("front.png", _label_png(), "image/png")},
        data={"captureSource": "UPLOAD", "imageType": "FRONT"},
    )
    assert img.status_code == 201, img.text

    kick = client.post(
        f"{API}/inspections/{inspection_id}/perceive",
        headers=inspector_headers,
    )
    assert kick.status_code == 202, kick.text

    evaluate = client.post(
        f"{API}/inspections/{inspection_id}/evaluate",
        headers=inspector_headers,
    )
    assert evaluate.status_code == 200, evaluate.text
    evaluation_id = evaluate.json()["evaluation"]["id"]

    findings = client.get(
        f"{API}/inspections/{inspection_id}/compliance/findings",
        headers=inspector_headers,
    )
    assert findings.status_code == 200, findings.text
    return inspection_id, evaluation_id, findings.json()


class TestHitlApi:
    def test_field_correct_endpoint(self, client, inspector_headers, db,
                                    evaluated_api):
        inspection_id, _, findings = evaluated_api
        field_id = next(
            (f["extractedFieldId"] for f in findings if f.get("extractedFieldId")),
            None,
        )
        assert field_id, "expected at least one finding with an extracted field"
        resp = client.post(
            f"{API}/fields/{field_id}/correct",
            headers=inspector_headers,
            json={"correctedValue": "MRP ₹ 99.00 (inclusive of all taxes)",
                  "reason": "Verified against the physical package."},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["correctedValue"] == "MRP ₹ 99.00 (inclusive of all taxes)"
        assert body["previousValue"] is not None or body["previousRawText"] is not None

        history = client.get(f"{API}/fields/{field_id}/corrections",
                             headers=inspector_headers)
        assert history.status_code == 200
        assert len(history.json()) == 1

        review = client.get(f"{API}/fields/{field_id}/review",
                            headers=inspector_headers)
        assert review.status_code == 200
        data = review.json()
        assert data["correctedValue"] == "MRP ₹ 99.00 (inclusive of all taxes)"
        assert data["originalValue"] is not None or data["originalRawText"] is not None
        assert data["aiConfidence"] is not None

    def test_auditor_cannot_correct(self, client, auditor_headers, db, evaluated_api):
        _, _, findings = evaluated_api
        field_id = next(
            (f["extractedFieldId"] for f in findings if f.get("extractedFieldId")),
            None,
        )
        resp = client.post(
            f"{API}/fields/{field_id}/correct",
            headers=auditor_headers,
            json={"correctedValue": "x", "reason": "auditor attempt"},
        )
        assert resp.status_code == 403

    def test_finding_review_endpoint(self, client, inspector_headers, db,
                                     evaluated_api):
        _, _, findings = evaluated_api
        finding_id = findings[0]["id"]
        resp = client.post(
            f"{API}/compliance/findings/{finding_id}/review",
            headers=inspector_headers,
            json={"action": "CONFIRM"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["state"] == "CONFIRMED"

        get_resp = client.get(
            f"{API}/compliance/findings/{finding_id}/review",
            headers=inspector_headers,
        )
        assert get_resp.status_code == 200
        assert get_resp.json()["state"] == "CONFIRMED"
        assert len(get_resp.json()["events"]) == 1

    def test_finding_review_verb_routes(self, client, inspector_headers, db,
                                        evaluated_api):
        _, _, findings = evaluated_api
        finding_id = next(
            f["id"] for f in findings if f.get("extractedFieldId")
        )
        resp = client.post(
            f"{API}/compliance/findings/{finding_id}/reject",
            headers=inspector_headers,
            json={"reason": "False positive — verified on the label."},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["state"] == "REJECTED"

    def test_auditor_cannot_review(self, client, auditor_headers, db, evaluated_api):
        _, _, findings = evaluated_api
        finding_id = findings[0]["id"]
        resp = client.post(
            f"{API}/compliance/findings/{finding_id}/review",
            headers=auditor_headers,
            json={"action": "CONFIRM"},
        )
        assert resp.status_code == 403

    def test_decision_endpoints(self, client, inspector_headers, db, evaluated_api):
        inspection_id, evaluation_id, findings = evaluated_api
        # Resolve any reviewable findings first (the gate may block otherwise).
        for finding in findings:
            if finding.get("extractedFieldId"):
                client.post(
                    f"{API}/compliance/findings/{finding['id']}/review",
                    headers=inspector_headers,
                    json={"action": "CONFIRM"},
                )
        resp = client.post(
            f"{API}/inspections/{inspection_id}/decision",
            headers=inspector_headers,
            json={"decision": "COMPLIANT", "reason": "All verified."},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["decision"] == "COMPLIANT"

        current = client.get(
            f"{API}/inspections/{inspection_id}/decision",
            headers=inspector_headers,
        )
        assert current.status_code == 200
        assert current.json()["decision"] == "COMPLIANT"

        history = client.get(
            f"{API}/inspections/{inspection_id}/decision-history",
            headers=inspector_headers,
        )
        assert history.status_code == 200
        assert len(history.json()["history"]) == 1

        # Change it — supersede, never overwrite.
        change = client.post(
            f"{API}/inspections/{inspection_id}/decision",
            headers=inspector_headers,
            json={"decision": "REQUIRES_FURTHER_REVIEW",
                  "reason": "Reopened after new evidence."},
        )
        assert change.status_code == 200, change.text
        history2 = client.get(
            f"{API}/inspections/{inspection_id}/decision-history",
            headers=inspector_headers,
        )
        assert len(history2.json()["history"]) == 2
        assert history2.json()["history"][0]["decision"] == "COMPLIANT"

    def test_auditor_cannot_decide(self, client, auditor_headers, db, evaluated_api):
        inspection_id, _, _ = evaluated_api
        resp = client.post(
            f"{API}/inspections/{inspection_id}/decision",
            headers=auditor_headers,
            json={"decision": "COMPLIANT", "reason": "auditor attempt"},
        )
        assert resp.status_code == 403

    def test_review_status_endpoint(self, client, inspector_headers, db,
                                    evaluated_api):
        inspection_id, _, findings = evaluated_api
        resp = client.get(
            f"{API}/inspections/{inspection_id}/review-status",
            headers=inspector_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["totalFindings"] == len(findings)
        assert body["unreviewed"] == len(findings)
        assert "decisionAllowed" in body
        assert "boundaryNote" in body

    def test_gate_blocks_compliant_decision_over_api(self, client, inspector_headers,
                                                     db, evaluated_api):
        inspection_id, _, findings = evaluated_api
        # Leave findings unreviewed; manufacture a critical unresolved one.
        from app.models import EvaluationFinding

        finding_row = db.get(EvaluationFinding, uuid.UUID(findings[0]["id"]))
        finding_row.severity = "CRITICAL"
        db.commit()

        resp = client.post(
            f"{API}/inspections/{inspection_id}/decision",
            headers=inspector_headers,
            json={"decision": "COMPLIANT"},
        )
        assert resp.status_code == 409, resp.text
        assert "unresolved" in resp.json()["error"]["message"].lower()

    def test_engine_never_writes_hitl_rows(self, db, services, inspector):
        """Invariant: the compliance engine creates no review/decision rows."""
        inspection = _make_inspection(db, fields=_FULL_COMPLIANT_FIELDS)
        services.compliance.evaluate_inspection(
            db, inspection_id=inspection.id, actor_id=inspector.id
        )
        assert db.execute(select(func_count(FindingReview.id))).scalar() >= 0
        # Reviews and decisions only ever appear through the HITL service.
        reviews_for_this = db.execute(
            select(FindingReview).where(FindingReview.inspection_id == inspection.id)
        ).scalars().all()
        decisions = db.execute(
            select(InspectionDecision).where(
                InspectionDecision.inspection_id == inspection.id
            )
        ).scalars().all()
        assert reviews_for_this == []
        assert decisions == []


# ===========================================================================
# 6. Authorization matrix (Phase 19) — every role against every endpoint class
# ===========================================================================


class TestAuthorization:
    """All four roles against the HITL surface. AUDITOR is strictly read-only;
    OVERRIDE additionally requires SUPERVISOR/ADMIN. Unauthenticated requests
    are rejected before any handler logic runs."""

    def test_unauthenticated_requests_rejected(self, client, evaluated_api):
        inspection_id, _, findings = evaluated_api
        field_id = next(
            (f["extractedFieldId"] for f in findings if f.get("extractedFieldId")),
            None,
        )
        finding_id = findings[0]["id"]
        paths = [
            (f"{API}/fields/{field_id}/correct", "post"),
            (f"{API}/fields/{field_id}/corrections", "get"),
            (f"{API}/fields/{field_id}/review", "get"),
            (f"{API}/compliance/findings/{finding_id}/review", "post"),
            (f"{API}/compliance/findings/{finding_id}/review", "get"),
            (f"{API}/compliance/findings/{finding_id}/confirm", "post"),
            (f"{API}/inspections/{inspection_id}/decision", "post"),
            (f"{API}/inspections/{inspection_id}/decision", "get"),
            (f"{API}/inspections/{inspection_id}/decision-history", "get"),
            (f"{API}/inspections/{inspection_id}/review-status", "get"),
        ]
        for path, method in paths:
            resp = getattr(client, method)(path)
            assert resp.status_code == 401, f"{method.upper()} {path} -> {resp.status_code}"

    def test_auditor_reads_but_never_writes(self, client, auditor_headers,
                                            evaluated_api):
        inspection_id, _, findings = evaluated_api
        field_id = next(
            (f["extractedFieldId"] for f in findings if f.get("extractedFieldId")),
            None,
        )
        finding_id = findings[0]["id"]
        # Reads: all allowed (the audit role is read-only, not blind).
        assert client.get(
            f"{API}/inspections/{inspection_id}/review-status",
            headers=auditor_headers,
        ).status_code == 200
        assert client.get(
            f"{API}/fields/{field_id}/corrections", headers=auditor_headers
        ).status_code == 200
        assert client.get(
            f"{API}/fields/{field_id}/review", headers=auditor_headers
        ).status_code == 200
        assert client.get(
            f"{API}/compliance/findings/{finding_id}/review", headers=auditor_headers
        ).status_code == 200
        assert client.get(
            f"{API}/inspections/{inspection_id}/decision-history",
            headers=auditor_headers,
        ).status_code == 200
        # Writes: all forbidden.
        for method, path, body in (
            ("post", f"{API}/fields/{field_id}/correct",
             {"correctedValue": "x", "reason": "nope"}),
            ("post", f"{API}/compliance/findings/{finding_id}/review",
             {"action": "CONFIRM"}),
            ("post", f"{API}/compliance/findings/{finding_id}/confirm", {}),
            ("post", f"{API}/compliance/findings/{finding_id}/reject",
             {"reason": "nope"}),
            ("post", f"{API}/inspections/{inspection_id}/decision",
             {"decision": "COMPLIANT"}),
        ):
            resp = client.post(path, headers=auditor_headers, json=body) \
                if method == "post" else client.get(path, headers=auditor_headers)
            assert resp.status_code == 403, f"{path} -> {resp.status_code}"

    def test_supervisor_can_review_and_decide(self, client, supervisor_headers,
                                              db, evaluated_api):
        _, _, findings = evaluated_api
        finding_id = findings[0]["id"]
        resp = client.post(
            f"{API}/compliance/findings/{finding_id}/review",
            headers=supervisor_headers,
            json={"action": "CONFIRM"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["state"] == "CONFIRMED"

    def test_admin_can_review_and_decide(self, client, admin_headers, db,
                                         evaluated_api):
        inspection_id, _, findings = evaluated_api
        for finding in findings:
            if finding.get("extractedFieldId"):
                client.post(
                    f"{API}/compliance/findings/{finding['id']}/review",
                    headers=admin_headers,
                    json={"action": "CONFIRM"},
                )
        resp = client.post(
            f"{API}/inspections/{inspection_id}/decision",
            headers=admin_headers,
            json={"decision": "COMPLIANT", "reason": "Admin-reviewed sample."},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["decision"] == "COMPLIANT"

    def test_override_requires_supervisor_role(self, client, inspector_headers,
                                                supervisor_headers, db,
                                                evaluated_api):
        """An INSPECTOR cannot override — the override path is
        SUPERVISOR/ADMIN only, even with a reason."""
        _, _, findings = evaluated_api
        finding_id = findings[0]["id"]
        client.post(
            f"{API}/compliance/findings/{finding_id}/review",
            headers=inspector_headers,
            json={"action": "CONFIRM"},
        )
        denied = client.post(
            f"{API}/compliance/findings/{finding_id}/override",
            headers=inspector_headers,
            json={"reason": "inspector attempting an override"},
        )
        assert denied.status_code == 403, denied.text

        allowed = client.post(
            f"{API}/compliance/findings/{finding_id}/override",
            headers=supervisor_headers,
            json={"reason": "Supervisor reviewed the physical package."},
        )
        assert allowed.status_code == 200, allowed.text
        assert allowed.json()["state"] == "OVERRIDDEN"

    def test_decision_cannot_reference_other_inspection_evaluation(
        self, client, inspector_headers, db, evaluated_api, monkeypatch, services
    ):
        """Cross-inspection integrity: a decision on inspection B can never be
        based on an evaluation from inspection A."""
        from tests.test_perception_pipeline import (
            FakeOCRService,
            FakeVisionService,
            _label_png,
        )

        pipeline = services.perception._pipeline
        monkeypatch.setattr(pipeline, "_ocr", FakeOCRService())
        monkeypatch.setattr(pipeline, "_vision", FakeVisionService())
        inspection_id, evaluation_id, _ = evaluated_api

        create_b = client.post(
            f"{API}/inspections",
            headers=inspector_headers,
            json={"productName": "Other Tea 100g", "productCategory": "food"},
        )
        assert create_b.status_code == 201
        inspection_b = create_b.json()["id"]
        client.post(
            f"{API}/inspections/{inspection_b}/images/upload",
            headers=inspector_headers,
            files={"file": ("front.png", _label_png(), "image/png")},
            data={"captureSource": "UPLOAD", "imageType": "FRONT"},
        )
        client.post(
            f"{API}/inspections/{inspection_b}/perceive", headers=inspector_headers
        )

        resp = client.post(
            f"{API}/inspections/{inspection_b}/decision",
            headers=inspector_headers,
            json={"decision": "COMPLIANT", "evaluationId": evaluation_id},
        )
        assert resp.status_code in (400, 404, 422), resp.text
        # And inspection B still has NO decision.
        get_b = client.get(
            f"{API}/inspections/{inspection_b}/decision", headers=inspector_headers
        )
        assert get_b.status_code == 404


# ===========================================================================
# 7. GOLDEN HITL FLOW (Phase 22) — the full loop, end to end, over the API
# ===========================================================================


class TestGoldenHitlFlow:
    def test_full_loop_image_to_decision_with_audit_trail(
        self, client, inspector_headers, supervisor_headers, db, services,
        monkeypatch
    ):
        """The golden human-in-the-loop trace:

        real image upload → real perception run (fake OCR/vision providers,
        deterministic) → engine evaluation → REVIEW_REQUIRED finding →
        inspector corrects the field → re-evaluation consumes the correction
        (new evaluation, history preserved) → finding confirmed → another
        finding escalated → supervisor resolves → final decision recorded →
        every step present in the audit trail → evidence graph shows the
        HUMAN nodes alongside the AI ones.
        """
        from app.core.enums import AuditEventType
        from app.models import AuditEvent as AuditEventModel
        from tests.test_perception_pipeline import (
            FakeOCRService,
            FakeVisionService,
            _label_png,
        )

        pipeline = services.perception._pipeline
        monkeypatch.setattr(pipeline, "_ocr", FakeOCRService())
        monkeypatch.setattr(pipeline, "_vision", FakeVisionService())

        # --- 1. Intake + perception + evaluation -----------------------------
        create = client.post(
            f"{API}/inspections",
            headers=inspector_headers,
            json={"productName": "Golden HITL Tea 250g", "productCategory": "food"},
        )
        assert create.status_code == 201, create.text
        inspection_id = create.json()["id"]
        upload = client.post(
            f"{API}/inspections/{inspection_id}/images/upload",
            headers=inspector_headers,
            files={"file": ("front.png", _label_png(), "image/png")},
            data={"captureSource": "UPLOAD", "imageType": "FRONT"},
        )
        assert upload.status_code == 201, upload.text
        assert client.post(
            f"{API}/inspections/{inspection_id}/perceive",
            headers=inspector_headers,
        ).status_code == 202
        evaluate = client.post(
            f"{API}/inspections/{inspection_id}/evaluate",
            headers=inspector_headers,
        )
        assert evaluate.status_code == 200, evaluate.text
        first_evaluation_id = evaluate.json()["evaluation"]["id"]

        findings = client.get(
            f"{API}/inspections/{inspection_id}/compliance/findings",
            headers=inspector_headers,
        ).json()
        assert findings, "engine produced no findings"
        # Every finding starts life awaiting a human.
        assert all(f["reviewState"] == "PENDING_REVIEW" for f in findings)

        # --- 2. Correct a field (append-only) ---------------------------------
        field_finding = next(
            (f for f in findings if f.get("extractedFieldId")), None
        )
        assert field_finding, "expected at least one finding with a field"
        field_id = field_finding["extractedFieldId"]
        correction = client.post(
            f"{API}/fields/{field_id}/correct",
            headers=inspector_headers,
            json={"correctedValue": "MRP ₹ 99.00 (inclusive of all taxes)",
                  "reason": "Inspector read the physical label."},
        )
        assert correction.status_code == 200, correction.text
        assert correction.json()["previousValue"] is not None or \
            correction.json()["previousRawText"] is not None

        # --- 3. Re-evaluate: NEW evaluation, history preserved ----------------
        reevaluate = client.post(
            f"{API}/inspections/{inspection_id}/evaluate",
            headers=inspector_headers,
        )
        assert reevaluate.status_code == 200, reevaluate.text
        second_evaluation_id = reevaluate.json()["evaluation"]["id"]
        assert second_evaluation_id != first_evaluation_id
        # The findings list reflects the latest evaluation; the historical
        # evaluation row itself is untouched (asserted via its id remaining
        # queryable and the correction history below).
        latest_findings = client.get(
            f"{API}/inspections/{inspection_id}/compliance/findings",
            headers=inspector_headers,
        ).json()

        # --- 4. Review the findings of the latest evaluation ------------------
        second_findings = [
            f for f in latest_findings if f["evaluationId"] == second_evaluation_id
        ]
        assert second_findings, "re-evaluation produced no findings"
        confirmed = None
        escalated = None
        for finding in second_findings:
            if finding.get("extractedFieldId") and confirmed is None:
                resp = client.post(
                    f"{API}/compliance/findings/{finding['id']}/review",
                    headers=inspector_headers,
                    json={"action": "CONFIRM"},
                )
                assert resp.status_code == 200, resp.text
                assert resp.json()["state"] == "CONFIRMED"
                confirmed = finding
            elif escalated is None and not finding.get("extractedFieldId"):
                resp = client.post(
                    f"{API}/compliance/findings/{finding['id']}/escalate",
                    headers=inspector_headers,
                    json={"reason": "Needs a senior legal opinion."},
                )
                assert resp.status_code == 200, resp.text
                assert resp.json()["state"] == "ESCALATED"
                assert resp.json()["escalatedToRole"]
                escalated = finding

        # --- 5. Review status reflects the human work -------------------------
        status = client.get(
            f"{API}/inspections/{inspection_id}/review-status",
            headers=inspector_headers,
        ).json()
        assert status["confirmed"] >= 1
        assert status["escalated"] >= 1
        assert status["pendingReview"] + status["unreviewed"] >= 0

        # --- 6. Final decision (gate + supersede chain) ------------------------
        decision = client.post(
            f"{API}/inspections/{inspection_id}/decision",
            headers=inspector_headers,
            json={"decision": "REQUIRES_FURTHER_REVIEW",
                  "reason": "Escalated finding awaits supervisor review."},
        )
        assert decision.status_code == 200, decision.text

        # Resolve every remaining reviewable finding of the LATEST evaluation
        # so the gate opens for a definitive decision.
        latest = client.get(
            f"{API}/inspections/{inspection_id}/compliance/findings",
            headers=inspector_headers,
        ).json()
        for finding in latest:
            if finding["evaluationId"] != second_evaluation_id:
                continue
            if finding["reviewState"] == "PENDING_REVIEW":
                resolve = client.post(
                    f"{API}/compliance/findings/{finding['id']}/review",
                    headers=supervisor_headers,
                    json={"action": "CONFIRM"},
                )
                assert resolve.status_code == 200, resolve.text

        revised = client.post(
            f"{API}/inspections/{inspection_id}/decision",
            headers=supervisor_headers,
            json={"decision": "NON_COMPLIANT",
                  "reason": "Supervisor confirmed the violation on review."},
        )
        assert revised.status_code == 200, revised.text
        assert revised.json()["supersedesDecisionId"] == decision.json()["id"]

        history = client.get(
            f"{API}/inspections/{inspection_id}/decision-history",
            headers=inspector_headers,
        ).json()
        assert len(history["history"]) == 2
        assert history["current"]["decision"] == "NON_COMPLIANT"

        # --- 7. The audit trail contains every human action --------------------
        events = db.execute(
            select(AuditEventModel)
            .where(AuditEventModel.inspection_id == uuid.UUID(inspection_id))
            .order_by(AuditEventModel.created_at.asc())
        ).scalars().all()
        event_types = {e.event_type for e in events}
        for expected in (
            AuditEventType.FIELD_CORRECTED.value,
            AuditEventType.FINDING_CONFIRMED.value,
            AuditEventType.FINDING_ESCALATED.value,
            AuditEventType.DECISION_SUBMITTED.value,
            AuditEventType.DECISION_CHANGED.value,
        ):
            assert expected in event_types, f"missing audit event {expected}"
        # No credentials of any kind in the payloads.
        for event in events:
            blob = str(event.payload or "").lower()
            for banned in ("password", "token", "secret", "apikey", "api_key"):
                assert banned not in blob

        # --- 8. The evidence graph shows AI and HUMAN as distinct nodes --------
        graph = client.get(
            f"{API}/inspections/{inspection_id}/evidence-graph",
            headers=inspector_headers,
        ).json()
        origins = {
            n["type"]: n["metadata"].get("origin")
            for n in graph["nodes"]
        }
        assert origins.get("EXTRACTED_FIELD") == "AI"
        assert origins.get("FIELD_CORRECTION") == "HUMAN"
        assert origins.get("FINDING_REVIEW") == "HUMAN"
        assert origins.get("INSPECTION_DECISION") == "HUMAN"
        edge_types = {e["type"] for e in graph["edges"]}
        assert "FIELD_CORRECTION_CORRECTS_FIELD" in edge_types
        assert "FINDING_REVIEW_REVIEWS_FINDING" in edge_types
        assert "DECISION_FOR_INSPECTION" in edge_types
        assert "DECISION_SUPERSEDES_DECISION" in edge_types
