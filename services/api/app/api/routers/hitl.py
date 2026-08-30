"""Human-in-the-loop review routes (Prompt 8).

Thin by design: authenticate → enforce role → delegate to HitlService →
serialise. The state machine, decision gate and immutability guarantees live
in the service layer — never in a router, never in the frontend.

Endpoints (Phase 18):

    POST /fields/{field_id}/correct             inspector corrects a value
    GET  /fields/{field_id}/corrections         correction history (append-only)
    GET  /fields/{field_id}/review              original AI value vs correction

    POST /compliance/findings/{finding_id}/review        one action:
        {action: CONFIRM|REJECT|OVERRIDE|ESCALATE|CORRECT, reason?, correctedValue?}
    GET  /compliance/findings/{finding_id}/review        review + event history

    POST /inspections/{inspection_id}/decision          final human decision
    GET  /inspections/{inspection_id}/decision          current decision
    GET  /inspections/{inspection_id}/decision-history  full decision chain
    GET  /inspections/{inspection_id}/review-status     review progress + gate

Authorization (Phase 7): INSPECTOR/SUPERVISOR/ADMIN write; AUDITOR read-only.
Overrides additionally require SUPERVISOR/ADMIN (enforced in the service).
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_services_dep, require_role
from app.core.enums import UserRole
from app.db.session import get_db
from app.models import User
from app.schemas.hitl import (
    DecisionHistoryOut,
    DecisionRequest,
    FieldCorrectionOut,
    FieldCorrectRequest,
    FieldReviewOut,
    FindingReviewActionRequest,
    FindingReviewOut,
    FindingReviewVerbRequest,
    InspectionDecisionOut,
    ReviewStatusOut,
)
from app.services.registry import Services

router = APIRouter(tags=["human-review"])

# Who may write human review data. AUDITOR is deliberately absent — the audit
# role is read-only and can never modify findings, corrections or decisions.
_REVIEW_WRITE_ROLES = (UserRole.INSPECTOR, UserRole.SUPERVISOR, UserRole.ADMIN)


def _decision_out(decision, db: Session) -> InspectionDecisionOut:
    out = InspectionDecisionOut.model_validate(decision)
    if decision.decided_by is not None:
        user = db.get(User, decision.decided_by)
        out.decided_by_name = getattr(user, "full_name", None) if user else None
    return out


# --------------------------------------------------------------------- fields


@router.post("/fields/{field_id}/correct", response_model=FieldCorrectionOut)
def correct_field(
    field_id: UUID,
    body: FieldCorrectRequest,
    user: User = Depends(require_role(*_REVIEW_WRITE_ROLES)),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> FieldCorrectionOut:
    """Record one inspector correction of an extracted field.

    The original OCR/AI output is NEVER overwritten — the correction is an
    append-only history row; re-evaluation consumes the corrected value in a
    NEW evaluation (the historical evaluation is preserved untouched).
    """
    correction = services.hitl.correct_field(
        db,
        field_id=field_id,
        actor=user,
        corrected_value=body.corrected_value,
        reason=body.reason,
        triggered_by_evaluation_id=body.triggered_by_evaluation_id,
    )
    out = FieldCorrectionOut.model_validate(correction)
    if correction.corrected_by is not None:
        actor = db.get(User, correction.corrected_by)
        out.corrected_by_name = getattr(actor, "full_name", None) if actor else None
    return out


@router.get("/fields/{field_id}/corrections", response_model=list[FieldCorrectionOut])
def list_field_corrections(
    field_id: UUID,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> list[FieldCorrectionOut]:
    """Full append-only correction history of one field (oldest first)."""
    rows = services.hitl.field_corrections(db, field_id)
    return [FieldCorrectionOut.model_validate(row) for row in rows]


@router.get("/fields/{field_id}/review", response_model=FieldReviewOut)
def get_field_review(
    field_id: UUID,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> FieldReviewOut:
    """Original AI extraction vs the latest human correction of one field."""
    data = services.hitl.field_review(db, field_id)
    return FieldReviewOut.model_validate(data)


# ------------------------------------------------------------------- findings


@router.post(
    "/compliance/findings/{finding_id}/review",
    response_model=FindingReviewOut,
)
def review_finding(
    finding_id: UUID,
    body: FindingReviewActionRequest,
    user: User = Depends(require_role(*_REVIEW_WRITE_ROLES)),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> FindingReviewOut:
    """Apply one review action to an engine finding.

    Actions: CONFIRM / CORRECT / REJECT / OVERRIDE / ESCALATE. The state
    machine is enforced in the backend; invalid transitions are rejected with
    409 CONFLICT. Repeating a no-op action is idempotent (no duplicate
    events). REJECT / OVERRIDE / ESCALATE require a reason — an unexplained
    override is never accepted. (The per-verb routes below carry the same
    action in the path.)
    """
    result = services.hitl.review_finding(
        db,
        finding_id=finding_id,
        actor=user,
        action=body.action,
        reason=body.reason,
        note=body.note,
        corrected_value=body.corrected_value,
    )
    return FindingReviewOut.model_validate(result.review)


@router.get(
    "/compliance/findings/{finding_id}/review",
    response_model=FindingReviewOut,
)
def get_finding_review(
    finding_id: UUID,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> FindingReviewOut:
    """The review state + full transition history of one engine finding."""
    review = services.hitl.get_review(db, finding_id)
    return FindingReviewOut.model_validate(review)


# Per-verb convenience routes (Phase 18 suggested API shape). All delegate to
# the same backend-enforced state machine — these are syntax sugar, not
# separate mechanisms.

_VERB_ACTIONS = {
    "confirm": "CONFIRM",
    "reject": "REJECT",
    "override": "OVERRIDE",
    "escalate": "ESCALATE",
}


def _verb_route(verb: str):
    def _handler(
        finding_id: UUID,
        body: FindingReviewVerbRequest | None = None,
        user: User = Depends(require_role(*_REVIEW_WRITE_ROLES)),
        db: Session = Depends(get_db),
        services: Services = Depends(get_services_dep),
    ) -> FindingReviewOut:
        result = services.hitl.review_finding(
            db,
            finding_id=finding_id,
            actor=user,
            action=_VERB_ACTIONS[verb],
            reason=body.reason if body else None,
            note=body.note if body else None,
            corrected_value=body.corrected_value if body else None,
        )
        return FindingReviewOut.model_validate(result.review)

    _handler.__name__ = f"review_finding_{verb}"
    return _handler


for _verb in _VERB_ACTIONS:
    router.post(
        f"/compliance/findings/{{finding_id}}/{_verb}",
        response_model=FindingReviewOut,
    )(_verb_route(_verb))


# ------------------------------------------------------------------ decisions


@router.post(
    "/inspections/{inspection_id}/decision",
    response_model=InspectionDecisionOut,
)
def submit_decision(
    inspection_id: UUID,
    body: DecisionRequest,
    user: User = Depends(require_role(*_REVIEW_WRITE_ROLES)),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> InspectionDecisionOut:
    """Record the FINAL human decision on an inspection.

    This is the only place a legal conclusion is ever recorded — by an
    authorised human, never by the engine. Critical unresolved findings block
    COMPLIANT / NON_COMPLIANT decisions (409) until resolved or explicitly
    deferred via REQUIRES_FURTHER_REVIEW. Earlier decisions are superseded,
    never overwritten or deleted.
    """
    decision = services.hitl.submit_decision(
        db,
        inspection_id=inspection_id,
        actor=user,
        decision=body.decision,
        reason=body.reason,
        note=body.note,
        evaluation_id=body.evaluation_id,
    )
    return _decision_out(decision, db)


@router.get(
    "/inspections/{inspection_id}/decision",
    response_model=InspectionDecisionOut,
)
def get_current_decision(
    inspection_id: UUID,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> InspectionDecisionOut:
    """The CURRENT decision (latest row) — or an explicit 404 when none exists."""
    from app.core.errors import NotFoundError

    decision = services.hitl.latest_decision(db, inspection_id)
    if decision is None:
        raise NotFoundError(
            f"No decision has been recorded for inspection {inspection_id}."
        )
    return _decision_out(decision, db)


@router.get(
    "/inspections/{inspection_id}/decision-history",
    response_model=DecisionHistoryOut,
)
def get_decision_history(
    inspection_id: UUID,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> DecisionHistoryOut:
    """The full decision chain — previous decisions are never deleted."""
    history = services.hitl.decision_history(db, inspection_id)
    outs = [_decision_out(row, db) for row in history]
    return DecisionHistoryOut(
        inspection_id=inspection_id,
        current=outs[-1] if outs else None,
        history=outs,
    )


@router.get(
    "/inspections/{inspection_id}/review-status",
    response_model=ReviewStatusOut,
)
def get_review_status(
    inspection_id: UUID,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    services: Services = Depends(get_services_dep),
) -> ReviewStatusOut:
    """Review progress of an inspection: per-state counts, unresolved
    critical findings, the decision gate, and the current decision."""
    status = services.hitl.review_status(db, inspection_id)
    decision = status.pop("decision", None)
    out = ReviewStatusOut(**status)
    if decision is not None:
        out.decision = _decision_out(decision, db)
    return out
