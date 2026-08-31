"""Package perception pipeline (Prompt 4).

One auditable execution over ONE image:

    load original -> validate/decode -> OCR derivative -> processing run
    -> real OCR -> OCR rows -> vision regions -> normalize -> deterministic
    field extraction -> evidence linkage -> model versions -> summary
    -> COMPLETED / PARTIAL / REVIEW_REQUIRED / FAILED

Design rules
------------
* The ORIGINAL image is never modified; the OCR derivative is stored
  separately and recorded in the run configuration.
* Raw OCR text is stored verbatim; normalization is a derived column.
* A failing vision stage degrades the run to PARTIAL — successful OCR evidence
  is never discarded.
* A failing OCR stage fails the run (no text => no downstream perception).
* Re-analysis ALWAYS creates a new run; prior runs remain as history.
* NOTHING here evaluates regulatory requirements or compliance.
"""
from __future__ import annotations

import uuid

from sqlalchemy.orm import Session, selectinload

from app.core.config import Settings
from app.core.enums import (
    AuditEventType,
    ExtractionStatus,
    ProcessingRunStatus,
    RegionType,
)
from app.core.errors import AppError, NotFoundError
from app.core.logging import get_logger
from app.db.base import utcnow
from app.models import (
    ExtractedField,
    Image,
    ImageRegion,
    Inspection,
    OcrTextResult,
    ProcessingRun,
)
from app.services.audit.service import AuditService
from app.services.interfaces import (
    FieldExtractionProvider,
    ImagePreprocessor,
    OCRService,
    VisionService,
)
from app.services.perception.normalize import normalize_ocr_text
from app.services.provenance import resolve_model_version
from app.services.storage.base import StorageService

logger = get_logger(__name__)


