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


class InspectionSummaryOut(CamelModel):
    id: UUID
    reference_no: str
    status: InspectionStatus
    product_id: UUID | None = None
    inspector_id: UUID | None = None
    batch_id: UUID | None = None
    note: str | None = None
    is_demo: bool
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None
    finding_counts: FindingCounts | None = None


class InspectionDetailOut(InspectionSummaryOut):
    product: ProductOut | None = None
    packages: list[PackageOut] = []


class CreateInspectionRequest(CamelModel):
    product_name: str = Field(min_length=1, max_length=255)
    product_category: str = Field(min_length=1, max_length=120)
    gtin: str | None = Field(default=None, max_length=64)
    note: str | None = Field(default=None, max_length=2000)
    batch_id: UUID | None = None


class AnalyzeInspectionRequest(CamelModel):
    # Drives version-aware rule selection; defaults to the inspection's date.
    context_date: datetime | None = None
