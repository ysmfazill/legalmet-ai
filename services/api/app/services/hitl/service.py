"""Human-in-the-loop service (Prompt 8).

THE CONTRACT: AI ASSISTS. THE INSPECTOR DECIDES.

Everything in this service is performed by an authenticated human whose role
has been checked at the router. The deterministic engine never calls into this
module and this module never calls the engine's writers — the only bridge is
``re-evaluation``, which creates a NEW ComplianceEvaluation (the historical
evaluation is never mutated).

State machine (Phase 20), enforced HERE — never in the frontend:

    PENDING_REVIEW ──confirm──▶ CONFIRMED
    PENDING_REVIEW ──correct──▶ CORRECTED      (via field correction)
    PENDING_REVIEW ──reject───▶ REJECTED       (reason mandatory)
    PENDING_REVIEW ──escalate─▶ ESCALATED      (reason mandatory)
    CONFIRMED ──────override──▶ OVERRIDDEN     (SUPERVISOR/ADMIN only, reason mandatory)
    CORRECTED ──────override──▶ OVERRIDDEN     (SUPERVISOR/ADMIN only, reason mandatory)
    ESCALATED ──confirm/reject/override──▶ CONFIRMED / REJECTED / OVERRIDDEN

Any other transition raises ConflictError (409). REJECTED and OVERRIDDEN are
terminal.

Decision gate (Phase 13): a final decision is blocked while CRITICAL-severity
findings remain unresolved (PENDING_REVIEW / ESCALATED), unless the decision
is REQUIRES_FURTHER_REVIEW (which IS the escalation of the whole inspection).

Decision immutability (Phase 14): a new decision never overwrites an old one —
it supersedes it (``supersedes_decision_id``), and the previous decision is
preserved verbatim in the history chain.

Idempotency (Phase 21): repeating the same review action on a finding already
in the target state is a no-op that returns the current state — it never
creates duplicate events or corrections. Submitting an IDENTICAL decision
(first decision, same actor, same decision type and reason) returns the
existing row.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.enums import (
    AuditEventType,
    FindingReviewState,
    FindingSeverity,
    InspectionDecisionType,
    UserRole,
)
from app.core.errors import ConflictError, ForbiddenError, NotFoundError
from app.db.base import utcnow
from app.models import (
    EvaluationFinding,
    ExtractedField,
    FieldCorrection,
    FindingReview,
    FindingReviewEvent,
    Inspection,
    InspectionDecision,
    User,
)
from app.services.audit.service import AuditService

# --- state machine tables (Phase 20) -------------------------------------------

# action -> {allowed source states -> target state}
# Self-mappings (e.g. CONFIRMED → CONFIRMED) make a repeated action an
# idempotent no-op rather than a conflict (Phase 21).
_REVIEW_TRANSITIONS: dict[str, dict[FindingReviewState, FindingReviewState]] = {
    "CONFIRM": {
        FindingReviewState.PENDING_REVIEW: FindingReviewState.CONFIRMED,
        FindingReviewState.ESCALATED: FindingReviewState.CONFIRMED,
        # Re-confirm after a correction recorded through the field API:
        FindingReviewState.CORRECTED: FindingReviewState.CONFIRMED,
        FindingReviewState.CONFIRMED: FindingReviewState.CONFIRMED,
    },
    "CORRECT": {
        FindingReviewState.PENDING_REVIEW: FindingReviewState.CORRECTED,
        FindingReviewState.ESCALATED: FindingReviewState.CORRECTED,
        FindingReviewState.CORRECTED: FindingReviewState.CORRECTED,
    },
    "REJECT": {
        FindingReviewState.PENDING_REVIEW: FindingReviewState.REJECTED,
        FindingReviewState.ESCALATED: FindingReviewState.REJECTED,
        FindingReviewState.REJECTED: FindingReviewState.REJECTED,
    },
    "OVERRIDE": {
        FindingReviewState.CONFIRMED: FindingReviewState.OVERRIDDEN,
        FindingReviewState.CORRECTED: FindingReviewState.OVERRIDDEN,
        FindingReviewState.REJECTED: FindingReviewState.OVERRIDDEN,
        FindingReviewState.ESCALATED: FindingReviewState.OVERRIDDEN,
        FindingReviewState.OVERRIDDEN: FindingReviewState.OVERRIDDEN,
    },
    "ESCALATE": {
        FindingReviewState.PENDING_REVIEW: FindingReviewState.ESCALATED,
        FindingReviewState.CONFIRMED: FindingReviewState.ESCALATED,
        FindingReviewState.CORRECTED: FindingReviewState.ESCALATED,
        FindingReviewState.ESCALATED: FindingReviewState.ESCALATED,
    },
}

# Terminal states — no transitions out except the idempotent self-mapping
# and the supervisor OVERRIDE of a REJECTED finding (listed explicitly above).
_TERMINAL_STATES = frozenset(
    {FindingReviewState.REJECTED, FindingReviewState.OVERRIDDEN}
)

# Actions that demand a reason (Phase 6). CONFIRM may be done without a reason
# (agreeing with the system needs no justification); every *disagreeing* or
# *transferring* action does.
_REASON_REQUIRED_ACTIONS = frozenset({"REJECT", "OVERRIDE", "ESCALATE"})

# Roles that may act on finding reviews (Phase 7).
_REVIEW_WRITE_ROLES = frozenset(
    {UserRole.INSPECTOR.value, UserRole.SUPERVISOR.value, UserRole.ADMIN.value}
)
# Only senior roles may override a confirmed outcome.
_OVERRIDE_ROLES = frozenset({UserRole.SUPERVISOR.value, UserRole.ADMIN.value})
# Roles that may record the final decision.
_DECISION_ROLES = frozenset(
    {UserRole.INSPECTOR.value, UserRole.SUPERVISOR.value, UserRole.ADMIN.value}
)

# Severity that blocks a final decision while unresolved (Phase 13).
_BLOCKING_SEVERITIES = frozenset(
    {FindingSeverity.CRITICAL.value, FindingSeverity.MAJOR.value}
)
_UNRESOLVED_STATES = frozenset(
    {FindingReviewState.PENDING_REVIEW.value, FindingReviewState.ESCALATED.value}
)

DECISION_BOUNDARY_NOTE = (
    "METRASIGHT provides AI-assisted inspection analysis and traceability. "
    "The authorized inspector remains responsible for the final inspection "
    "decision."
)


@dataclass(frozen=True)
class ReviewActionResult:
    """Result of one review action (review + optional correction)."""

    review: FindingReview
    correction: FieldCorrection | None


class HitlService:
    """All human-in-the-loop writes: corrections, reviews, decisions."""

    def __init__(self, audit: AuditService) -> None:
        self._audit = audit

    # ------------------------------------------------------------------ fields

    def correct_field(
        self,
        db: Session,
        *,
        field_id: uuid.UUID,
        actor: User,
        corrected_value: str,
        reason: str,
        triggered_by_evaluation_id: uuid.UUID | None = None,
        finding_id: uuid.UUID | None = None,
    ) -> FieldCorrection:
        """Record one inspector correction of an extracted field (Phase 1).

        The ORIGINAL AI output is NEVER overwritten: raw_text,
        normalized_value, confidence and status stay exactly as the pipeline
        wrote them. The correction is a new append-only history row; the
        field's corrected_* columns are maintained as a pointer to the LATEST
        correction (that is what re-evaluation consumes).
        """
        if actor.role not in _REVIEW_WRITE_ROLES:
            raise ForbiddenError(
                "Only an inspector, supervisor or admin may correct a field."
            )
        if not reason or not reason.strip():
            from app.core.errors import ValidationError

            raise ValidationError("A correction reason is mandatory.")

        field = db.get(ExtractedField, field_id)
        if field is None:
            raise NotFoundError(f"Extracted field not found: {field_id}")

        correction = self._record_correction(
            db,
            field=field,
            actor=actor,
            corrected_value=corrected_value,
            reason=reason,
            triggered_by_evaluation_id=triggered_by_evaluation_id,
            finding_id=finding_id,
        )
        db.commit()
        return correction

    def _record_correction(
        self,
        db: Session,
        *,
        field: ExtractedField,
        actor: User,
        corrected_value: str,
        reason: str,
        triggered_by_evaluation_id: uuid.UUID | None = None,
        finding_id: uuid.UUID | None = None,
    ) -> FieldCorrection:
        """Append one correction row + update the latest-pointer. NO commit —
        the caller owns the transaction (so a correction that is part of a
        finding review commits atomically with the review transition)."""
        inspection_id = self._inspection_of_field(db, field)

        correction = FieldCorrection(
            extracted_field_id=field.id,
            inspection_id=inspection_id,
            corrected_by=actor.id,
            corrected_at=utcnow(),
            previous_value=field.normalized_value,
            previous_raw_text=field.raw_text,
            corrected_value=corrected_value,
            reason=reason.strip(),
            triggered_by_evaluation_id=triggered_by_evaluation_id,
        )
        db.add(correction)
        db.flush()

        # Latest-correction pointer ONLY — the AI values above are untouched.
        field.corrected_value = corrected_value
        field.corrected_at = correction.corrected_at
        field.corrected_by = actor.id
        field.corrected_reason = correction.reason
        db.flush()

        self._audit.record(
            db,
            event_type=AuditEventType.FIELD_CORRECTED,
            entity_type="extracted_field",
            entity_id=field.id,
            actor_id=actor.id,
            inspection_id=inspection_id,
            payload={
                "correctionId": str(correction.id),
                "previousValue": correction.previous_value,
                "previousRawText": correction.previous_raw_text,
                "correctedValue": corrected_value,
                "reason": correction.reason,
                "actorRole": actor.role,
                **({"findingId": str(finding_id)} if finding_id else {}),
            },
        )
        return correction

    def field_corrections(
        self, db: Session, field_id: uuid.UUID
    ) -> list[FieldCorrection]:
        """Full append-only correction history of one field (oldest first)."""
        field = db.get(ExtractedField, field_id)
        if field is None:
            raise NotFoundError(f"Extracted field not found: {field_id}")
        return list(
            db.execute(
                select(FieldCorrection)
                .where(FieldCorrection.extracted_field_id == field_id)
                .order_by(FieldCorrection.created_at.asc())
            ).scalars()
        )

    def field_review(self, db: Session, field_id: uuid.UUID) -> dict:
        """Read model: original AI output vs latest human correction."""
        field = db.get(ExtractedField, field_id)
        if field is None:
            raise NotFoundError(f"Extracted field not found: {field_id}")
        count = (
            db.execute(
                select(func.count())
                .select_from(FieldCorrection)
                .where(FieldCorrection.extracted_field_id == field_id)
            ).scalar()
            or 0
        )
        corrected_by_name = None
        if field.corrected_by is not None:
            user = db.get(User, field.corrected_by)
            corrected_by_name = getattr(user, "full_name", None) if user else None
        return {
            "field_id": field.id,
            "inspection_id": self._inspection_of_field(db, field),
            "original_value": field.normalized_value,
            "original_raw_text": field.raw_text,
            "ai_confidence": field.confidence,
            "ai_extraction_status": field.status,
            "corrected_value": field.corrected_value,
            "corrected_at": field.corrected_at,
            "corrected_by": field.corrected_by,
            "corrected_by_name": corrected_by_name,
            "correction_reason": field.corrected_reason,
            "correction_count": count,
        }

    # --------------------------------------------------------------- findings

    def review_finding(
        self,
        db: Session,
        *,
        finding_id: uuid.UUID,
        actor: User,
        action: str,
        reason: str | None = None,
        note: str | None = None,
        corrected_value: str | None = None,
    ) -> ReviewActionResult:
        """Apply one review action to an engine finding (Phases 4/6/20/21).

        Actions: CONFIRM / CORRECT / REJECT / OVERRIDE / ESCALATE. The state
        machine above is the ONLY path from one state to another — anything
        else raises ConflictError. Repeating an action that would be a no-op
        (the finding is already in the target state, same actor) returns the
        current state without creating duplicates.
        """
        if actor.role not in _REVIEW_WRITE_ROLES:
            raise ForbiddenError(
                "Only an inspector, supervisor or admin may review a finding."
            )
        normalized_action = action.strip().upper()
        if normalized_action not in _REVIEW_TRANSITIONS:
            raise NotFoundError(
                f"Unknown review action '{action}'. Use one of: "
                "CONFIRM, CORRECT, REJECT, OVERRIDE, ESCALATE."
            )
        if normalized_action in _REASON_REQUIRED_ACTIONS and not (
            reason and reason.strip()
        ):
            from app.core.errors import ValidationError

            raise ValidationError(
                f"A reason is mandatory for {normalized_action} — an "
                "unexplained override is never accepted."
            )
        if normalized_action == "OVERRIDE" and actor.role not in _OVERRIDE_ROLES:
            raise ForbiddenError(
                "Only a supervisor or admin may override a confirmed outcome."
            )

        finding = db.get(EvaluationFinding, finding_id)
        if finding is None:
            raise NotFoundError(f"Finding not found: {finding_id}")

        review = self._ensure_review(db, finding)
        current = FindingReviewState(review.state)
        transitions = _REVIEW_TRANSITIONS[normalized_action]
        target = transitions.get(current)

        # --- idempotency (Phase 21): same action on same state = no-op -------
        if target is None:
            if current in _TERMINAL_STATES:
                raise ConflictError(
                    f"Finding review is in terminal state {current.value} — "
                    "no further transitions are allowed."
                )
            # e.g. ESCALATE on an already-ESCALATED review: idempotent no-op.
            if (
                normalized_action == "ESCALATE"
                and current == FindingReviewState.ESCALATED
            ):
                return ReviewActionResult(review=review, correction=None)
            raise ConflictError(
                f"Cannot {normalized_action} a finding in state "
                f"{current.value}."
            )
        if current == target:
            return ReviewActionResult(review=review, correction=None)

        # --- CORRECT needs a value (goes through the correction workflow) ----
        correction: FieldCorrection | None = None
        if normalized_action == "CORRECT":
            if not corrected_value or not str(corrected_value).strip():
                from app.core.errors import ValidationError

                raise ValidationError(
                    "A corrected value is required for the CORRECT action "
                    "(or use POST /fields/{field_id}/correct)."
                )
            if finding.extracted_field_id is None:
                raise ConflictError(
                    "This finding has no extracted field to correct (its "
                    "evidence is an absence, not a value)."
                )
            if not (reason and reason.strip()):
                from app.core.errors import ValidationError

                raise ValidationError(
                    "A correction reason is mandatory — an unexplained "
                    "correction is never accepted."
                )
            field = db.get(ExtractedField, finding.extracted_field_id)
            if field is None:
                raise ConflictError(
                    "The finding's extracted field no longer exists."
                )
            correction = self._record_correction(
                db,
                field=field,
                actor=actor,
                corrected_value=str(corrected_value).strip(),
                reason=reason,
                triggered_by_evaluation_id=finding.evaluation_id,
                finding_id=finding.id,
            )
            review.correction_id = correction.id

        previous = FindingReviewState(review.state)
        review.state = target.value
        review.reviewed_by = actor.id
        review.reviewed_at = utcnow()
        review.reason = (reason or note or "").strip() or None
        if normalized_action == "ESCALATE":
            review.escalated_to_role = UserRole.SUPERVISOR.value
        db.flush()

        event = FindingReviewEvent(
            review_id=review.id,
            actor_id=actor.id,
            actor_role=actor.role,
            action=normalized_action,
            previous_state=previous.value,
            new_state=target.value,
            reason=review.reason,
            payload={
                "findingId": str(finding.id),
                "findingStatus": finding.status,
                "note": note,
                **(
                    {"correctionId": str(correction.id)}
                    if correction is not None
                    else {}
                ),
            },
        )
        db.add(event)
        db.flush()

        # --- audit (Phase 16) --------------------------------------------------
        # CORRECT already audited itself via FIELD_CORRECTED above.
        event_type = {
            "CONFIRM": AuditEventType.FINDING_CONFIRMED,
            "REJECT": AuditEventType.FINDING_REJECTED,
            "OVERRIDE": AuditEventType.FINDING_OVERRIDDEN,
            "ESCALATE": AuditEventType.FINDING_ESCALATED,
        }.get(normalized_action)
        if event_type is not None:
            self._audit.record(
                db,
                event_type=event_type,
                entity_type="evaluation_finding",
                entity_id=finding.id,
                actor_id=actor.id,
                inspection_id=review.inspection_id,
                payload={
                    "reviewId": str(review.id),
                    "actorRole": actor.role,
                    "previousState": previous.value,
                    "newState": target.value,
                    "reason": review.reason,
                    "findingStatus": finding.status,
                    **(
                        {"correctionId": str(correction.id)}
                        if correction is not None
                        else {}
                    ),
                },
            )
        # A supervisor override is ALSO a supervisor review event.
        if normalized_action == "OVERRIDE":
            self._audit.record(
                db,
                event_type=AuditEventType.SUPERVISOR_REVIEWED,
                entity_type="evaluation_finding",
                entity_id=finding.id,
                actor_id=actor.id,
                inspection_id=review.inspection_id,
                payload={
                    "reviewId": str(review.id),
                    "actorRole": actor.role,
                    "action": "OVERRIDE",
                    "reason": review.reason,
                },
            )
        db.commit()
        return ReviewActionResult(review=review, correction=correction)

    def get_review(self, db: Session, finding_id: uuid.UUID) -> FindingReview:
        """The review of one finding (creates nothing — read only).

        A finding with no review row yet is NOT an error: its implicit state
        is PENDING_REVIEW, so a synthetic overlay is returned. This keeps the
        read honest (the finding exists, the human simply has not acted) and
        lets the AUDITOR role read the state of unreviewed findings.
        """
        finding = db.get(EvaluationFinding, finding_id)
        if finding is None:
            raise NotFoundError(f"Finding not found: {finding_id}")
        review = (
            db.execute(
                select(FindingReview)
                .where(FindingReview.finding_id == finding_id)
                .options(selectinload(FindingReview.events))
            )
            .scalars()
            .first()
        )
        if review is None:
            return FindingReview(
                finding_id=finding.id,
                inspection_id=finding.evaluation.inspection_id,
                state=FindingReviewState.PENDING_REVIEW,
                events=[],
            )
        return review

    def reviews_for_inspection(
        self, db: Session, inspection_id: uuid.UUID
    ) -> list[FindingReview]:
        return list(
            db.execute(
                select(FindingReview)
                .where(FindingReview.inspection_id == inspection_id)
                .options(selectinload(FindingReview.events))
                .order_by(FindingReview.created_at.asc())
            ).scalars()
        )

    # -------------------------------------------------------------- decisions

    def submit_decision(
        self,
        db: Session,
        *,
        inspection_id: uuid.UUID,
        actor: User,
        decision: InspectionDecisionType,
        reason: str | None = None,
        note: str | None = None,
        evaluation_id: uuid.UUID | None = None,
    ) -> InspectionDecision:
        """Record the FINAL human decision (Phases 5/13/14/21).

        The engine NEVER calls this — only an authenticated human whose role
        is in _DECISION_ROLES. Gate: unresolved CRITICAL/MAJOR findings block
        COMPLIANT / NON_COMPLIANT decisions (the inspector must first resolve
        them or record REQUIRES_FURTHER_REVIEW).
        """
        if actor.role not in _DECISION_ROLES:
            raise ForbiddenError(
                "Only an inspector, supervisor or admin may record the final "
                "decision. The system never decides."
            )
        if decision in (
            InspectionDecisionType.NON_COMPLIANT,
            InspectionDecisionType.REQUIRES_FURTHER_REVIEW,
        ) and not (reason and reason.strip()):
            from app.core.errors import ValidationError

            raise ValidationError(
                f"A reason is mandatory for a {decision.value} decision."
            )
        inspection = db.get(Inspection, inspection_id)
        if inspection is None:
            raise NotFoundError(f"Inspection not found: {inspection_id}")

        previous = self.latest_decision(db, inspection_id)

        # Phase 14: changing an existing decision demands an explanation.
        if (
            previous is not None
            and previous.decision != decision.value
            and not (reason and reason.strip())
        ):
            from app.core.errors import ValidationError

            raise ValidationError(
                "A reason is mandatory when changing an existing decision."
            )

        # --- decision gate (Phase 13) ------------------------------------------
        blockers: list[str] = []
        if decision in (
            InspectionDecisionType.COMPLIANT,
            InspectionDecisionType.NON_COMPLIANT,
        ):
            blockers = self._decision_blockers(db, inspection_id)
            if blockers:
                raise ConflictError(
                    "Critical findings remain unresolved — resolve them (or "
                    "record REQUIRES_FURTHER_REVIEW) before recording a final "
                    "decision. Blockers: " + "; ".join(blockers)
                )

        # --- idempotency (Phase 21): identical resubmission is a no-op --------
        if (
            previous is not None
            and previous.decided_by == actor.id
            and previous.decision == decision.value
            and (previous.reason or None) == (reason.strip() if reason else None)
        ):
            return previous

        # --- immutability (Phase 14): supersede, never overwrite ---------------
        resolved_evaluation_id = evaluation_id
        if resolved_evaluation_id is not None:
            from app.models import ComplianceEvaluation

            linked = db.get(ComplianceEvaluation, resolved_evaluation_id)
            if linked is None or linked.inspection_id != inspection_id:
                from app.core.errors import ValidationError

                raise ValidationError(
                    "evaluationId does not reference an evaluation of this "
                    "inspection."
                )
        else:
            from app.models import ComplianceEvaluation

            latest_eval = (
                db.execute(
                    select(ComplianceEvaluation)
                    .where(ComplianceEvaluation.inspection_id == inspection_id)
                    .order_by(ComplianceEvaluation.created_at.desc())
                    .limit(1)
                )
                .scalars()
                .first()
            )
            resolved_evaluation_id = latest_eval.id if latest_eval else None

        counts = self._review_counts(db, inspection_id)
        row = InspectionDecision(
            inspection_id=inspection_id,
            decision=decision.value,
            decided_by=actor.id,
            decided_at=utcnow(),
            reason=reason.strip() if reason else None,
            evaluation_id=resolved_evaluation_id,
            supersedes_decision_id=previous.id if previous else None,
            payload={
                "note": note,
                "reviewCounts": counts,
                "supersededDecision": (
                    {
                        "id": str(previous.id),
                        "decision": previous.decision,
                        "decidedBy": str(previous.decided_by),
                        "decidedAt": previous.decided_at.isoformat(),
                        "reason": previous.reason,
                    }
                    if previous
                    else None
                ),
            },
        )
        db.add(row)
        db.flush()

        event_type = (
            AuditEventType.DECISION_CHANGED
            if previous is not None
            else AuditEventType.DECISION_SUBMITTED
        )
        self._audit.record(
            db,
            event_type=event_type,
            entity_type="inspection",
            entity_id=inspection_id,
            actor_id=actor.id,
            inspection_id=inspection_id,
            payload={
                "decisionId": str(row.id),
                "actorRole": actor.role,
                "decision": decision.value,
                "reason": row.reason,
                **(
                    {"previousDecision": previous.decision,
                     "previousDecisionId": str(previous.id)}
                    if previous
                    else {}
                ),
            },
        )
        db.commit()
        return row

    def latest_decision(
        self, db: Session, inspection_id: uuid.UUID
    ) -> InspectionDecision | None:
        return (
            db.execute(
                select(InspectionDecision)
                .where(InspectionDecision.inspection_id == inspection_id)
                .order_by(InspectionDecision.created_at.desc())
                .limit(1)
            )
            .scalars()
            .first()
        )

    def decision_history(
        self, db: Session, inspection_id: uuid.UUID
    ) -> list[InspectionDecision]:
        """Full decision chain (oldest first) — nothing is ever deleted."""
        inspection = db.get(Inspection, inspection_id)
        if inspection is None:
            raise NotFoundError(f"Inspection not found: {inspection_id}")
        return list(
            db.execute(
                select(InspectionDecision)
                .where(InspectionDecision.inspection_id == inspection_id)
                .order_by(InspectionDecision.created_at.asc())
            ).scalars()
        )

    def review_status(self, db: Session, inspection_id: uuid.UUID) -> dict:
        """GET /inspections/{id}/review-status (Phase 18)."""
        inspection = db.get(Inspection, inspection_id)
        if inspection is None:
            raise NotFoundError(f"Inspection not found: {inspection_id}")

        from app.models import ComplianceEvaluation

        latest_eval = (
            db.execute(
                select(ComplianceEvaluation)
                .where(ComplianceEvaluation.inspection_id == inspection_id)
                .order_by(ComplianceEvaluation.created_at.desc())
                .limit(1)
            )
            .scalars()
            .first()
        )
        findings: list[EvaluationFinding] = (
            list(latest_eval.findings) if latest_eval else []
        )
        counts = self._review_counts(db, inspection_id, findings=findings)
        blockers = self._decision_blockers(
            db, inspection_id, findings=findings
        )
        decision = self.latest_decision(db, inspection_id)
        return {
            "inspection_id": inspection_id,
            "total_findings": len(findings),
            "pending_review": counts["pending_review"],
            "confirmed": counts["confirmed"],
            "corrected": counts["corrected"],
            "rejected": counts["rejected"],
            "overridden": counts["overridden"],
            "escalated": counts["escalated"],
            "unreviewed": counts["unreviewed"],
            "critical_unresolved": len(blockers),
            "decision": decision,
            "decision_allowed": not blockers,
            "decision_blockers": blockers,
        }

    # --------------------------------------------------------------- internals

    def _ensure_review(self, db: Session, finding: EvaluationFinding) -> FindingReview:
        if finding.review is not None:
            return finding.review
        review = FindingReview(
            finding_id=finding.id,
            inspection_id=finding.evaluation.inspection_id,
            state=FindingReviewState.PENDING_REVIEW.value,
        )
        db.add(review)
        db.flush()
        # Reload relationship for the caller.
        finding.review = review
        return review

    def _review_counts(
        self,
        db: Session,
        inspection_id: uuid.UUID,
        *,
        findings: list[EvaluationFinding] | None = None,
    ) -> dict[str, int]:
        if findings is None:
            from app.models import ComplianceEvaluation

            latest_eval = (
                db.execute(
                    select(ComplianceEvaluation)
                    .where(ComplianceEvaluation.inspection_id == inspection_id)
                    .order_by(ComplianceEvaluation.created_at.desc())
                    .limit(1)
                )
                .scalars()
                .first()
            )
            findings = list(latest_eval.findings) if latest_eval else []
        counts = {
            "pending_review": 0,
            "confirmed": 0,
            "corrected": 0,
            "rejected": 0,
            "overridden": 0,
            "escalated": 0,
            "unreviewed": 0,
        }
        for finding in findings:
            state = finding.review_state
            if state == FindingReviewState.PENDING_REVIEW.value:
                if finding.review is None:
                    counts["unreviewed"] += 1
                else:
                    counts["pending_review"] += 1
            else:
                counts[state.lower()] = counts.get(state.lower(), 0) + 1
        return counts

    def _decision_blockers(
        self,
        db: Session,
        inspection_id: uuid.UUID,
        *,
        findings: list[EvaluationFinding] | None = None,
    ) -> list[str]:
        """Findings that block a final decision (Phase 13).

        A CRITICAL/MAJOR finding blocks while its review is unresolved
        (PENDING_REVIEW or ESCALATED). Resolving means the inspector CONFIRMS,
        CORRECTS or REJECTS it — a human verdict exists either way.
        """
        if findings is None:
            from app.models import ComplianceEvaluation

            latest_eval = (
                db.execute(
                    select(ComplianceEvaluation)
                    .where(ComplianceEvaluation.inspection_id == inspection_id)
                    .order_by(ComplianceEvaluation.created_at.desc())
                    .limit(1)
                )
                .scalars()
                .first()
            )
            findings = list(latest_eval.findings) if latest_eval else []
        blockers: list[str] = []
        for finding in findings:
            if finding.severity not in _BLOCKING_SEVERITIES:
                continue
            state = finding.review_state
            if state in _UNRESOLVED_STATES:
                blockers.append(
                    f"Finding {finding.id} ({finding.severity}, status "
                    f"{finding.status}) is {state}"
                )
        return blockers

    @staticmethod
    def _inspection_of_field(db: Session, field: ExtractedField) -> uuid.UUID:
        from app.models import Package

        package = db.get(Package, field.package_id)
        if package is None or package.inspection_id is None:
            raise NotFoundError(
                f"The field's package has no inspection (field {field.id})."
            )
        return package.inspection_id
