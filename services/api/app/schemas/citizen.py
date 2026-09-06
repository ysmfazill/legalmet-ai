"""Citizen Mode + complaint schemas (UI-02, extended in UI-03).

Anonymous, camelCase contracts for the consumer flow:
SCAN → DETECT → REVIEW → REPORT → department REVIEW → INSPECTION.

Honesty contract baked into the shapes themselves:
* ``outcome`` is an *automated screening* result — the schema comments and the
  UI both say so; it is never a Legal Metrology determination.
* Screen-outcome vocabulary is deliberately non-committal:
  NO_OBVIOUS_ISSUE / POSSIBLE_ISSUE / REVIEW_REQUIRED / INSUFFICIENT_EVIDENCE /
  IMAGE_UNREADABLE. There is no "violation" outcome — by construction the API
  cannot express a confirmed violation.
* The complaint lifecycle is a controlled state machine (UI-03): the status
  enum and the transition table live HERE, in one place. The service layer is
  the only writer; the frontend never invents statuses.
"""
from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import Field, field_validator

from app.core.enums import ExtractionStatus, FieldType, ImageQualityGrade
from app.schemas.base import CamelModel


class CitizenScreenOutcome(StrEnum):
    NO_OBVIOUS_ISSUE = "NO_OBVIOUS_ISSUE"
    POSSIBLE_ISSUE = "POSSIBLE_ISSUE"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    IMAGE_UNREADABLE = "IMAGE_UNREADABLE"


class CitizenReportStatus(StrEnum):
    """The complaint lifecycle (UI-03) — the single source of truth.

    SUBMITTED → UNDER_REVIEW → (REJECTED | REQUEST_INFORMATION | ACCEPTED)
    REQUEST_INFORMATION → UNDER_REVIEW (citizen responds)
    ACCEPTED → ASSIGNED → INSPECTION_SCHEDULED → INSPECTION_COMPLETED
    INSPECTION_COMPLETED → (ACTION_TAKEN) → CLOSED

    No status expresses a legal conclusion: ACCEPTED means "accepted for
    further review". The official determination lives in the inspection
    workflow's human decision.
    """

    SUBMITTED = "SUBMITTED"
    UNDER_REVIEW = "UNDER_REVIEW"
    REJECTED = "REJECTED"
    REQUEST_INFORMATION = "REQUEST_INFORMATION"
    ACCEPTED = "ACCEPTED"
    ASSIGNED = "ASSIGNED"
    INSPECTION_SCHEDULED = "INSPECTION_SCHEDULED"
    INSPECTION_COMPLETED = "INSPECTION_COMPLETED"
    ACTION_TAKEN = "ACTION_TAKEN"
    CLOSED = "CLOSED"


class ComplaintAction(StrEnum):
    """Department actions on a complaint. The service layer maps each action
    to its allowed from-states; illegal transitions are rejected with 422."""

    START_REVIEW = "START_REVIEW"
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"
    REQUEST_INFORMATION = "REQUEST_INFORMATION"
    ASSIGN = "ASSIGN"
    CREATE_INSPECTION = "CREATE_INSPECTION"
    COMPLETE_INSPECTION = "COMPLETE_INSPECTION"
    RECORD_ACTION = "RECORD_ACTION"
    CLOSE = "CLOSE"


class CitizenDetectedField(CamelModel):
    field_type: FieldType
    label: str
    raw_text: str
    normalized_value: str | None = None
    confidence: float
    status: ExtractionStatus


class CitizenQualitySummary(CamelModel):
    grade: ImageQualityGrade | None = None
    score: float | None = None
    status: str | None = None
    readable: bool = False


class CitizenScanOut(CamelModel):
    id: UUID
    reference: str
    filename: str
    quality: CitizenQualitySummary
    outcome: CitizenScreenOutcome
    outcome_rationale: str | None = None
    detected_fields: list[CitizenDetectedField] = []
    ocr_provider: str | None = None
    ocr_model: str | None = None
    image_url: str | None = None
    created_at: datetime


class CitizenReportCreate(CamelModel):
    scan_id: UUID
    product: str = Field(min_length=1, max_length=255)
    shop: str | None = Field(default=None, max_length=255)
    location: str | None = Field(default=None, max_length=255)
    issue: str = Field(min_length=1, max_length=2000)
    description: str | None = Field(default=None, max_length=4000)
    reporter_name: str | None = Field(default=None, max_length=128)
    reporter_contact: str | None = Field(default=None, max_length=128)

    @field_validator("product", "issue")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value.strip()


