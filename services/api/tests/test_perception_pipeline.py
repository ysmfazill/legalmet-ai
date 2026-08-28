"""Pipeline + service tests for package perception (Prompt 4).

Runs the REAL pipeline (preprocessing, evidence linkage, model-version
recording, run lifecycle, audit) against the in-memory database and the real
local storage backend — but with FAKE OCR / vision providers so no AI model is
ever downloaded or executed here. The real-engine path is covered by
``tests/test_perception_integration.py`` (marked ``integration``).

Guardrails asserted throughout:
* raw OCR text is preserved verbatim; normalization is a derived column;
* an OCR failure fails the run; a vision failure degrades to PARTIAL and
  keeps every OCR-derived evidence row;
* reanalysis creates a NEW run and never destroys prior runs;
* nothing anywhere produces a compliance verdict.
"""
from __future__ import annotations

import uuid
from io import BytesIO

import pytest
from PIL import Image, ImageDraw
from sqlalchemy import select

from app.core.enums import (
    AuditEventType,
    ExtractionStatus,
    FieldType,
    ModelServiceType,
    ProcessingRunStatus,
    RegionType,
)
from app.core.errors import ServiceUnavailableError, ValidationError
from app.models import (
    AuditEvent,
    ExtractedField,
    ImageRegion,
    Inspection,
    ModelVersion,
    OcrTextResult,
    Package,
)
from app.models import (
    Image as ImageModel,
)
from app.services.interfaces import (
    BBox,
    DetectedRegion,
    OcrLine,
    OcrResult,
    OCRService,
    ServiceDescriptor,
    VisionRegionsResult,
    VisionService,
)
from app.services.registry import Services

# --- fakes ---------------------------------------------------------------------


def _descriptor(service_type, name):
    return ServiceDescriptor(
        service_type=service_type, name=name, version="1.0.0", provider="fake"
    )


class FakeOCRService(OCRService):
    """Deterministic fake: always the same label lines, real bytes required."""

    def __init__(self) -> None:
        self.calls: list[bytes] = []

    @property
    def descriptor(self) -> ServiceDescriptor:
        return _descriptor(ModelServiceType.OCR, "fake-ocr")

    def extract_text(self, *, image_bytes, storage_key, seed) -> OcrResult:
        assert image_bytes, "pipeline must feed the OCR engine real (derivative) bytes"
        self.calls.append(image_bytes)
        lines = [
            OcrLine(
                text="SUNRISE CRUNCHY MASALA",
                bbox=BBox(0.1, 0.05, 0.7, 0.09),
                confidence=0.98,
            ),
            OcrLine(
                text="M.R.P. ₹ 499.00 (incl. of all taxes)",
                bbox=BBox(0.1, 0.2, 0.6, 0.05),
                confidence=0.97,
            ),
            OcrLine(text="Net Qty: 500 g", bbox=BBox(0.1, 0.3, 0.4, 0.05), confidence=0.96),
            OcrLine(
                text="Mfg Date: 03/2026", bbox=BBox(0.1, 0.4, 0.3, 0.05), confidence=0.94
            ),
            # Low OCR confidence on purpose -> REVIEW_REQUIRED path.
            OcrLine(
                text="Batch No: DMO-2231", bbox=BBox(0.1, 0.5, 0.4, 0.05), confidence=0.45
            ),
        ]
        mean = round(sum(line.confidence for line in lines) / len(lines), 3)
        return OcrResult(
            lines=lines, mean_confidence=mean, descriptor=self.descriptor, width=1200, height=1600
        )


class FailingOCRService(OCRService):
    @property
    def descriptor(self) -> ServiceDescriptor:
        return _descriptor(ModelServiceType.OCR, "failing-ocr")

    def extract_text(self, *, image_bytes, storage_key, seed) -> OcrResult:
        raise ServiceUnavailableError("Perception model unavailable (fake failure).")


class FakeVisionService(VisionService):
    """Deterministic fake: one decoded QR code + one barcode region."""

    def __init__(self) -> None:
        self.calls: list[bytes] = []

    @property
    def descriptor(self) -> ServiceDescriptor:
        return _descriptor(ModelServiceType.VISION, "fake-vision")

    def detect_regions(self, *, image_bytes, storage_key, seed) -> VisionRegionsResult:
        assert image_bytes
        self.calls.append(image_bytes)
        return VisionRegionsResult(
            regions=[
                DetectedRegion(
                    region_type=RegionType.QR_CODE,
                    bbox=BBox(0.6, 0.8, 0.2, 0.2),
                    confidence=1.0,
                    payload={"symbology": "QR", "value": "HELLO LEGALMET 123", "decoded": True},
                ),
                DetectedRegion(
                    region_type=RegionType.BARCODE,
                    bbox=BBox(0.1, 0.8, 0.35, 0.1),
                    confidence=1.0,
                    payload={"symbology": "EAN_13", "value": "8901234123457", "decoded": True},
                ),
            ],
            descriptor=self.descriptor,
        )

    def detect_fields(self, *, ocr, regions, profile, seed):
        return []  # field extraction lives in the FieldExtractionProvider seam


