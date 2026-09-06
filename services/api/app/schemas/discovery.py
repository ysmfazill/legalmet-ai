"""UI-09 discovery schemas — global search, inspection history, product directory.

Every shape here is a READ model over existing entities: no new tables, no
duplicated entities. Privacy by construction: search results never carry
citizen reporter names or contacts, internal notes, or storage keys.
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from app.schemas.base import CamelModel

# --------------------------------------------------------------------- search


class SearchInspectionHit(CamelModel):
    id: UUID
    reference: str
    product_name: str | None = None
    status: str
    result: str
    inspector_name: str | None = None
    source: str
    created_at: datetime


class SearchComplaintHit(CamelModel):
    id: UUID
    reference: str
    status: str
    product: str
    issue: str
    location: str | None = None
    inspection_id: UUID | None = None
    created_at: datetime


class SearchProductHit(CamelModel):
    id: UUID
    name: str
    category: str
    gtin: str | None = None
    inspection_count: int
    last_inspection_at: datetime | None = None


class SearchReportHit(CamelModel):
    id: UUID
    inspection_id: UUID
    inspection_reference: str
    status: str
    version: int
    result: str


class SearchFindingHit(CamelModel):
    id: UUID
    inspection_id: UUID
    inspection_reference: str
    rule_code: str | None = None
    status: str
    severity: str
    detected_value: str | None = None
    created_at: datetime


class SearchEvidenceHit(CamelModel):
    id: UUID
    inspection_id: UUID
    inspection_reference: str
    field_type: str
    value: str
    image_id: UUID | None = None
    created_at: datetime


class SearchResults(CamelModel):
    """Grouped global-search results (UI-09 §2)."""

    query: str
    inspections: list[SearchInspectionHit] = []
    complaints: list[SearchComplaintHit] = []
    products: list[SearchProductHit] = []
    reports: list[SearchReportHit] = []
    findings: list[SearchFindingHit] = []
    evidence: list[SearchEvidenceHit] = []


# -------------------------------------------------------------------- history


class HistoryReportRef(CamelModel):
    """The report state for one inspection (link chip + status)."""

    id: UUID
    status: str
    version: int


class InspectionHistoryItem(CamelModel):
    id: UUID
    reference: str
    created_at: datetime
    product_name: str | None = None
    product_category: str | None = None
    inspector_name: str | None = None
    # Where the inspection came from a citizen complaint, the reported shop /
    # establishment (§7 "Establishment"). Direct inspections have none.
    establishment: str | None = None
    source: str  # CITIZEN_COMPLAINT | DIRECT_INSPECTION
    source_complaint_reference: str | None = None
    status: str
    result: str  # decision → evaluation status → NOT_EVALUATED
    image_count: int = 0  # real captured-evidence count
    report: HistoryReportRef | None = None


class InspectionHistoryKpis(CamelModel):
    """Real COUNT()s over the filtered history set — never hardcoded."""

    total: int
    compliant: int
    non_compliant: int
    review_required: int
    open: int


class TimelineEvent(CamelModel):
    """One REAL recorded event on an inspection's chain — never fabricated."""

    stage: str  # canonical stage key (CREATED, PACKAGE_CAPTURED, ...)
    label: str  # human label
    event_type: str | None = None
    at: datetime
    actor_name: str | None = None
    detail: str | None = None
    # Cross-links so the UI can offer the next hop without losing context.
    report_id: UUID | None = None
    decision: str | None = None


class InspectionTimeline(CamelModel):
    inspection_id: UUID
    reference: str
    events: list[TimelineEvent]


# ------------------------------------------------------------------- products


class ProductSummary(CamelModel):
    id: UUID
    name: str
    category: str
    gtin: str | None = None
    inspection_count: int
    finding_count: int
    last_inspection_at: datetime | None = None
    latest_result: str  # NOT_EVALUATED when nothing was ever evaluated


class ProductDeclaredField(CamelModel):
    """Latest detected declaration for one field type across inspections."""

    field_type: str
    raw_text: str
    normalized_value: str | None = None
    unit: str | None = None
    inspection_id: UUID
    inspection_reference: str
    detected_at: datetime


class ProductInspectionRef(CamelModel):
    id: UUID
    reference: str
    created_at: datetime
    inspector_name: str | None = None
    result: str
    report: HistoryReportRef | None = None
    source: str


class ProductFindingHistory(CamelModel):
    """Recurring finding pattern — a HISTORICAL RECORD, never a verdict."""

    rule_code: str | None
    label: str
    occurrence_count: int
    inspection_count: int
    review_required_count: int
    non_compliant_count: int


class ProductEvidenceImage(CamelModel):
    id: UUID
    inspection_id: UUID
    inspection_reference: str
    image_type: str
    original_filename: str
    created_at: datetime
    field_types: list[str] = []


class ProductDetail(CamelModel):
    id: UUID
    name: str
    category: str
    gtin: str | None = None
    inspection_count: int
    finding_count: int
    last_inspection_at: datetime | None = None
    latest_result: str
    declared_fields: list[ProductDeclaredField] = []
    inspections: list[ProductInspectionRef] = []
    findings_history: list[ProductFindingHistory] = []
    evidence_gallery: list[ProductEvidenceImage] = []
    # Honesty contract: history proves nothing about the current package.
    boundary_note: str = (
        "Historical inspection record — previous inspections do not prove "
        "current compliance."
    )
