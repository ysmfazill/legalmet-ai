"""Images and detected image regions (perception inputs / spatial evidence)."""
from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import (
    CaptureSource,
    ImageProcessingStatus,
    ImageQualityStatus,
    ImageType,
    RegionType,
)
from app.db.base import Base, CreatedAtMixin, JSONType, UUIDPrimaryKeyMixin


class Image(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "images"

    package_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("packages.id", ondelete="CASCADE"), index=True, nullable=False
    )
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(64), nullable=False)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    image_type: Mapped[str] = mapped_column(
        String(16), default=ImageType.OTHER.value, nullable=False
    )
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    quality_status: Mapped[str] = mapped_column(
        String(24), default=ImageQualityStatus.UNKNOWN.value, nullable=False
    )
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # --- Prompt 3: real package intake (provenance + preprocessing) -------
    # SHA-256 hex of the ORIGINAL bytes — provenance + exact-duplicate detection.
    checksum: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    capture_source: Mapped[str] = mapped_column(
        String(16), default=CaptureSource.UPLOAD.value, nullable=False
    )
    processing_status: Mapped[str] = mapped_column(
        String(16), default=ImageProcessingStatus.PENDING.value, nullable=False
    )
    quality_grade: Mapped[str | None] = mapped_column(String(16), nullable=True)
    quality_metrics: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    # Metadata-stripped, resized derivative used for display/analysis. The
    # ORIGINAL is always preserved verbatim under `storage_key`.
    processed_storage_key: Mapped[str | None] = mapped_column(String(512), nullable=True)

    package = relationship("Package", back_populates="images")
    regions = relationship("ImageRegion", back_populates="image", cascade="all, delete-orphan")
    extracted_fields = relationship(
        "ExtractedField", back_populates="image", cascade="all, delete-orphan"
    )


class ImageRegion(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "image_regions"

    image_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("images.id", ondelete="CASCADE"), index=True, nullable=False
    )
    region_type: Mapped[str] = mapped_column(
        String(24), default=RegionType.OTHER.value, nullable=False
    )
    # Normalised bounding box {x, y, width, height} in 0..1 image coordinates.
    bbox: Mapped[dict] = mapped_column(JSONType, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    image = relationship("Image", back_populates="regions")
    extracted_fields = relationship("ExtractedField", back_populates="region")