class FailingVisionService(VisionService):
    @property
    def descriptor(self) -> ServiceDescriptor:
        return _descriptor(ModelServiceType.VISION, "failing-vision")

    def detect_regions(self, *, image_bytes, storage_key, seed) -> VisionRegionsResult:
        raise RuntimeError("vision boom")

    def detect_fields(self, *, ocr, regions, profile, seed):
        return []


# --- fixtures ------------------------------------------------------------------


def _label_png() -> bytes:
    """A real, decodable PNG (the preprocessor must be able to process it)."""
    img = Image.new("RGB", (800, 600), (245, 245, 245))
    draw = ImageDraw.Draw(img)
    draw.rectangle([20, 20, 780, 580], outline=(0, 0, 0), width=4)
    draw.text((60, 60), "SUNRISE MASALA", fill=(0, 0, 0))
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture()
def inspection_with_image(db, services: Services):
    """An inspection + package + one stored, usable image (no API involved)."""
    inspection = Inspection(
        reference_no=f"INS-T-{uuid.uuid4().hex[:8].upper()}",
        is_demo=False,
    )
    db.add(inspection)
    db.flush()
    package = Package(inspection_id=inspection.id, label="Package 1")
    db.add(package)
    db.flush()
    storage_key = f"inspections/{inspection.id}/{uuid.uuid4().hex}.png"
    data = _label_png()
    services.storage.save(key=storage_key, data=data, content_type="image/png")
    image = ImageModel(
        package_id=package.id,
        storage_key=storage_key,
        original_filename="front.png",
        mime_type="image/png",
        width=800,
        height=600,
        file_size=len(data),
        image_type="FRONT",
        quality_grade="ACCEPTABLE",
        checksum="deadbeef" * 8,
        is_demo=False,
    )
    db.add(image)
    db.commit()
    db.refresh(image)
    db.refresh(inspection)
    return inspection, image


@pytest.fixture()
def pipeline(services: Services):
    """The registry-built pipeline with providers swapped for fakes."""
    pipeline = services.perception._pipeline
    original_ocr, original_vision = pipeline._ocr, pipeline._vision
    pipeline._ocr = FakeOCRService()
    pipeline._vision = FakeVisionService()
    yield pipeline
    pipeline._ocr, pipeline._vision = original_ocr, original_vision


def _run_pipeline(pipeline, db, inspection, image, *, reanalysis=False):
    run = pipeline.create_run(db, image=image, inspection=inspection, actor_id=None,
                              reanalysis=reanalysis)
    return pipeline.execute_run(db, run_id=run.id)


# --- happy path ---------------------------------------------------------------


