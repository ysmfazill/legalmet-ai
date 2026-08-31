"""Perception application service (Prompt 4).

Thin orchestration + read layer over the pipeline: starts runs (in the request
transaction), executes them (each in its own background session), and answers
the read queries the Inspection Workspace consumes. It asserts NOTHING about
compliance — the strongest thing it can say is what a run perceived.
"""
from __future__ import annotations

import uuid
from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.enums import ImageQualityGrade, ProcessingRunStatus
from app.core.errors import NotFoundError, ValidationError
from app.models import (
    ExtractedField,
    Image,
    ImageRegion,
    Inspection,
    OcrTextResult,
    Package,
    ProcessingRun,
)
from app.schemas.image import ExtractedFieldOut, ImageRegionOut
from app.schemas.perception import (
    OcrTextResultOut,
    PerceptionAnalysisOut,
    PerceptionImageSummaryOut,
    PerceptionSummaryOut,
    ProcessingRunDetailOut,
    ProcessingRunOut,
)
from app.services.perception.pipeline import PackagePerceptionPipeline

_TERMINAL = {
    ProcessingRunStatus.COMPLETED.value,
    ProcessingRunStatus.PARTIAL.value,
    ProcessingRunStatus.FAILED.value,
    ProcessingRunStatus.REVIEW_REQUIRED.value,
}


