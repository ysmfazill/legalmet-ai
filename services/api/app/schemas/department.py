"""Department Command Center contracts (UI-04).

One aggregated, read-only dashboard payload for the department route:
KPIs, complaint trend, status / risk distributions, evidence completeness,
needs-attention signals, the complaint → inspection pipeline, location
rollups, recent activity and the priority queue.

Honesty contract (unchanged from UI-02/UI-03):

* Every number is a real database COUNT / GROUP BY result — zero when the
  database is empty, never a fabricated figure.
* ``priority`` values are TRIAGE signals only: the OFFICIAL decision where a
  department transition set one, otherwise the deterministic SYSTEM SCREENING
  value. Neither is a legal determination.
* ``evidence_completeness`` measures how complete a complaint's evidence is
  (photo, OCR extraction, descriptions, follow-ups) — it is explicitly NOT a
  probability of violation.
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.schemas.base import CamelModel


class DepartmentKpisOut(CamelModel):
    """Headline figures — every value is a real database COUNT."""

    total_complaints: int = 0
    # SUBMITTED + UNDER_REVIEW + REQUEST_INFORMATION: awaiting/under first review.
    pending_review: int = 0
    # Open complaints whose effective priority (official, else screening) is HIGH.
    high_priority: int = 0
    # Complaints a department decision converted into a real inspection.
    converted_to_inspection: int = 0
    # Status INSPECTION_SCHEDULED: inspection created, not yet completed.
    under_investigation: int = 0
    # ACTION_TAKEN + CLOSED: department recorded an outcome.
    resolved: int = 0
    rejected: int = 0
    unassigned_open: int = 0


class ComplaintTrendPointOut(CamelModel):
    """Complaints created on one UTC day (real created_at grouping, zero-filled)."""

    date: str  # YYYY-MM-DD
    count: int


class EvidenceCompletenessOut(CamelModel):
    """Deterministic evidence completeness over OPEN complaints.

    Bands: complete ≥ 80, partial 50–79, minimal < 50. The scoring rule is
    fixed and explainable (see the department service); it says how complete
    the recorded evidence is, nothing about violation likelihood.
    """

    average: int = 0  # 0..100 across scored complaints (0 when none)
    scored: int = 0
    complete: int = 0
    partial: int = 0
    minimal: int = 0


class AttentionItemOut(CamelModel):
    """One actionable "needs attention" signal with its queue filter."""

    kind: str
    label: str
    description: str
    count: int
    # Query params for GET /citizen/complaints — the filtered queue to open.
    filters: dict[str, str] = {}


class DepartmentPipelineOut(CamelModel):
    """CITIZEN → REPORT → REVIEW → PRIORITIZE → INSPECT → VERIFY → DECIDE,
    each stage a real count of complaints that actually reached it."""

    citizen_reports: int = 0
    department_review: int = 0
    accepted: int = 0
    inspection_assigned: int = 0
    inspection_completed: int = 0
    decision: int = 0


class LocationRollupOut(CamelModel):
    area: str
    complaints: int
    high_priority: int
    inspections: int


class PhysicalVerificationOut(CamelModel):
    """UI-07 — physical verification workload, from real records only.

    Every count is a SQL COUNT over actual verification tasks / results /
    lots. No number here is a compliance signal: "awaiting measurement"
    means evidence is missing, never that a package is suspect.
    """

    # Inspections with at least one open REQUIRED measurement task
    # (inspection-level; lot-anchored tasks are counted under lots).
    inspections_requiring_verification: int = 0
    # Total recorded measurement results (append-only rows).
    measurements_completed: int = 0
    # Lots still IN_PROGRESS (decision not yet submitted).
    lots_under_verification: int = 0
    # IN_PROGRESS lots with sampled packages still awaiting a measurement.
    lots_awaiting_measurement: int = 0
    # Lots with a submitted decision (COMPLIANT/NON_COMPLIANT/REQUIRES_REVIEW).
    lots_completed: int = 0


class DepartmentActivityOut(CamelModel):
    """One real audit event from the department's complaint operations."""

    id: UUID
    event: str
    actor_name: str | None = None
    created_at: datetime
    reference: str | None = None  # complaint reference (CMP-…) from the payload
    report_id: UUID | None = None  # entity_id — the link target


class PriorityComplaintOut(CamelModel):
    """A queue row for the priority section, with its triage signals."""

    id: UUID
    reference: str
    status: str
    product: str
    issue: str
    location: str | None = None
    # Effective priority: the OFFICIAL decision when set, else SYSTEM SCREENING.
    priority: str | None = None
    priority_source: str | None = None  # OFFICIAL_DECISION | SYSTEM_SCREENING
    evidence_completeness: int = 0
    created_at: datetime


class DepartmentDashboardOut(CamelModel):
    generated_at: datetime
    window_days: int = Field(ge=1, le=365)
    # Complaints created inside the trend window (the chart's total).
    window_complaints: int = 0
    kpis: DepartmentKpisOut
    status_distribution: dict[str, int] = {}
    trend: list[ComplaintTrendPointOut] = []
    # Effective priority over OPEN complaints: HIGH / MEDIUM / LOW / UNSET.
    risk_distribution: dict[str, int] = {}
    evidence: EvidenceCompletenessOut
    physical_verification: PhysicalVerificationOut = PhysicalVerificationOut()
    needs_attention: list[AttentionItemOut] = []
    pipeline: DepartmentPipelineOut
    locations: list[LocationRollupOut] = []
    recent_activity: list[DepartmentActivityOut] = []
    priority_queue: list[PriorityComplaintOut] = []