class TestPipelineSuccess:
    def test_run_lifecycle_and_evidence(self, db, services, inspection_with_image, pipeline):
        inspection, image = inspection_with_image
        run = _run_pipeline(pipeline, db, inspection, image)

        assert run.reference.startswith("PR-")
        assert run.status in (
            ProcessingRunStatus.REVIEW_REQUIRED.value,
            ProcessingRunStatus.COMPLETED.value,
        )  # Batch line has low OCR confidence -> REVIEW_REQUIRED expected
        assert run.status == ProcessingRunStatus.REVIEW_REQUIRED.value
        assert run.started_at is not None
        assert run.completed_at is not None
        assert run.duration_ms is not None
        assert run.pipeline_version == "4.0.0"
        assert run.is_demo is False
        assert run.ocr_provider == "fake"
        assert run.ocr_model == "fake-ocr"
        assert run.vision_model == "fake-vision"

        # --- OCR evidence: raw verbatim, normalization derived -------------
        ocr_rows = list(
            db.execute(
                select(OcrTextResult).where(OcrTextResult.processing_run_id == run.id)
            ).scalars()
        )
        assert len(ocr_rows) == 5
        by_raw = {row.raw_text: row for row in ocr_rows}
        assert "M.R.P. ₹ 499.00 (incl. of all taxes)" in by_raw  # verbatim, ₹-space intact
        assert by_raw["M.R.P. ₹ 499.00 (incl. of all taxes)"].normalized_text == (
            "M.R.P. ₹499.00 (incl. of all taxes)"
        )
        for row in ocr_rows:
            assert row.provider == "fake"
            assert row.model_name == "fake-ocr"
            assert row.region_id is not None  # every OCR line owns a TEXT_LINE region
            bbox = row.bbox
            assert 0.0 <= bbox["x"] <= 1.0 and 0.0 <= bbox["y"] <= 1.0

        # --- regions: 5 text lines + QR + barcode --------------------------
        regions = list(
            db.execute(
                select(ImageRegion).where(ImageRegion.processing_run_id == run.id)
            ).scalars()
        )
        text_regions = [r for r in regions if r.region_type == RegionType.TEXT_LINE.value]
        qr_regions = [r for r in regions if r.region_type == RegionType.QR_CODE.value]
        barcodes = [r for r in regions if r.region_type == RegionType.BARCODE.value]
        assert len(text_regions) == 5
        assert len(qr_regions) == 1
        assert qr_regions[0].payload == {
            "symbology": "QR",
            "value": "HELLO LEGALMET 123",
            "decoded": True,
        }
        assert len(barcodes) == 1
        assert barcodes[0].payload["symbology"] == "EAN_13"
        assert barcodes[0].payload["value"] == "8901234123457"

        # --- fields: deterministic extraction with status + provenance ------
        fields = list(
            db.execute(
                select(ExtractedField).where(ExtractedField.processing_run_id == run.id)
            ).scalars()
        )
        by_type = {f.field_type: f for f in fields}
        assert by_type[FieldType.MRP.value].normalized_value == "₹499.00"
        assert by_type[FieldType.MRP.value].status == ExtractionStatus.DETECTED.value
        assert by_type[FieldType.NET_QUANTITY.value].normalized_value == "500 g"
        assert by_type[FieldType.DATE_OF_MANUFACTURE.value].normalized_value == "03/2026"
        # Low OCR confidence (0.45 x 0.95) -> REVIEW_REQUIRED, never asserted.
        batch = by_type[FieldType.BATCH_NUMBER.value]
        assert batch.status == ExtractionStatus.REVIEW_REQUIRED.value
        # Typography heuristic -> always review.
        product_name = by_type[FieldType.PRODUCT_NAME.value]
        assert product_name.status == ExtractionStatus.REVIEW_REQUIRED.value
        assert by_type[FieldType.PRODUCT_NAME.value].extraction_method == "heuristic:typography"
        for field in fields:
            assert field.processing_run_id == run.id
            assert field.source_ocr_result_id is not None
            assert field.is_demo is False
            assert field.model_version_id is not None

        # --- model versions recorded for provenance ------------------------
        mv_names = {
            mv.name
            for mv in db.execute(select(ModelVersion)).scalars()
        }
        assert {"fake-ocr", "fake-vision", "deterministic-regex"} <= mv_names

        # --- configuration + summary ---------------------------------------
        assert run.configuration["ocrDerivativeStorageKey"].startswith(
            f"inspections/{inspection.id}/ocr/"
        )
        assert run.configuration["preprocessing"]["operations"]
        assert run.configuration["originalChecksum"] == "deadbeef" * 8
        assert run.summary["textElements"] == 5
        assert run.summary["visualRegions"] == 7
        assert run.summary["lowConfidenceItems"] >= 1
        assert run.error is None

        # The OCR engine actually received the preprocessed derivative bytes.
        assert pipeline._ocr.calls and pipeline._ocr.calls[0] != _label_png()

    def test_audit_trail(self, db, services, inspection_with_image, pipeline):
        inspection, image = inspection_with_image
        run = _run_pipeline(pipeline, db, inspection, image)
        events = list(
            db.execute(
                select(AuditEvent).where(AuditEvent.inspection_id == inspection.id)
            ).scalars()
        )
        types = {e.event_type for e in events}
        assert AuditEventType.PERCEPTION_STARTED.value in types
        assert AuditEventType.PERCEPTION_COMPLETED.value in types
        started = next(
            e for e in events if e.event_type == AuditEventType.PERCEPTION_STARTED.value
        )
        assert started.payload["processingRunRef"] == run.reference


# --- failure paths ------------------------------------------------------------


