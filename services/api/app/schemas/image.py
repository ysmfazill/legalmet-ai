"""Imaging + extraction schemas."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.core.enums import (
    CaptureSource,
    FieldType,
    ImageProcessingStatus,
    ImageQualityGrade,
    ImageQualityStatus,
    ImageType,
    RegionType,
)
from app.schemas.base import CamelModel


class BoundingBox(CamelModel):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    width: float = Field(ge=0, le=1)
    height: float = Field(ge=0, le=1)


class ImageRegionOut(CamelModel):
    id: UUID
    image_id: UUID
    region_type: RegionType
    bbox: BoundingBox
    confidence: float
    created_at: datetime


class ExtractedFieldOut(CamelModel):
    id: UUID
    image_id: UUID
    image_region_id: UUID | None = None
    package_id: UUID
    field_type: FieldType
    raw_text: str
    normalized_value: str | None = None
    unit: str | None = None
    confidence: float
    extraction_method: str
    model_version_id: UUID | None = None
    is_demo: bool
    created_at: datetime


class ImageOut(CamelModel):
    id: UUID
    package_id: UUID
    storage_key: str
    original_filename: str
    mime_type: str
    width: int | None = None
    height: int | None = None
    file_size: int | None = None
    image_type: ImageType
    quality_score: float | None = None
    quality_status: ImageQualityStatus
    is_demo: bool
    created_at: datetime
    regions: list[ImageRegionOut] = []
    # --- Prompt 3: real intake provenance + preprocessing -----------------
    checksum: str | None = None
    capture_source: CaptureSource = CaptureSource.UPLOAD
    processing_status: ImageProcessingStatus = ImageProcessingStatus.PENDING
    quality_grade: ImageQualityGrade | None = None
    quality_metrics: dict | None = None
    processed_storage_key: str | None = None
    # Retrieval URLs are populated by the router from the storage backend; they
    # are not ORM columns, so they default to None on a bare model_validate.
    url: str | None = None
    processed_url: str | None = None


class CreatePackageRequest(CamelModel):
    label: str | None = Field(default=None, max_length=255)


class BatchUploadError(CamelModel):
    code: str
    message: str


class BatchUploadItemResult(CamelModel):
    filename: str
    status: str  # "UPLOADED" | "REJECTED"
    image: ImageOut | None = None
    error: BatchUploadError | None = None


class BatchUploadResponse(CamelModel):
    items: list[BatchUploadItemResult] = []
    uploaded: int = 0
    rejected: int = 0


class RegisterImageRequest(CamelModel):
    original_filename: str
    mime_type: str
    image_type: ImageType = ImageType.OTHER
    content_base64: str | None = None
    storage_key: str | None = None
    width: int | None = None
    height: int | None = None
    file_size: int | None = None
