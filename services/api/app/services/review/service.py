"""Review service — human-in-the-loop decision recording.

Records an inspector's decision on a finding as an immutable
:class:`ReviewAction` and maintains the finding's human-decision overlay
(``review_status`` / ``is_reviewed``) WITHOUT ever overwriting the original
machine ``status``. Every review is appended to the audit trail.

Decision semantics:
    ACCEPT   -> confirm the machine result (review_status = status), reviewed
    CORRECT  -> assert a different status (requires corrected_status), reviewed
    REJECT   -> dismiss the finding as a false positive, reviewed
    ESCALATE -> hand off to a supervisor (workflow; not finalized)
    REQUEST_RESCAN -> ask for better images (workflow; not finalized)
    NOTE     -> annotation only (not finalized)
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.core.enums import AuditEventType, ReviewActionType
from app.core.errors import ValidationError
from app.models import ComplianceFinding, ReviewAction
from app.schemas.finding import ReviewFindingRequest
from app.services.audit.service import AuditService

_FINALIZING = {ReviewActionType.ACCEPT, ReviewActionType.REJECT, ReviewActionType.CORRECT}


class ReviewService:
    def __init__(self, audit: AuditService) -> None:
        self._audit = audit

    def record_review(
        self,
        db: Session,
        *,
        finding: ComplianceFinding,
        reviewer_id: UUID | None,
        request: ReviewFindingRequest,
    ) -> ReviewAction:
        action = request.action
        if action == ReviewActionType.CORRECT and request.corrected_status is None:
            raise ValidationError("A corrected status is required when correcting a finding.")

        corrected = request.corrected_status.value if request.corrected_status else None
        review = ReviewAction(
            finding_id=finding.id,
            reviewer_id=reviewer_id,
            action=action.value,
            corrected_status=corrected,
            reason=request.reason,
            note=request.note,
        )
        db.add(review)

        if action in _FINALIZING:
            finding.is_reviewed = True
            if action == ReviewActionType.ACCEPT:
                finding.review_status = finding.status
            elif action == ReviewActionType.CORRECT:
                finding.review_status = corrected
            else:  # REJECT
                finding.review_status = None

        db.flush()

        self._audit.record(
            db,
            event_type=AuditEventType.REVIEW_RECORDED,
            entity_type="compliance_finding",
            entity_id=finding.id,
            actor_id=reviewer_id,
            inspection_id=finding.inspection_id,
            payload={"action": action.value, "correctedStatus": corrected},
        )
        return review