class TestPipelineFailures:
    def test_ocr_failure_fails_the_run(self, db, services, inspection_with_image, pipeline):
        inspection, image = inspection_with_image
        pipeline._ocr = FailingOCRService()
        run = _run_pipeline(pipeline, db, inspection, image)

        assert run.status == ProcessingRunStatus.FAILED.value
        assert run.error["code"] == "AI_SERVICE_UNAVAILABLE"
        assert run.error["stage"] == ProcessingRunStatus.OCR_PROCESSING.value
        assert run.completed_at is not None
        # No partial evidence was persisted for the failed run.
        assert (
            db.execute(
                select(OcrTextResult).where(OcrTextResult.processing_run_id == run.id)
            ).first()
            is None
        )

    def test_vision_failure_degrades_to_partial(
        self, db, services, inspection_with_image, pipeline
    ):
        inspection, image = inspection_with_image
        pipeline._vision = FailingVisionService()
        run = _run_pipeline(pipeline, db, inspection, image)

        assert run.status == ProcessingRunStatus.PARTIAL.value
        assert run.error["code"] == "VISION_STAGE_FAILED"
        # Successful OCR evidence is NEVER discarded.
        ocr_count = len(
            list(
                db.execute(
                    select(OcrTextResult).where(OcrTextResult.processing_run_id == run.id)
                ).scalars()
            )
        )
        assert ocr_count == 5
        assert run.ocr_model == "fake-ocr"
        assert run.vision_model is None

    def test_unexpected_error_is_sanitised(self, db, services, inspection_with_image, pipeline):
        inspection, image = inspection_with_image

        class ExplodingOCR(FailingOCRService):
            def extract_text(self, *, image_bytes, storage_key, seed):
                raise RuntimeError("secret path C:\\Users\\x\\model.pdparams")

        pipeline._ocr = ExplodingOCR()
        run = _run_pipeline(pipeline, db, inspection, image)
        assert run.status == ProcessingRunStatus.FAILED.value
        assert run.error["code"] == "INTERNAL_ERROR"
        # The internal exception detail (paths, model files) must not leak.
        assert "secret" not in str(run.error)


# --- reanalysis + service layer ------------------------------------------------


class TestPerceptionService:
    def test_reanalysis_preserves_history(self, db, services, inspection_with_image, pipeline):
        inspection, image = inspection_with_image
        first = _run_pipeline(pipeline, db, inspection, image)
        second = _run_pipeline(pipeline, db, inspection, image, reanalysis=True)

        assert second.id != first.id
        runs = services.perception.list_runs(db, inspection.id)
        assert len(runs) == 2

        # The FIRST run's evidence is intact.
        detail = services.perception.get_run(db, first.id)
        assert len(detail.ocr_results) == 5
        assert detail.regions
        assert detail.fields

        # Latest-run reads see only the second run.
        latest = services.perception._latest_runs(db, inspection.id)
        assert latest[image.id].id == second.id
        assert len(services.perception.list_ocr(db, inspection.id)) == 5

        # Reanalysis is auditable.
        events = list(
            db.execute(
                select(AuditEvent).where(AuditEvent.inspection_id == inspection.id)
            ).scalars()
        )
        assert any(e.event_type == AuditEventType.IMAGE_REANALYZED.value for e in events)

    def test_start_skips_rejected_images(self, db, services, inspection_with_image, pipeline):
        inspection, image = inspection_with_image
        image.quality_grade = "REJECTED"
        db.commit()

        with pytest.raises(ValidationError):
            services.perception.start_for_inspection(db, inspection_id=inspection.id, actor_id=None)

    def test_analysis_aggregates_latest_runs(self, db, services, inspection_with_image, pipeline):
        inspection, image = inspection_with_image
        _run_pipeline(pipeline, db, inspection, image)

        analysis = services.perception.get_analysis(db, inspection.id)
        assert analysis.has_runs is True
        assert analysis.active is False  # terminal status
        assert analysis.summary.text_elements == 5
        assert analysis.summary.fields_extracted >= 4
        assert analysis.summary.ocr_model == "fake/fake-ocr/1.0.0"
        assert analysis.summary.vision_model == "fake/fake-vision/1.0.0"
        # Perception answers "what did we see" — never compliance.
        assert analysis.regulatory_evaluation == "AWAITING_REGULATORY_EVALUATION"
        assert len(analysis.images) == 1
        assert analysis.images[0].field_count >= 4

    def test_execute_runs_uses_its_own_session(
        self, db, session_factory, services, inspection_with_image, pipeline
    ):
        inspection, image = inspection_with_image
        run = pipeline.create_run(db, image=image, inspection=inspection, actor_id=None)
        results = services.perception.execute_runs([run.id])
        assert results[0].status in (
            ProcessingRunStatus.COMPLETED.value,
            ProcessingRunStatus.REVIEW_REQUIRED.value,
        )