class PerceptionService:
    def __init__(
        self,
        *,
        pipeline: PackagePerceptionPipeline,
        session_factory: Callable[[], Session],
    ) -> None:
        self._pipeline = pipeline
        self._session_factory = session_factory

    # --- engine warm-up ---------------------------------------------------------

    def prewarm_ocr(self) -> None:
        """Initialise the OCR engine(s) now so the first request is warm.

        Called at startup (never fatal — see app.main._lifespan). Engines are
        cached per language inside the OCR service, so this simply forces the
        lazy init that the first perception request would otherwise pay.
        """
        prewarm = getattr(self._pipeline, "prewarm_ocr", None)
        if callable(prewarm):
            prewarm()

    # --- mutations (request transaction) --------------------------------------

    def start_for_inspection(
        self, db: Session, *, inspection_id: uuid.UUID, actor_id: uuid.UUID | None
    ) -> list[ProcessingRun]:
        """Create one QUEUED run per usable image. Returns the created runs.

        Images rejected by the intake usability grader are skipped (they are
        not worth analysing); an inspection with no usable image is a 422.

        Duplicate-guard (Prompt 9, Phase 8): an image that already has an
        ACTIVE (non-terminal) run is NOT re-queued — the existing run is
        returned, so a double-click or a repeated perceive request is
        idempotent while processing is underway. A new run is only created
        once every prior run has reached a terminal state.
        """
        inspection = self._inspection(db, inspection_id)
        images = [
            image
            for package in inspection.packages
            for image in package.images
            if image.quality_grade != ImageQualityGrade.REJECTED.value
        ]
        if not images:
            raise ValidationError(
                "Attach at least one usable image before running perception analysis.",
                details={"inspectionId": str(inspection_id)},
            )
        runs: list[ProcessingRun] = []
        for image in images:
            active = self._active_run_for_image(db, image.id)
            if active is not None:
                # Already being processed — do not start a duplicate run.
                runs.append(active)
                continue
            runs.append(
                self._pipeline.create_run(
                    db,
                    image=image,
                    inspection=inspection,
                    actor_id=actor_id,
                    reanalysis=self._has_prior_runs(db, image.id),
                )
            )
        return runs

    def reanalyze_image(
        self, db: Session, *, image_id: uuid.UUID, actor_id: uuid.UUID | None
    ) -> ProcessingRun:
        """Queue a NEW run for one image. Prior runs remain untouched.

        If a run is still ACTIVE for this image, it is returned unchanged —
        re-analysis must wait for the current run to finish (prevents
        uncontrolled duplicate processing from repeated requests).
        """
        active = self._active_run_for_image(db, image_id)
        if active is not None:
            return active
        image = db.get(Image, image_id, options=(selectinload(Image.package),))
        if image is None:
            raise NotFoundError(f"Image not found: {image_id}")
        inspection = db.get(Inspection, image.package.inspection_id)
        return self._pipeline.create_run(
            db,
            image=image,
            inspection=inspection,
            actor_id=actor_id,
            reanalysis=True,
        )

    def execute_runs(self, run_ids: list[uuid.UUID]) -> list[ProcessingRun]:
        """Execute queued runs, each in its own session. Called from a FastAPI
        background task AFTER the 202 response has been assembled."""
        results: list[ProcessingRun] = []
        for run_id in run_ids:
            session = self._session_factory()
            try:
                results.append(self._pipeline.execute_run(session, run_id=run_id))
            finally:
                session.close()
        return results

    # --- reads ------------------------------------------------------------------

    def get_analysis(self, db: Session, inspection_id: uuid.UUID) -> PerceptionAnalysisOut:
        inspection = self._inspection(db, inspection_id)
        latest = self._latest_runs(db, inspection_id)

        images: list[PerceptionImageSummaryOut] = []
        summary = PerceptionSummaryOut()
        active = False
        for package in inspection.packages:
            for image in package.images:
                run = latest.get(image.id)
                ocr_count = region_count = field_count = 0
                if run is not None:
                    ocr_count = self._count(db, OcrTextResult, run.id)
                    region_count = self._count(db, ImageRegion, run.id)
                    field_count = self._count(db, ExtractedField, run.id)
                    if run.status not in _TERMINAL:
                        active = True
                    if run.summary:
                        summary.text_elements += int(run.summary.get("textElements") or 0)
                        summary.visual_regions += int(run.summary.get("visualRegions") or 0)
                        summary.fields_extracted += int(run.summary.get("fieldsExtracted") or 0)
                        summary.low_confidence_items += int(
                            run.summary.get("lowConfidenceItems") or 0
                        )
                        summary.total_processing_ms += int(run.summary.get("durationMs") or 0)
                    if run.ocr_model:
                        summary.ocr_model = (
                            f"{run.ocr_provider}/{run.ocr_model}/{run.ocr_version}"
                        )
                    if run.vision_model:
                        summary.vision_model = (
                            f"{run.vision_provider}/{run.vision_model}/{run.vision_version}"
                        )
                images.append(
                    PerceptionImageSummaryOut(
                        image_id=image.id,
                        image_type=image.image_type,
                        latest_run=ProcessingRunOut.model_validate(run) if run else None,
                        ocr_count=ocr_count,
                        region_count=region_count,
                        field_count=field_count,
                    )
                )
        return PerceptionAnalysisOut(
            inspection_id=inspection_id,
            has_runs=bool(latest),
            active=active,
            summary=summary,
            images=images,
        )

    def list_ocr(self, db: Session, inspection_id: uuid.UUID) -> list[OcrTextResult]:
        run_ids = [r.id for r in self._latest_runs(db, inspection_id).values()]
        return self._for_runs(db, OcrTextResult, run_ids) if run_ids else []

    def list_regions(self, db: Session, inspection_id: uuid.UUID) -> list[ImageRegion]:
        run_ids = [r.id for r in self._latest_runs(db, inspection_id).values()]
        return self._for_runs(db, ImageRegion, run_ids) if run_ids else []

    def list_fields(self, db: Session, inspection_id: uuid.UUID) -> list[ExtractedField]:
        run_ids = [r.id for r in self._latest_runs(db, inspection_id).values()]
        return self._for_runs(db, ExtractedField, run_ids) if run_ids else []

    def list_runs(self, db: Session, inspection_id: uuid.UUID) -> list[ProcessingRun]:
        self._inspection(db, inspection_id)
        stmt = (
            select(ProcessingRun)
            .where(ProcessingRun.inspection_id == inspection_id)
            .order_by(ProcessingRun.created_at.desc())
        )
        return list(db.execute(stmt).scalars().all())

    def get_run(self, db: Session, run_id: uuid.UUID) -> ProcessingRunDetailOut:
        run = db.get(ProcessingRun, run_id)
        if run is None:
            raise NotFoundError(f"Processing run not found: {run_id}")
        ocr = self._for_runs(db, OcrTextResult, [run.id])
        regions = self._for_runs(db, ImageRegion, [run.id])
        fields = self._for_runs(db, ExtractedField, [run.id])
        detail = ProcessingRunDetailOut.model_validate(run)
        detail.ocr_results = [OcrTextResultOut.model_validate(row) for row in ocr]
        detail.regions = [ImageRegionOut.model_validate(row) for row in regions]
        detail.fields = [ExtractedFieldOut.model_validate(row) for row in fields]
        return detail

    # --- internals ----------------------------------------------------------------

    @staticmethod
    def _inspection(db: Session, inspection_id: uuid.UUID) -> Inspection:
        stmt = (
            select(Inspection)
            .where(Inspection.id == inspection_id)
            .options(selectinload(Inspection.packages).selectinload(Package.images))
        )
        inspection = db.execute(stmt).scalar_one_or_none()
        if inspection is None:
            raise NotFoundError(f"Inspection not found: {inspection_id}")
        return inspection

    @staticmethod
    def _latest_runs(db: Session, inspection_id: uuid.UUID) -> dict[uuid.UUID, ProcessingRun]:
        stmt = (
            select(ProcessingRun)
            .where(ProcessingRun.inspection_id == inspection_id)
            .order_by(ProcessingRun.created_at.desc())
        )
        latest: dict[uuid.UUID, ProcessingRun] = {}
        for run in db.execute(stmt).scalars().all():
            if run.image_id not in latest:
                latest[run.image_id] = run
        return latest

    @staticmethod
    def _active_run_for_image(db: Session, image_id: uuid.UUID) -> ProcessingRun | None:
        """The still-running run for an image, if any (duplicate guard)."""
        stmt = (
            select(ProcessingRun)
            .where(ProcessingRun.image_id == image_id)
            .order_by(ProcessingRun.created_at.desc())
        )
        for run in db.execute(stmt).scalars():
            if run.status not in _TERMINAL:
                return run
        return None

    @staticmethod
    def _has_prior_runs(db: Session, image_id: uuid.UUID) -> bool:
        stmt = select(ProcessingRun.id).where(ProcessingRun.image_id == image_id).limit(1)
        return db.execute(stmt).first() is not None

    @staticmethod
    def _for_runs(db: Session, model, run_ids: list[uuid.UUID]) -> list:
        stmt = (
            select(model)
            .where(model.processing_run_id.in_(run_ids))
            .order_by(model.created_at.asc())
        )
        return list(db.execute(stmt).scalars().all())

    @staticmethod
    def _count(db: Session, model, run_id: uuid.UUID) -> int:
        stmt = select(model.id).where(model.processing_run_id == run_id)
        return len(db.execute(stmt).scalars().all())
