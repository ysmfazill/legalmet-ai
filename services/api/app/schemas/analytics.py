"""Batch + analytics schemas."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from app.core.enums import BatchStatus, ComplianceStatus, FieldType, InspectionStatus
from app.schemas.base import CamelModel
from app.schemas.inspection import FindingCounts, InspectionSummaryOut


class BatchStats(CamelModel):
    total: int = 0
    by_status: dict[ComplianceStatus, int] = {}
    review_required: int = 0
    potential_violations: int = 0


class BatchInspectionOut(CamelModel):
    id: UUID
    name: str
    description: str | None = None
    status: BatchStatus
    total_count: int
    stats: BatchStats | None = None
    created_by: UUID | None = None
    is_demo: bool
    created_at: datetime
    updated_at: datetime


class RecurringViolation(CamelModel):
    field_type: FieldType | None = None
    rule_id: UUID | None = None
    rule_code: str | None = None
    count: int
    affected_inspections: int


class InspectionStatusBreakdown(CamelModel):
    total: int = 0
    by_status: dict[InspectionStatus, int] = {}


class DashboardSummary(CamelModel):
    inspections: InspectionStatusBreakdown
    findings: FindingCounts
    recent_inspections: list[InspectionSummaryOut] = []
    recurring_violations: list[RecurringViolation] = []
    generated_at: datetime


# ------------------------------------------------------- UI-09 operational ----


class OperationalKpis(CamelModel):
    """Real counts + rates. Rates are None (rendered N/A) when the denominator
    is zero — an invented 0% would be a fabricated statistic (UI-09 §13/§34)."""

    total_inspections: int
    complaint_led_inspections: int
    decided_inspections: int
    compliance_rate: float | None
    non_compliance_rate: float | None
    review_required: int
    open_inspections: int
    average_evidence_completeness: float | None


class TrendPoint(CamelModel):
    period: str  # ISO period label (day/week/month bucket)
    count: int


class OutcomeSlice(CamelModel):
    result: str
    count: int
    # None when the denominator is zero — the UI renders N/A, never 0%.
    percentage: float | None


class ComplaintPipelineStage(CamelModel):
    stage: str
    label: str
    count: int


class ComplaintPipeline(CamelModel):
    """Citizen Complaint → Department Reviewed → Accepted → Converted to
    Inspection → Inspection Completed → Finding Generated. Real counts only."""

    stages: list[ComplaintPipelineStage]
    conversion_rate: float | None = None


class EvidenceQualityMetrics(CamelModel):
    """Evidence-first analytics from the Evidence Planner (UI-09 §17)."""

    inspections_with_planner: int
    average_evidence_completeness: float | None
    incomplete_inspections: int
    missing_required_evidence: int
    measurements_pending: int
    reports_blocked_by_evidence: int


class FindingCategorySlice(CamelModel):
    """Top finding categories from ACTUAL engine findings — no invented
    categories (UI-09 §18)."""

    rule_code: str
    label: str
    count: int
    inspection_count: int
    percentage: float | None


class RepeatFindingPattern(CamelModel):
    """Recurring engine finding across inspections of one product — neutral
    wording: a repeated INSPECTION finding, never a violator label (§21)."""

    product_name: str
    rule_code: str
    label: str
    inspection_count: int
    occurrence_count: int


class LocationSlice(CamelModel):
    """Location intelligence from REAL complaint locations only (§19)."""

    location: str
    complaint_count: int
    inspection_count: int
    finding_count: int


class LocationIntelligence(CamelModel):
    locations: list[LocationSlice] = []
    sufficient: bool
    note: str | None = None


class ReportAnalytics(CamelModel):
    generated: int
    finalized: int
    amended: int
    pdf_exports: int
    docx_exports: int


class OperationalAnalytics(CamelModel):
    kpis: OperationalKpis
    trend: list[TrendPoint]
    granularity: str
    outcomes: list[OutcomeSlice]
    complaint_pipeline: ComplaintPipeline
    evidence_quality: EvidenceQualityMetrics
    finding_categories: list[FindingCategorySlice]
    repeat_findings: list[RepeatFindingPattern]
    locations: LocationIntelligence
    reports: ReportAnalytics
    # Honest banner when the dataset is small (§12).
    data_note: str | None = None
    generated_at: datetime
