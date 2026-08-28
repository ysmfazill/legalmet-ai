"""Perception provenance models (Prompt 4).

A :class:`ProcessingRun` is one auditable execution of the perception pipeline
over ONE image: which providers/models/versions ran, what configuration was
used, how long it took, and what failed. Re-analysis always creates a NEW run —
runs are append-only history, never overwritten.

An :class:`OcrTextResult` is one raw OCR line with its bounding box and the
engine's own confidence. ``raw_text`` is immutable evidence;
``normalized_text`` is derived (whitespace/currency tidy-up) and never replaces
the raw value.

Both are perception records: they describe *what the system saw*, never whether
it was legally sufficient. That judgement belongs to the (later) rule layer.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import ProcessingRunStatus
from app.db.base import Base, CreatedAtMixin, JSONType, UUIDPrimaryKeyMixin


class ProcessingRun(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "processing_runs"

    # Human-friendly audit reference, e.g. PR-1A2B3C4D.
    reference: Mapped[str] = mapped_column(String(16), unique=True, index=True, nullable=False)
    inspection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("inspections.id", ondelete="CASCADE"), index=True, nullable=False
    )
    image_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("images.id", ondelete="CASCADE"), index=True, nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(24), default=ProcessingRunStatus.QUEUED.value, index=True, nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Provider/model provenance (denormalised for auditability even if the
    # ModelVersion row is later retired).
    ocr_provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ocr_model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    ocr_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    vision_provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    vision_model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    vision_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    pipeline_version: Mapped[str] = mapped_column(String(32), nullable=False)

    configuration: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    summary: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    error: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    inspection = relationship("Inspection")
    image = relationship("Image", back_populates="processing_runs")
    ocr_results = relationship(
        "OcrTextResult", back_populates="processing_run", cascade="all, delete-orphan"
    )


class OcrTextResult(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "ocr_text_results"

    image_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("images.id", ondelete="CASCADE"), index=True, nullable=False
    )
    processing_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("processing_runs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # The TEXT_LINE region this line was read from — the first link of the
    # evidence chain IMAGE -> REGION -> OCR -> FIELD.
    region_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("image_regions.id", ondelete="SET NULL"), index=True, nullable=True
    )
    # Raw engine output — immutable evidence. Normalisation is derived, below.
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Normalised bounding box {x, y, width, height} in 0..1 image coordinates,
    # relative to the ORIGINAL (post-EXIF-orientation) image frame.
    bbox: Mapped[dict] = mapped_column(JSONType, nullable=False)
    # The OCR engine's own recognition confidence. OCR CONFIDENCE — not legal
    # confidence, never used as a compliance signal on its own.
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    language: Mapped[str | None] = mapped_column(String(16), nullable=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model_name: Mapped[str] = mapped_column(String(120), nullable=False)
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)

    image = relationship("Image", back_populates="ocr_results")
    processing_run = relationship("ProcessingRun", back_populates="ocr_results")
    region = relationship("ImageRegion", back_populates="ocr_results")
    # Plain back-populates (ExtractedField is cascade-owned by the Image).
    extracted_fields = relationship("ExtractedField", back_populates="source_ocr_result")