class PackagePerceptionPipeline:
    PIPELINE_VERSION = "4.0.0"

    def __init__(
        self,
        *,
        settings: Settings,
        storage: StorageService,
        ocr: OCRService,
        vision: VisionService,
        preprocessor: ImagePreprocessor,
        extractor: FieldExtractionProvider,
        audit: AuditService,
    ) -> None:
        self._settings = settings
        self._storage = storage
        self._ocr = ocr
        self._vision = vision
        self._preprocessor = preprocessor
        self._extractor = extractor
        self._audit = audit

    # --- engine warm-up ---------------------------------------------------------

    def prewarm_ocr(self) -> None:
        """Initialise the OCR engine(s) now (startup warm-up, never fatal here —
        the caller in app.main logs and continues). Keeps the first live
        perception request free of engine-init latency."""
        warm = getattr(self._ocr, "prewarm", None)
        if callable(warm):
            warm()

    # --- run creation (called in the request transaction) ---------------------

    def create_run(
        self,
        db: Session,
        *,
        image: Image,
        inspection: Inspection,
        actor_id: uuid.UUID | None,
        reanalysis: bool = False,
    ) -> ProcessingRun:
        """Register a QUEUED run for one image (committed immediately)."""
        run = ProcessingRun(
            reference=_run_reference(),
            inspection_id=inspection.id,
            image_id=image.id,
            status=ProcessingRunStatus.QUEUED.value,
            pipeline_version=self.PIPELINE_VERSION,
            configuration=self._run_configuration(),
            is_demo=False,
        )
        db.add(run)
        db.flush()
        if reanalysis:
            self._audit.record(
                db,
                event_type=AuditEventType.IMAGE_REANALYZED,
                entity_type="image",
                entity_id=image.id,
                actor_id=actor_id,
                inspection_id=inspection.id,
                payload={"processingRunRef": run.reference},
            )
        self._audit.record(
            db,
            event_type=AuditEventType.PERCEPTION_STARTED,
            entity_type="processing_run",
            entity_id=run.id,
            actor_id=actor_id,
            inspection_id=inspection.id,
            payload={"processingRunRef": run.reference, "imageId": str(image.id)},
        )
        db.commit()
        db.refresh(run)
        return run

    # --- execution (runs in a background task / its own session) --------------

    def execute_run(self, db: Session, *, run_id: uuid.UUID) -> ProcessingRun:
        run = db.get(
            ProcessingRun,
            run_id,
            options=(selectinload(ProcessingRun.image).selectinload(Image.package),),
        )
        if run is None:
            raise NotFoundError(f"Processing run not found: {run_id}")
        image = run.image
        inspection_id = run.inspection_id

        run.started_at = utcnow()
        stage = ProcessingRunStatus.PREPROCESSING.value
        try:
            stage = self._set_status(db, run, ProcessingRunStatus.PREPROCESSING)
            original = self._storage.read(key=image.storage_key)
            prep = self._preprocessor.prepare(image_bytes=original)
            derivative_key = f"inspections/{inspection_id}/ocr/{uuid.uuid4().hex}.png"
            self._storage.save(key=derivative_key, data=prep.data, content_type="image/png")
            configuration = dict(run.configuration or {})
            configuration["ocrDerivativeStorageKey"] = derivative_key
            configuration["preprocessing"] = {
                "preprocessor": f"{self._preprocessor.name}/{self._preprocessor.version}",
                "width": prep.width,
                "height": prep.height,
                "operations": prep.operations,
            }
            if image.checksum:
                configuration["originalChecksum"] = image.checksum
            run.configuration = configuration

            # ---- OCR (fatal on failure) ----
            stage = self._set_status(db, run, ProcessingRunStatus.OCR_PROCESSING)
            ocr_result = self._ocr.extract_text(
                image_bytes=prep.data, storage_key=derivative_key, seed=derivative_key
            )
            ocr_descriptor = ocr_result.descriptor
            resolve_model_version(db, ocr_descriptor)  # registers provenance row
            run.ocr_provider = ocr_descriptor.provider
            run.ocr_model = ocr_descriptor.name
            run.ocr_version = ocr_descriptor.version

            ocr_rows: list[OcrTextResult] = []
            for line in ocr_result.lines:
                region = ImageRegion(
                    image_id=image.id,
                    processing_run_id=run.id,
                    region_type=RegionType.TEXT_LINE.value,
                    bbox=line.bbox.as_dict(),
                    confidence=line.confidence,
                )
                db.add(region)
                db.flush()
                ocr_row = OcrTextResult(
                    image_id=image.id,
                    processing_run_id=run.id,
                    region_id=region.id,
                    raw_text=line.text,
                    normalized_text=normalize_ocr_text(line.text),
                    bbox=line.bbox.as_dict(),
                    confidence=line.confidence,
                    language=line.language,
                    provider=ocr_descriptor.provider,
                    model_name=ocr_descriptor.name,
                    model_version=ocr_descriptor.version,
                )
                db.add(ocr_row)
                ocr_rows.append(ocr_row)
            db.flush()

            # ---- Vision (non-fatal on failure) ----
            stage = self._set_status(db, run, ProcessingRunStatus.VISION_PROCESSING)
            vision_failed_reason: str | None = None
            try:
                vision_result = self._vision.detect_regions(
                    image_bytes=prep.data, storage_key=derivative_key, seed=derivative_key
                )
                vision_descriptor = vision_result.descriptor
                resolve_model_version(db, vision_descriptor)
                run.vision_provider = vision_descriptor.provider
                run.vision_model = vision_descriptor.name
                run.vision_version = vision_descriptor.version
                for detected in vision_result.regions:
                    db.add(
                        ImageRegion(
                            image_id=image.id,
                            processing_run_id=run.id,
                            region_type=detected.region_type.value,
                            bbox=detected.bbox.as_dict(),
                            confidence=detected.confidence,
                            payload=detected.payload,
                        )
                    )
                db.flush()
            except AppError as exc:
                vision_failed_reason = f"{exc.code.value}: {exc.message}"
            except Exception as exc:  # noqa: BLE001 — perception must degrade, not crash
                vision_failed_reason = f"{type(exc).__name__}: {exc}"

            # ---- Field extraction ----
            stage = self._set_status(db, run, ProcessingRunStatus.FIELD_EXTRACTION)
            extractor_descriptor = self._extractor.descriptor
            extractor_mv = resolve_model_version(db, extractor_descriptor)
            candidates = self._extractor.extract(ocr=ocr_result)
            field_count = 0
            low_confidence = 0
            for candidate in candidates:
                source_row = (
                    ocr_rows[candidate.source_index]
                    if candidate.source_index is not None
                    and candidate.source_index < len(ocr_rows)
                    else None
                )
                db.add(
                    ExtractedField(
                        image_id=image.id,
                        image_region_id=source_row.region_id if source_row else None,
                        package_id=image.package_id,
                        field_type=candidate.field_type.value,
                        raw_text=candidate.raw_text,
                        normalized_value=candidate.normalized_value,
                        unit=candidate.unit,
                        confidence=candidate.confidence,
                        extraction_method=candidate.method or "deterministic",
                        model_version_id=extractor_mv.id,
                        processing_run_id=run.id,
                        source_ocr_result_id=source_row.id if source_row else None,
                        status=candidate.status.value,
                        is_demo=False,
                    )
                )
                if candidate.status != ExtractionStatus.NOT_EXTRACTED:
                    field_count += 1
                if candidate.status == ExtractionStatus.REVIEW_REQUIRED:
                    low_confidence += 1
            db.flush()

            # ---- Summary + terminal status ----
            region_count = (
                db.query(ImageRegion)
                .filter(ImageRegion.processing_run_id == run.id)
                .count()
            )
            completed_at = utcnow()
            run.completed_at = completed_at
            run.duration_ms = int(
                (completed_at - run.started_at).total_seconds() * 1000
            ) if run.started_at else None
            run.summary = {
                "textElements": len(ocr_rows),
                "visualRegions": region_count,
                "fieldsExtracted": field_count,
                "lowConfidenceItems": low_confidence,
                "durationMs": run.duration_ms,
                "model": (
                    f"{ocr_descriptor.provider}/{ocr_descriptor.name}/{ocr_descriptor.version}"
                ),
                "visionModel": (
                    f"{run.vision_provider}/{run.vision_model}/{run.vision_version}"
                    if run.vision_provider
                    else None
                ),
            }
            if vision_failed_reason:
                run.status = ProcessingRunStatus.PARTIAL.value
                run.error = {"code": "VISION_STAGE_FAILED", "message": vision_failed_reason}
            elif low_confidence > 0:
                run.status = ProcessingRunStatus.REVIEW_REQUIRED.value
            else:
                run.status = ProcessingRunStatus.COMPLETED.value

            self._audit.record(
                db,
                event_type=AuditEventType.PERCEPTION_COMPLETED,
                entity_type="processing_run",
                entity_id=run.id,
                actor_id=None,
                inspection_id=inspection_id,
                payload={
                    "processingRunRef": run.reference,
                    "status": run.status,
                    "textElements": len(ocr_rows),
                    "visualRegions": region_count,
                    "fieldsExtracted": field_count,
                    "lowConfidenceItems": low_confidence,
                },
            )
            db.commit()
        except AppError as exc:
            self._fail(db, run, stage, exc.code.value, exc.message)
        except MemoryError:
            self._fail(db, run, stage, "MEMORY_ERROR", "OCR/vision inference exhausted memory.")
        except Exception as exc:  # noqa: BLE001 — surface as a failed run, never a 500 leak
            logger.error(
                "perception_run_failed",
                processing_run=str(run.id),
                stage=stage,
                error=str(exc),
                error_type=type(exc).__name__,
            )
            self._fail(db, run, stage, "INTERNAL_ERROR", "Unexpected perception failure.")
        db.refresh(run)
        return run

    # --- internals -------------------------------------------------------------

    def _run_configuration(self) -> dict:
        return {
            "pipelineVersion": self.PIPELINE_VERSION,
            "preprocessor": f"{self._preprocessor.name}/{self._preprocessor.version}",
            "fieldExtractor": (
                f"{self._extractor.descriptor.provider}/{self._extractor.descriptor.name}/"
                f"{self._extractor.descriptor.version}"
            ),
            "reviewThreshold": getattr(self._extractor, "review_threshold", None),
        }

    @staticmethod
    def _set_status(db: Session, run: ProcessingRun, status: ProcessingRunStatus) -> str:
        run.status = status.value
        db.commit()
        return status.value

    def _fail(
        self, db: Session, run: ProcessingRun, stage: str, code: str, message: str
    ) -> None:
        completed_at = utcnow()
        run.status = ProcessingRunStatus.FAILED.value
        run.completed_at = completed_at
        run.duration_ms = (
            int((completed_at - run.started_at).total_seconds() * 1000)
            if run.started_at
            else None
        )
        run.error = {"code": code, "message": message, "stage": stage}
        self._audit.record(
            db,
            event_type=AuditEventType.PERCEPTION_FAILED,
            entity_type="processing_run",
            entity_id=run.id,
            actor_id=None,
            inspection_id=run.inspection_id,
            payload={"processingRunRef": run.reference, "code": code, "stage": stage},
        )
        db.commit()


def _run_reference() -> str:
    return f"PR-{uuid.uuid4().hex[:8].upper()}"
