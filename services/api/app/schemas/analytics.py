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