class CitizenReportOut(CamelModel):
    id: UUID
    reference: str
    scan_id: UUID
    status: CitizenReportStatus
    product: str
    shop: str | None = None
    location: str | None = None
    issue: str
    description: str | None = None
    reporter_name: str | None = None
    reporter_contact: str | None = None
    created_at: datetime
    updated_at: datetime | None = None
    is_live: bool = True


class ComplaintEventOut(CamelModel):
    """One recorded complaint-history entry (the timeline's only source)."""

    id: UUID
    event: str
    actor_type: str
    actor_name: str | None = None
    note: str | None = None
    created_at: datetime


class ComplaintLinkedInspectionOut(CamelModel):
    id: UUID
    reference_no: str
    status: str


class CitizenReportDetailOut(CitizenReportOut):
    """Citizen-facing complaint detail: status, real timeline, the pending
    information request (if any) and the linked inspection summary."""

    pending_info_request: str | None = None
    events: list[ComplaintEventOut] = []
    inspection: ComplaintLinkedInspectionOut | None = None


class CitizenRespondRequest(CamelModel):
    message: str = Field(min_length=1, max_length=4000)
    location: str | None = Field(default=None, max_length=255)

    @field_validator("message")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value.strip()


# --- Department (staff) complaint contracts ---------------------------------


class ComplaintSummaryOut(CamelModel):
    id: UUID
    reference: str
    status: CitizenReportStatus
    product: str
    location: str | None = None
    issue: str
    # SYSTEM SCREENING priority (deterministic, from scan evidence) —
    # distinct from official_priority below.
    screening_risk: str | None = None
    official_priority: str | None = None
    assigned_inspector_id: UUID | None = None
    assigned_inspector_name: str | None = None
    inspection_id: UUID | None = None
    inspection_reference: str | None = None
    # UI-05: the linked inspection's own lifecycle status (None when the
    # complaint has not been converted) — drives the queue's inspection column.
    inspection_status: str | None = None
    has_image_evidence: bool = False
    # UI-04: deterministic evidence-completeness score (0–100). How complete
    # the recorded evidence is — never a violation likelihood.
    evidence_completeness: int = 0
    pending_info_request: str | None = None
    created_at: datetime
    updated_at: datetime | None = None


class ComplaintDetailOut(ComplaintSummaryOut):
    shop: str | None = None
    description: str | None = None
    reporter_name: str | None = None
    reporter_contact: str | None = None
    # The submit-time scan evidence snapshot (image URL, detected
    # declarations, quality, OCR provenance, citizen follow-ups).
    evidence: dict | None = None
    events: list[ComplaintEventOut] = []
    inspection: ComplaintLinkedInspectionOut | None = None


class ComplaintTransitionRequest(CamelModel):
    action: ComplaintAction
    # Required for REJECT (reason) and REQUEST_INFORMATION (what is needed).
    reason: str | None = Field(default=None, max_length=4000)
    # Required for ASSIGN.
    inspector_id: UUID | None = None
    # Optional OFFICIAL priority decision (LOW/MEDIUM/HIGH) — may accompany
    # any action; only this staff path can set it.
    official_priority: str | None = Field(default=None, pattern="^(LOW|MEDIUM|HIGH)$")


class ComplaintStatsOut(CamelModel):
    """Department KPIs — every value is a real database COUNT."""

    total: int = 0
    submitted: int = 0
    under_review: int = 0
    request_information: int = 0
    accepted: int = 0
    assigned: int = 0
    inspection_pending: int = 0
    inspection_completed: int = 0
    action_taken: int = 0
    closed: int = 0
    rejected: int = 0
    unassigned_open: int = 0


class SourceComplaintOut(CamelModel):
    """GET /inspections/{id}/source-complaint (UI-05) — the complaint brief an
    inspector needs to understand WHY a targeted inspection exists, plus the
    immutable citizen evidence that originated it.

    Honesty contract: everything here is *source evidence submitted by a
    citizen* — a suspected issue to verify, never a finding. The official
    determination belongs to the inspection workflow's human decision.
    """

    id: UUID
    reference: str
    status: CitizenReportStatus
    product: str
    shop: str | None = None
    location: str | None = None
    issue: str
    description: str | None = None
    reporter_name: str | None = None
    screening_risk: str | None = None
    official_priority: str | None = None
    assigned_inspector_id: UUID | None = None
    assigned_inspector_name: str | None = None
    evidence: dict | None = None
    event_count: int = 0
    created_at: datetime
