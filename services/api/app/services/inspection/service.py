"""Inspection service — the orchestrator.

This is the conductor that turns an inspection into evidence-backed findings by
composing the pluggable services in the correct order, while keeping the
critical separation intact:

    perception (mock OCR / vision / product understanding)  -> observations
    regulatory service (version-aware)                      -> applicable rules
    deterministic rule engine                               -> findings
    evidence service                                        -> traceability
    audit service                                           -> provenance

The orchestrator NEVER decides compliance itself and never invents rules — it
only wires verified rule data and perception observations into the engine and
records the results. Each public mutating method is one transaction.
"""
from __future__ import annotations

import base64
import binascii
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import Settings
from app.core.enums import (
    AuditEventType,
    ComplianceStatus,
    ImageQualityStatus,
    InspectionStatus,
)
from app.core.errors import (
    ImageTooLargeError,
    InvalidImageError,
    NotFoundError,
    UnsupportedFileError,
)
from app.core.logging import get_logger
from app.models import ComplianceFinding, Image, ImageRegion, Inspection, Package, Product
from app.schemas.image import RegisterImageRequest
from app.schemas.inspection import AnalyzeInspectionRequest, CreateInspectionRequest
from app.services.analytics.service import AnalyticsService
from app.services.audit.service import AuditService
from app.services.evidence.service import EvidenceService
from app.services.interfaces import (
    FieldObservation,
    ImageQualityAnalyzer,
    ImageQualityResult,
    OCRService,
    ProductUnderstandingService,
    RuleEngine,
    VisionService,
)
from app.services.provenance import resolve_model_version
from app.services.regulatory.service import RegulatoryService
from app.services.storage.base import StorageService

logger = get_logger(__name__)

# Medium confidence threshold (mirrors CONFIDENCE_THRESHOLDS.medium in config).
CONFIDENCE_THRESHOLD = 0.6

_DEGRADED_QUALITY = {
    ImageQualityStatus.BLURRY.value,
    ImageQualityStatus.GLARE.value,
    ImageQualityStatus.LOW_RESOLUTION.value,
}


