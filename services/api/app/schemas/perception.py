"""Perception schemas (Prompt 4).

Serialisation for processing runs, OCR results and the inspection-level
perception analysis. Everything here describes *what the system perceived* —
statuses are perception outcomes (DETECTED / REVIEW_REQUIRED / NOT_EXTRACTED),
never compliance verdicts.
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.core.enums import ProcessingRunStatus
from app.schemas.base import CamelModel
from app.schemas.image import BoundingBox, ExtractedFieldOut, ImageRegionOut


class ProcessingRunOut(CamelModel):
    id: UUID
    reference: str
    inspection_id: UUID
    image_id: UUID
    status: ProcessingRunStatus
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_ms: int | None = None
    ocr_provider: str | None = None
    ocr_model: str | None = None
    ocr_version: str | None = None
    vision_provider: str | None = None
    vision_model: str | None = None
    vision_version: str | None = None
    pipeline_version: str
    configuration: dict | None = None
    summary: dict | None = None
    error: dict | None = None
    is_demo: bool
    created_at: datetime


class OcrTextResultOut(CamelModel):
    id: UUID
    image_id: UUID
    processing_run_id: UUID
    region_id: UUID | None = None
    # Raw engine output — immutable evidence.
    raw_text: str
    # Derived tidy-up; the raw text above is never modified.
    normalized_text: str | None = None
    bbox: BoundingBox
    # The OCR engine's own recognition confidence (OCR confidence — not legal
    # confidence).
    confidence: float
    language: str | None = None
    provider: str
    model_name: str
    model_version: str
    created_at: datetime


class PerceptionKickoffRun(CamelModel):
    """One queued run in the 202 response of a perception request."""

    run_id: UUID
    reference: str
    image_id: UUID


class PerceptionKickoffOut(CamelModel):
    inspection_id: UUID
    status: str = "QUEUED"
    runs: list[PerceptionKickoffRun] = []
    note: str = (
        "Perception analysis queued. Poll GET /inspections/{id}/analysis for "
        "stage updates. This produces perception evidence only — no compliance "
        "evaluation is performed at this stage."
    )


class PerceptionImageSummaryOut(CamelModel):
    image_id: UUID
    image_type: str
    latest_run: ProcessingRunOut | None = None
    ocr_count: int = 0
    region_count: int = 0
    field_count: int = 0


class PerceptionSummaryOut(CamelModel):
    """Counts over the LATEST run of every image. Perception metrics only."""

    text_elements: int = 0
    visual_regions: int = 0
    fields_extracted: int = 0
    low_confidence_items: int = 0
    total_processing_ms: int = 0
    ocr_model: str | None = None
    vision_model: str | None = None


class PerceptionAnalysisOut(CamelModel):
    inspection_id: UUID
    has_runs: bool = False
    # True while any latest run is still in a non-terminal stage — the frontend
    # polls while this is set.
    active: bool = False
    summary: PerceptionSummaryOut = Field(default_factory=PerceptionSummaryOut)
    images: list[PerceptionImageSummaryOut] = []
    regulatory_evaluation: str = "AWAITING_REGULATORY_EVALUATION"


class ProcessingRunDetailOut(ProcessingRunOut):
    """Run detail including the evidence produced by that exact run."""

    ocr_results: list[OcrTextResultOut] = []
    regions: list[ImageRegionOut] = []
    fields: list[ExtractedFieldOut] = []
