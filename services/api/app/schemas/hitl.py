"""Human-in-the-loop review schemas (Prompt 8).

Every payload carries the HITL boundary note: AI assists, the authorised
inspector decides. Requests that demand a reason (override, reject,
non-compliant decision, escalation) enforce it at the schema layer — an
unexplained human action is structurally impossible.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import Field, model_validator

from app.core.enums import FindingReviewState, InspectionDecisionType
from app.schemas.base import CamelModel

HITL_BOUNDARY_NOTE = (
    "LegalMet AI provides AI-assisted inspection analysis and traceability. "
    "The authorized inspector remains responsible for the final inspection "
    "decision."
)


class FieldCorrectRequest(CamelModel):
    """POST /fields/{field_id}/correct — inspector corrects an extracted value."""

    corrected_value: str = Field(min_length=1, max_length=255)
    reason: str = Field(min_length=3, max_length=2000)
    # Optional: the evaluation whose finding triggered this correction.
    triggered_by_evaluation_id: UUID | None = None


class FieldCorrectionOut(CamelModel):
    id: UUID
    extracted_field_id: UUID
    inspection_id: UUID
    corrected_by: UUID
    corrected_by_name: str | None = None
    corrected_at: datetime
    previous_value: str | None = None
    previous_raw_text: str | None = None
    corrected_value: str
    reason: str
    triggered_by_evaluation_id: UUID | None = None
    created_at: datetime


class FieldReviewOut(CamelModel):
    """The human-review overlay of one extracted field (read model)."""

    field_id: UUID
    inspection_id: UUID
    original_value: str | None = None
    original_raw_text: str | None = None
    ai_confidence: float | None = None
    ai_extraction_status: str | None = None
    corrected_value: str | None = None
    corrected_at: datetime | None = None
    corrected_by: UUID | None = None
    corrected_by_name: str | None = None
    correction_reason: str | None = None
    correction_count: int = 0
    boundary_note: str = HITL_BOUNDARY_NOTE


class FindingReviewActionRequest(CamelModel):
    """POST /compliance/findings/{finding_id}/review — one review action.

    ``action`` is one of CONFIRM / CORRECT / REJECT / OVERRIDE / ESCALATE.
    REJECT / OVERRIDE / ESCALATE require ``reason`` (enforced in the service
    layer — an unexplained override is never accepted).
    """

    action: str | None = Field(default=None, min_length=4, max_length=16)
    reason: str | None = Field(default=None, max_length=2000)
    note: str | None = Field(default=None, max_length=2000)
    # For the CORRECT action (creates a FieldCorrection via the same
    # correction workflow as POST /fields/{field_id}/correct).
    corrected_value: str | None = Field(default=None, max_length=255)


class FindingReviewVerbRequest(CamelModel):
    """Body of the per-verb routes (confirm/reject/override/escalate) — the
    action is the path verb, so no ``action`` field here."""

    reason: str | None = Field(default=None, max_length=2000)
    note: str | None = Field(default=None, max_length=2000)
    corrected_value: str | None = Field(default=None, max_length=255)


class FindingReviewEventOut(CamelModel):
    id: UUID
    review_id: UUID
    actor_id: UUID | None = None
    actor_role: str | None = None
    action: str
    previous_state: FindingReviewState | None = None
    new_state: FindingReviewState | None = None
    reason: str | None = None
    payload: dict[str, Any]
    created_at: datetime


class FindingReviewOut(CamelModel):
    # Null when no review row exists yet: the finding's implicit state is
    # PENDING_REVIEW and the overlay below is a synthetic read-only view.
    id: UUID | None = None
    finding_id: UUID
    inspection_id: UUID
    evaluation_id: UUID | None = None
    state: FindingReviewState
    reviewed_by: UUID | None = None
    reviewed_by_name: str | None = None
    reviewed_at: datetime | None = None
    reason: str | None = None
    correction_id: UUID | None = None
    escalated_to_role: str | None = None
    events: list[FindingReviewEventOut] = []
    boundary_note: str = HITL_BOUNDARY_NOTE


class DecisionRequest(CamelModel):
    """POST /inspections/{id}/decision — the final human decision."""

    decision: InspectionDecisionType
    reason: str | None = Field(default=None, max_length=4000)
    note: str | None = Field(default=None, max_length=2000)
    # Optional explicit evaluation reference; defaults to the latest.
    evaluation_id: UUID | None = None

    @model_validator(mode="after")
    def _reason_required(self) -> DecisionRequest:
        if self.decision in (
            InspectionDecisionType.NON_COMPLIANT,
            InspectionDecisionType.REQUIRES_FURTHER_REVIEW,
        ) and not (self.reason and self.reason.strip()):
            raise ValueError(
                "A reason is mandatory for NON_COMPLIANT and "
                "REQUIRES_FURTHER_REVIEW decisions."
            )
        return self


class InspectionDecisionOut(CamelModel):
    id: UUID
    inspection_id: UUID
    decision: InspectionDecisionType
    decided_by: UUID
    decided_by_name: str | None = None
    decided_at: datetime
    reason: str | None = None
    evaluation_id: UUID | None = None
    supersedes_decision_id: UUID | None = None
    payload: dict[str, Any]
    created_at: datetime
    boundary_note: str = HITL_BOUNDARY_NOTE


class DecisionHistoryOut(CamelModel):
    inspection_id: UUID
    current: InspectionDecisionOut | None = None
    history: list[InspectionDecisionOut] = []
    boundary_note: str = HITL_BOUNDARY_NOTE


class ReviewStatusOut(CamelModel):
    """GET /inspections/{id}/review-status — review progress of an inspection."""

    inspection_id: UUID
    total_findings: int = 0
    pending_review: int = 0
    confirmed: int = 0
    corrected: int = 0
    rejected: int = 0
    overridden: int = 0
    escalated: int = 0
    # Findings with no review row yet are implicitly PENDING_REVIEW.
    unreviewed: int = 0
    critical_unresolved: int = 0
    decision: InspectionDecisionOut | None = None
    # Gate (Phase 13): can a final decision be recorded right now?
    decision_allowed: bool = False
    decision_blockers: list[str] = []
    boundary_note: str = HITL_BOUNDARY_NOTE
