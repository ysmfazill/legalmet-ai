"""Extracted declaration fields (perception output).

An ExtractedField says "this region appears to be an MRP with value ₹499 at
confidence 0.82". It is a perception claim, not a legal conclusion. Legal
significance is decided later by the deterministic rule engine.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import ExtractionStatus, FieldType
from app.db.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin


class ExtractedField(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "extracted_fields"

    image_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("images.id", ondelete="CASCADE"), index=True, nullable=False
    )
    image_region_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("image_regions.id", ondelete="SET NULL"), index=True, nullable=True
    )
    package_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("packages.id", ondelete="CASCADE"), index=True, nullable=False
    )
    field_type: Mapped[str] = mapped_column(
        String(32), default=FieldType.OTHER.value, index=True, nullable=False
    )
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_value: Mapped[str | None] = mapped_column(String(255), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    extraction_method: Mapped[str] = mapped_column(String(64), default="mock", nullable=False)
    model_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("model_versions.id", ondelete="SET NULL"), nullable=True
    )
    is_demo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # --- Prompt 4: real perception provenance + evidence linkage ------------
    processing_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("processing_runs.id", ondelete="CASCADE"), index=True, nullable=True
    )
    source_ocr_result_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ocr_text_results.id", ondelete="SET NULL"), index=True, nullable=True
    )
    # Perception outcome of this candidate: DETECTED / REVIEW_REQUIRED /
    # NOT_EXTRACTED. Explicitly NOT a compliance status.
    status: Mapped[str] = mapped_column(
        String(24), default=ExtractionStatus.DETECTED.value, nullable=False
    )
    # --- Human-correction foundation (future Inspector Copilot) -------------
    # Populated only by a human action; the pipeline NEVER writes these. The
    # raw evidence above stays untouched when a correction is recorded.
    corrected_value: Mapped[str | None] = mapped_column(String(255), nullable=True)
    corrected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    image = relationship("Image", back_populates="extracted_fields")
    region = relationship("ImageRegion", back_populates="extracted_fields")
    package = relationship("Package")
    model_version = relationship("ModelVersion")
    source_ocr_result = relationship("OcrTextResult", back_populates="extracted_fields")
