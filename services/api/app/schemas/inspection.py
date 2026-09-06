"""Inspection + package schemas."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.core.enums import InspectionStatus, PackageStatus
from app.schemas.base import CamelModel
from app.schemas.image import ImageOut
from app.schemas.product import ProductOut


class FindingCounts(CamelModel):
    total: int = 0
    compliant: int = 0
    potential_violation: int = 0
    review_required: int = 0
    not_applicable: int = 0
    low_confidence: int = 0
    image_quality_insufficient: int = 0


class PackageOut(CamelModel):
    id: UUID
    inspection_id: UUID
    product_id: UUID | None = None
    label: str
    status: PackageStatus = PackageStatus.CREATED
    created_at: datetime
    images: list[ImageOut] = []


class SourceComplaintRefOut(CamelModel):
    """Compact pointer to the citizen complaint an inspection was targeted
    from (UI-05). Carried on inspection list/detail rows so the inspector
    side can show provenance without a second fetch."""

    id: UUID
    reference: str
    status: str
    issue: str
    location: str | None = None
    priority: str | None = None


class InspectionSummaryOut(CamelModel):
    id: UUID
    reference_no: str
    status: InspectionStatus
    product_id: UUID | None = None
    inspector_id: UUID | None = None
    # UI-05: the assigned inspector's real name (was only the id before).
    inspector_name: str | None = None
    batch_id: UUID | None = None
    note: str | None = None
    is_demo: bool
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None
    finding_counts: FindingCounts | None = None
    # UI-05: present when this inspection originated from a citizen complaint.
    source_complaint: SourceComplaintRefOut | None = None


class InspectionDetailOut(InspectionSummaryOut):
    product: ProductOut | None = None
    packages: list[PackageOut] = []


class CreateInspectionRequest(CamelModel):
    product_name: str = Field(min_length=1, max_length=255)
    product_category: str = Field(min_length=1, max_length=120)
    gtin: str | None = Field(default=None, max_length=64)
    note: str | None = Field(default=None, max_length=2000)
    batch_id: UUID | None = None


class AssignInspectionRequest(CamelModel):
    """POST /inspections/{id}/assign (UI-05) — a department act."""

    inspector_id: UUID
    note: str | None = Field(default=None, max_length=2000)
    # Must be explicitly true to move an already-assigned inspection to a
    # different inspector (guards accidental duplicate assignment).
    reassign: bool = False


class AnalyzeInspectionRequest(CamelModel):
    # Drives version-aware rule selection; defaults to the inspection's date.
    context_date: datetime | None = None