class InspectionService:
    def __init__(
        self,
        *,
        settings: Settings,
        ocr: OCRService,
        vision: VisionService,
        product: ProductUnderstandingService,
        quality: ImageQualityAnalyzer,
        rule_engine: RuleEngine,
        regulatory: RegulatoryService,
        evidence: EvidenceService,
        audit: AuditService,
        analytics: AnalyticsService,
        storage: StorageService,
    ) -> None:
        self._settings = settings
        self._ocr = ocr
        self._vision = vision
        self._product = product
        self._quality = quality
        self._engine = rule_engine
        self._regulatory = regulatory
        self._evidence = evidence
        self._audit = audit
        self._analytics = analytics
        self._storage = storage

    # --- Reads -------------------------------------------------------------

    def get(self, db: Session, inspection_id: uuid.UUID) -> Inspection:
        stmt = (
            select(Inspection)
            .where(Inspection.id == inspection_id)
            .options(
                selectinload(Inspection.product),
                selectinload(Inspection.packages).selectinload(Package.images).selectinload(
                    Image.regions
                ),
            )
        )
        inspection = db.execute(stmt).scalar_one_or_none()
        if inspection is None:
            raise NotFoundError(f"Inspection not found: {inspection_id}")
        return inspection

    def list(
        self, db: Session, *, status: str | None, limit: int, offset: int
    ) -> tuple[list[Inspection], int]:
        base = select(Inspection)
        if status:
            base = base.where(Inspection.status == status)
        total = len(db.execute(base).scalars().all())
        page = (
            base.order_by(Inspection.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(db.execute(page).scalars().all()), total

    # --- Create ------------------------------------------------------------

    def create_inspection(
        self, db: Session, *, inspector_id: uuid.UUID | None, request: CreateInspectionRequest
    ) -> Inspection:
        profile = self._product.classify(
            name=request.product_name,
            category_hint=request.product_category,
            gtin=request.gtin,
        )
        product = Product(
            name=request.product_name,
            category=request.product_category,
            gtin=request.gtin,
            declaration_profile=[ft.value for ft in profile.declaration_profile],
            is_demo=True,
        )
        db.add(product)
        db.flush()

        inspection = Inspection(
            reference_no=self._reference_no(),
            status=InspectionStatus.CREATED.value,
            product_id=product.id,
            inspector_id=inspector_id,
            batch_id=request.batch_id,
            note=request.note,
            context_date=self._now(),
            is_demo=True,
        )
        db.add(inspection)
        db.flush()

        db.add(Package(inspection_id=inspection.id, product_id=product.id, label="Package 1"))
        db.flush()

        self._audit.record(
            db,
            event_type=AuditEventType.INSPECTION_CREATED,
            entity_type="inspection",
            entity_id=inspection.id,
            actor_id=inspector_id,
            inspection_id=inspection.id,
            payload={"referenceNo": inspection.reference_no, "category": request.product_category},
        )
        db.commit()
        return self.get(db, inspection.id)

    # --- Images ------------------------------------------------------------

    def add_image(
        self,
        db: Session,
        *,
        inspection_id: uuid.UUID,
        request: RegisterImageRequest,
        actor_id: uuid.UUID | None,
    ) -> Image:
        inspection = self.get(db, inspection_id)
        package = self._primary_package(db, inspection)

        mime = (request.mime_type or "").lower()
        if mime not in self._settings.allowed_image_mime_list:
            raise UnsupportedFileError(f"Unsupported image type: {request.mime_type}")

        data = self._decode_content(request.content_base64)
        if data is not None:
            if len(data) > self._settings.max_upload_bytes:
                raise ImageTooLargeError("Image exceeds the maximum allowed size.")
            storage_key = self._storage_key(inspection_id, request.original_filename)
            self._storage.save(key=storage_key, data=data, content_type=mime)
        elif request.storage_key:
            storage_key = request.storage_key
        else:
            raise InvalidImageError("Provide either contentBase64 or an existing storageKey.")

        quality = self._quality.analyze(
            image_bytes=data,
            width=request.width,
            height=request.height,
            mime_type=mime,
            seed=storage_key,
        )
        image = Image(
            package_id=package.id,
            storage_key=storage_key,
            original_filename=request.original_filename,
            mime_type=mime,
            width=request.width,
            height=request.height,
            file_size=len(data) if data is not None else request.file_size,
            image_type=request.image_type.value,
            quality_score=quality.score,
            quality_status=quality.status.value,
            is_demo=data is None,
        )
        db.add(image)

        if inspection.status == InspectionStatus.CREATED.value:
            inspection.status = InspectionStatus.IMAGES_PENDING.value
        db.flush()

        self._audit.record(
            db,
            event_type=AuditEventType.IMAGE_UPLOADED,
            entity_type="image",
            entity_id=image.id,
            actor_id=actor_id,
            inspection_id=inspection.id,
            payload={"qualityStatus": quality.status.value, "imageType": request.image_type.value},
        )
        db.commit()
        db.refresh(image)
        return image

    # --- Analyze (the pipeline) -------------------------------------------

    def analyze(
        self,
        db: Session,
        *,
        inspection_id: uuid.UUID,
        request: AnalyzeInspectionRequest | None = None,
        actor_id: uuid.UUID | None = None,
    ) -> Inspection:
        inspection = self.get(db, inspection_id)
        context_date = (
            (request.context_date if request else None)
            or inspection.context_date
            or inspection.created_at
        )

        inspection.status = InspectionStatus.ANALYZING.value
        db.flush()
        self._audit.record(
            db,
            event_type=AuditEventType.ANALYSIS_STARTED,
            entity_type="inspection",
            entity_id=inspection.id,
            actor_id=actor_id,
            inspection_id=inspection.id,
            payload={"contextDate": context_date.isoformat() if context_date else None},
        )

        self._reset_prior_analysis(db, inspection)

        # Provenance: one ModelVersion row per concrete service implementation.
        ocr_mv = resolve_model_version(db, self._ocr.descriptor)
        vision_mv = resolve_model_version(db, self._vision.descriptor)
        engine_mv = resolve_model_version(db, self._engine.descriptor)

        product = inspection.product
        profile = self._product.classify(
            name=product.name if product else "Unknown",
            category_hint=product.category if product else "general",
            gtin=product.gtin if product else None,
        )
        rules = self._regulatory.get_applicable_rules(
            db, category=profile.category, context_date=context_date
        )
        code_by_rule = {spec.rule_id: spec.rule_code for spec in rules}

        for package in inspection.packages:
            observations = self._perceive_package(
                db, package, profile=profile, ocr_mv_id=ocr_mv.id, vision_mv_id=vision_mv.id
            )
            first_image_id = package.images[0].id if package.images else None
            package_quality = self._aggregate_quality(package.images)

            if not rules:
                self._record_not_applicable(
                    db, inspection, package, first_image_id, engine_mv.id, profile.category, actor_id
                )
                continue

            results = self._engine.validate(
                observations=observations,
                rules=rules,
                quality=package_quality,
                confidence_threshold=CONFIDENCE_THRESHOLD,
            )
            for res in results:
                finding = ComplianceFinding(
                    inspection_id=inspection.id,
                    package_id=package.id,
                    rule_id=res.rule_id,
                    rule_version_id=res.rule_version_id,
                    field_type=res.field_type.value if res.field_type else None,
                    status=res.status.value,
                    confidence=res.confidence,
                    rationale=res.rationale,
                    model_version_id=engine_mv.id,
                    is_demo=True,
                )
                db.add(finding)
                db.flush()
                self._evidence.create_for_finding(
                    db,
                    finding=finding,
                    matched_field_ids=res.matched_field_ids,
                    fallback_image_id=first_image_id,
                    rule_code=code_by_rule.get(res.rule_id),
                    validator_output=res.validator_output,
                )
                self._audit.record(
                    db,
                    event_type=AuditEventType.FINDING_CREATED,
                    entity_type="compliance_finding",
                    entity_id=finding.id,
                    actor_id=actor_id,
                    inspection_id=inspection.id,
                    payload={"status": finding.status, "ruleCode": code_by_rule.get(res.rule_id)},
                )

        inspection.status = InspectionStatus.ANALYZED.value
        db.flush()
        self._audit.record(
            db,
            event_type=AuditEventType.ANALYSIS_COMPLETED,
            entity_type="inspection",
            entity_id=inspection.id,
            actor_id=actor_id,
            inspection_id=inspection.id,
            payload={"ruleCount": len(rules)},
        )

        if inspection.batch is not None:
            self._analytics.compute_batch_stats(db, inspection.batch)

        db.commit()
        return self.get(db, inspection.id)

    # --- Internals ---------------------------------------------------------

    def _perceive_package(
        self,
        db: Session,
        package: Package,
        *,
        profile,
        ocr_mv_id: uuid.UUID,
        vision_mv_id: uuid.UUID,
    ) -> list[FieldObservation]:
        from app.models import ExtractedField  # local import avoids a cycle at module load

        observations: list[FieldObservation] = []
        for image in package.images:
            seed = image.storage_key or str(image.id)
            ocr = self._ocr.extract_text(image_bytes=None, storage_key=image.storage_key, seed=seed)
            regions_result = self._vision.regions_from_ocr(ocr)

            region_by_text: dict[str, uuid.UUID] = {}
            for line, detected in zip(ocr.lines, regions_result.regions):
                region = ImageRegion(
                    image_id=image.id,
                    region_type=detected.region_type.value,
                    bbox=detected.bbox.as_dict(),
                    confidence=detected.confidence,
                )
                db.add(region)
                db.flush()
                region_by_text[line.text] = region.id

            candidates = self._vision.detect_fields(
                ocr=ocr, regions=regions_result, profile=profile, seed=seed
            )
            for cand in candidates:
                field = ExtractedField(
                    image_id=image.id,
                    image_region_id=region_by_text.get(cand.raw_text),
                    package_id=package.id,
                    field_type=cand.field_type.value,
                    raw_text=cand.raw_text,
                    normalized_value=cand.normalized_value,
                    unit=cand.unit,
                    confidence=cand.confidence,
                    extraction_method="mock",
                    model_version_id=vision_mv_id,
                    is_demo=True,
                )
                db.add(field)
                db.flush()
                observations.append(
                    FieldObservation(
                        id=field.id,
                        field_type=cand.field_type,
                        raw_text=cand.raw_text,
                        confidence=cand.confidence,
                        normalized_value=cand.normalized_value,
                    )
                )
        return observations

    def _record_not_applicable(
        self,
        db: Session,
        inspection: Inspection,
        package: Package,
        first_image_id: uuid.UUID | None,
        engine_mv_id: uuid.UUID,
        category: str,
        actor_id: uuid.UUID | None,
    ) -> None:
        finding = ComplianceFinding(
            inspection_id=inspection.id,
            package_id=package.id,
            rule_id=None,
            rule_version_id=None,
            field_type=None,
            status=ComplianceStatus.NOT_APPLICABLE.value,
            confidence=1.0,
            rationale=(
                f"No applicable rule found for category '{category}' at the inspection "
                "context date. DEMO DATA — NOT LEGAL ADVICE."
            ),
            model_version_id=engine_mv_id,
            is_demo=True,
        )
        db.add(finding)
        db.flush()
        self._evidence.create_for_finding(
            db,
            finding=finding,
            matched_field_ids=[],
            fallback_image_id=first_image_id,
            rule_code=None,
            validator_output={"note": "no_applicable_rule", "category": category},
        )
        self._audit.record(
            db,
            event_type=AuditEventType.FINDING_CREATED,
            entity_type="compliance_finding",
            entity_id=finding.id,
            actor_id=actor_id,
            inspection_id=inspection.id,
            payload={"status": finding.status},
        )

    def _reset_prior_analysis(self, db: Session, inspection: Inspection) -> None:
        """Make re-analysis idempotent: drop prior findings/fields/regions.

        Uses ORM deletes so relationship cascades fire regardless of whether the
        database enforces ON DELETE (SQLite does not, by default)."""
        for finding in list(inspection.findings):
            db.delete(finding)
        for package in inspection.packages:
            for image in package.images:
                for field in list(image.extracted_fields):
                    db.delete(field)
                for region in list(image.regions):
                    db.delete(region)
        db.flush()

    @staticmethod
    def _aggregate_quality(images: list[Image]) -> ImageQualityResult:
        if not images:
            return ImageQualityResult(ImageQualityStatus.UNKNOWN, 0.0, "No images to analyse.")
        scores = [img.quality_score if img.quality_score is not None else 0.0 for img in images]
        min_score = min(scores)
        statuses = [img.quality_status for img in images]
        note = f"Aggregated worst-case quality across {len(images)} image(s)."
        if ImageQualityStatus.INSUFFICIENT.value in statuses:
            return ImageQualityResult(ImageQualityStatus.INSUFFICIENT, min_score, note)
        for img in sorted(images, key=lambda i: i.quality_score or 0.0):
            if img.quality_status in _DEGRADED_QUALITY:
                return ImageQualityResult(ImageQualityStatus(img.quality_status), img.quality_score or 0.0, note)
        return ImageQualityResult(ImageQualityStatus.OK, min_score, note)

    @staticmethod
    def _primary_package(db: Session, inspection: Inspection) -> Package:
        if inspection.packages:
            return inspection.packages[0]
        package = Package(inspection_id=inspection.id, product_id=inspection.product_id, label="Package 1")
        db.add(package)
        db.flush()
        return package

    @staticmethod
    def _decode_content(content_base64: str | None) -> bytes | None:
        if not content_base64:
            return None
        payload = content_base64
        if payload.startswith("data:") and "," in payload:
            payload = payload.split(",", 1)[1]
        try:
            return base64.b64decode(payload, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise InvalidImageError("contentBase64 is not valid base64 data.") from exc

    @staticmethod
    def _storage_key(inspection_id: uuid.UUID, filename: str) -> str:
        suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
        return f"inspections/{inspection_id}/{uuid.uuid4().hex}.{suffix}"

    @staticmethod
    def _reference_no() -> str:
        return f"LM-{uuid.uuid4().hex[:8].upper()}"

    @staticmethod
    def _now() -> datetime:
        from app.db.base import utcnow

        return utcnow()
