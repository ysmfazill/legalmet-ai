"""Report schemas (UI-08).

REPORT → VERSIONS → EVIDENCE MANIFEST → EXPORTS.

Honesty contracts carried by every read model:

* the report result is the inspector's recorded decision — never a
  report-side invention; NOT_EVALUATED while no decision exists;
* every finding row keeps the deterministic engine status AND the human
  review state side by side (AI-assisted, inspector-reviewed);
* regulatory basis comes only from the frozen provenance of the engine
  evaluation — no rule is invented in the report layer;
* evidence completeness distinguishes REQUIRED (blocks finalization) from
  RECOMMENDED (never blocks) — a recommendation is never confused with a
  legal requirement.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import Field

from app.core.enums import ReportStatus
from app.schemas.base import CamelModel

REPORT_BOUNDARY_NOTE = (
    "Reports are decision-support artifacts generated from inspection "
    "evidence. They do not replace the authority of the authorized Legal "
    "Metrology inspector."
)


# ------------------------------------------------------------------ requests


class ReportCreateRequest(CamelModel):
    inspection_id: UUID
    # Optional note recorded with the creation audit event.
    note: str | None = None


class ReportGenerateRequest(CamelModel):
    note: str | None = None


class ReportFinalizeRequest(CamelModel):
    note: str | None = None


class ReportAmendRequest(CamelModel):
    """Mandatory reason — an amendment without explanation is never accepted."""

    reason: str = Field(min_length=1)
    note: str | None = None


# ------------------------------------------------------------------- read out


class ReportSummaryOut(CamelModel):
    """One row of the Report Center list (real DB records only)."""

    id: UUID
    inspection_id: UUID
    inspection_reference: str
    product_name: str | None = None
    inspection_date: datetime | None = None
    inspector_name: str | None = None
    result: str
    status: ReportStatus
    version: int
    evidence_count: int = 0
    generated_at: datetime | None = None
    finalized_at: datetime | None = None
    amendment_reason: str | None = None
    created_by: UUID
    updated_at: datetime


class ReportListOut(CamelModel):
    items: list[ReportSummaryOut]
    total: int
    page: int
    page_size: int


class ReportKpisOut(CamelModel):
    total: int
    draft: int
    finalized: int
    exported: int
    under_review: int
    amended: int
    requires_review: int


class ReportSnapshotFindingOut(CamelModel):
    """One finding frozen into a snapshot — engine status + human review."""

    id: UUID
    status: str
    severity: str
    requirement: str
    rule_code: str | None = None
    rule_version_label: str | None = None
    regulatory_version_label: str | None = None
    detected_value: str | None = None
    expected_value: str | None = None
    explanation: str
    review_state: str
    evidence_status: str
    source: str  # SOURCE (citizen scan) / OFFICIAL (inspection) / NONE


class ReportSnapshotMeasurementOut(CamelModel):
    measurement_id: UUID
    anchor: str
    declared_value: str | None = None
    measured_value: float | None = None
    unit: str | None = None
    observed_difference: str | None = None
    instrument_id: str | None = None
    instrument_verification_status: str | None = None
    recorded_by: UUID
    recorded_at: datetime
    evaluation_status: str
    evaluation_outcome: str | None = None
    evaluation_rule_code: str | None = None


class ReportSnapshotLotOut(CamelModel):
    lot_id: UUID
    label: str
    declared_value: str
    lot_size: int
    sampled: int
    measured: int
    decision: str | None = None
    decision_reason: str | None = None
    sampling_label: str


class ReportSnapshotDecisionOut(CamelModel):
    decision: str
    reason: str | None = None
    decided_by: UUID
    decided_by_name: str | None = None
    decided_at: datetime
    evaluation_id: UUID | None = None


class ReportEvidenceCompletenessOut(CamelModel):
    """Planner status distilled for the report — REQUIRED vs RECOMMENDED."""

    required_total: int
    required_open: int
    recommended_open: int
    evidence_items: int
    finding_rows: int
    counts: dict[str, int] = {}
    blockers: list[str] = []
    can_finalize: bool = False


class ReportVersionOut(CamelModel):
    version: int
    id: UUID
    reason: str
    created_at: datetime
    created_by: UUID
    created_by_name: str | None = None
    status_at_creation: str | None = None


class ReportEvidenceItemOut(CamelModel):
    """One evidence-manifest entry: E-00N + a reference to an existing record."""

    id: UUID
    ref: str  # "E-001"
    sequence: int
    evidence_type: str
    evidence_id: UUID
    label: str
    detail: dict[str, Any] | None = None


class ReportSourceComplaintOut(CamelModel):
    """Source context for complaint-originated inspections (UI-05 read model)."""

    reference: str
    status: str
    product: str | None = None
    location: str | None = None
    issue: str
    description: str | None = None
    priority: str | None = None
    submitted_at: datetime | None = None


class ReportDetailOut(CamelModel):
    """GET /reports/{id} — the full current read model."""

    id: UUID
    inspection_id: UUID
    inspection_reference: str
    status: ReportStatus
    result: str
    version: int
    product_name: str | None = None
    product_category: str | None = None
    inspection_date: datetime | None = None
    inspection_status: str | None = None
    inspector_name: str | None = None
    inspector_id: UUID | None = None
    created_by: UUID
    created_by_name: str | None = None
    generated_at: datetime | None = None
    finalized_at: datetime | None = None
    finalized_by: UUID | None = None
    finalized_by_name: str | None = None
    amendment_reason: str | None = None
    source_complaint: ReportSourceComplaintOut | None = None
    evidence: ReportEvidenceCompletenessOut
    versions: list[ReportVersionOut] = []
    snapshot: dict[str, Any] | None = None
    boundary_note: str = REPORT_BOUNDARY_NOTE


class ReportAuditEventOut(CamelModel):
    id: UUID
    actor_id: UUID | None = None
    actor_role: str | None = None
    actor_name: str | None = None
    event_type: str
    report_id: UUID | None = None
    inspection_id: UUID | None = None
    payload: dict[str, Any] | None = None
    created_at: datetime


class ReportEvidencePackOut(CamelModel):
    """GET /reports/{id}/evidence-pack — the exportable evidence bundle."""

    pack_id: UUID
    report_id: UUID
    inspection_id: UUID
    report_version: int
    created_at: datetime
    evidence_count: int
    completeness: ReportEvidenceCompletenessOut
    items: list[ReportEvidenceItemOut]
    source_complaint: ReportSourceComplaintOut | None = None
    decision: ReportSnapshotDecisionOut | None = None
    audit_events: list[ReportAuditEventOut] = []
    boundary_note: str = REPORT_BOUNDARY_NOTE


class ReportAuditOut(CamelModel):
    report_id: UUID
    inspection_id: UUID
    events: list[ReportAuditEventOut]
