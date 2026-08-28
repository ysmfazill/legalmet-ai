"""Service registry — the composition root / dependency-injection seam.

One place assembles every concrete implementation and wires the orchestrator.
Swapping a mock for a real backend (PaddleOCR, YOLO, an LLM, S3) is a change
*here only* — call sites depend on the interfaces, never the implementations.

Selection is config-driven so environments differ by settings, not by code.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Callable

from app.core.config import Settings, get_settings
from app.services.analytics.service import AnalyticsService
from app.services.audit.service import AuditService
from app.services.evidence.service import EvidenceService
from app.services.inspection.service import InspectionService
from app.services.intake.service import IntakeService
from app.services.interfaces import (
    FieldExtractionProvider,
    ImagePreprocessor,
    ImageQualityAnalyzer,
    OCRService,
    ProductUnderstandingService,
    RuleEngine,
    VisionService,
)
from app.services.ocr.mock import MockOCRService
from app.services.ocr.paddle import PaddleOCRService
from app.services.perception.extract import DeterministicFieldExtractor
from app.services.perception.pipeline import PackagePerceptionPipeline
from app.services.perception.preprocess import PillowOcrPreprocessor
from app.services.perception.service import PerceptionService
from app.services.product.mock import MockProductUnderstandingService
from app.services.quality.mock import MockImageQualityAnalyzer
from app.services.quality.pillow import PillowImageQualityAnalyzer
from app.services.regulatory.service import RegulatoryService
from app.services.review.service import ReviewService
from app.services.rules.engine import DeterministicRuleEngine
from app.services.storage.base import StorageService
from app.services.storage.local import LocalStorage
from app.services.vision.mock import MockVisionService
from app.services.vision.opencv import OpenCVVisionService


@dataclass
class Services:
    """Container holding every wired service (accessed via FastAPI deps)."""

    settings: Settings
    storage: StorageService
    ocr: OCRService
    vision: VisionService
    product: ProductUnderstandingService
    quality: ImageQualityAnalyzer
    intake_quality: ImageQualityAnalyzer
    rule_engine: RuleEngine
    regulatory: RegulatoryService
    evidence: EvidenceService
    audit: AuditService
    review: ReviewService
    analytics: AnalyticsService
    inspection: InspectionService
    intake: IntakeService
    # --- Prompt 4: real perception stack ---------------------------------
    preprocessor: ImagePreprocessor
    field_extractor: FieldExtractionProvider
    perception: PerceptionService
    # Session factory used by background perception execution (each run gets
    # its own session; tests inject the in-memory engine's factory here).
    session_factory: Callable[[], object]


def _build_storage(settings: Settings) -> StorageService:
    # Only the local backend exists in the foundation phase; an S3/MinIO backend
    # plugs in here behind the same StorageService interface.
    return LocalStorage(settings.storage_dir)


def _build_ocr(settings: Settings) -> OCRService:
    return MockOCRService()


def _build_vision(settings: Settings) -> VisionService:
    return MockVisionService()


def _build_product(settings: Settings) -> ProductUnderstandingService:
    return MockProductUnderstandingService()


def _build_quality(settings: Settings) -> ImageQualityAnalyzer:
    # Mock analyzer feeds the (later-phase) analysis pipeline. It is seeded and
    # tolerant of the 1x1 fixtures used by the perception tests.
    return MockImageQualityAnalyzer()


def _build_intake_quality(settings: Settings) -> ImageQualityAnalyzer:
    # Real, deterministic usability grader for the intake path (Prompt 3). It
    # reads actual pixels; the score is an IMAGE-USABILITY score only — never
    # AI/compliance/legal confidence.
    return PillowImageQualityAnalyzer(
        min_width=settings.min_image_width, min_height=settings.min_image_height
    )


def _build_rule_engine(settings: Settings) -> RuleEngine:
    # Deterministic and non-AI by design: the only component that concludes
    # compliance. This is intentionally NOT configurable to an LLM backend.
    return DeterministicRuleEngine()


def _build_perception_ocr(settings: Settings) -> OCRService:
    """REAL OCR backend for the Prompt 4 perception pipeline.

    Config-driven so environments differ by settings: `paddle` (default) runs
    the local PaddleOCR CPU engine; `mock` keeps the seeded demo stub. The
    legacy `ocr` service above stays on the mock and feeds only the demo
    compliance flow, so Prompt 1–3 behaviour is untouched.
    """
    backend = settings.perception_ocr_backend.strip().lower()
    if backend == "paddle":
        return PaddleOCRService(
            langs=settings.perception_ocr_lang_list,
            timeout_seconds=settings.perception_ocr_timeout_seconds,
        )
    if backend == "mock":
        return MockOCRService()
    raise ValueError(
        f"Unknown perception_ocr_backend: {settings.perception_ocr_backend!r} (use 'paddle' or 'mock')"
    )


def _build_perception_vision(settings: Settings) -> VisionService:
    # Real QR/barcode region detection. A heavier detector (e.g. YOLO) plugs
    # in here behind the same VisionService seam.
    return OpenCVVisionService()


def _build_preprocessor(settings: Settings) -> ImagePreprocessor:
    return PillowOcrPreprocessor(
        min_long_edge=settings.perception_ocr_min_long_edge,
        max_long_edge=settings.perception_ocr_max_long_edge,
    )


def _build_field_extractor(settings: Settings) -> FieldExtractionProvider:
    return DeterministicFieldExtractor(
        review_threshold=settings.perception_field_review_threshold
    )


def build_services(
    settings: Settings,
    *,
    session_factory: Callable[[], object] | None = None,
) -> Services:
    if session_factory is None:
        from app.db.session import SessionLocal

        session_factory = SessionLocal

    storage = _build_storage(settings)
    ocr = _build_ocr(settings)
    vision = _build_vision(settings)
    product = _build_product(settings)
    quality = _build_quality(settings)
    intake_quality = _build_intake_quality(settings)
    rule_engine = _build_rule_engine(settings)

    regulatory = RegulatoryService()
    evidence = EvidenceService()
    audit = AuditService()
    review = ReviewService(audit)
    analytics = AnalyticsService()

    inspection = InspectionService(
        settings=settings,
        ocr=ocr,
        vision=vision,
        product=product,
        quality=quality,
        rule_engine=rule_engine,
        regulatory=regulatory,
        evidence=evidence,
        audit=audit,
        analytics=analytics,
        storage=storage,
    )

    intake = IntakeService(
        settings=settings,
        storage=storage,
        quality=intake_quality,
        audit=audit,
    )

    preprocessor = _build_preprocessor(settings)
    field_extractor = _build_field_extractor(settings)
    pipeline = PackagePerceptionPipeline(
        settings=settings,
        storage=storage,
        ocr=_build_perception_ocr(settings),
        vision=_build_perception_vision(settings),
        preprocessor=preprocessor,
        extractor=field_extractor,
        audit=audit,
    )
    perception = PerceptionService(pipeline=pipeline, session_factory=session_factory)

    return Services(
        settings=settings,
        storage=storage,
        ocr=ocr,
        vision=vision,
        product=product,
        quality=quality,
        intake_quality=intake_quality,
        rule_engine=rule_engine,
        regulatory=regulatory,
        evidence=evidence,
        audit=audit,
        review=review,
        analytics=analytics,
        inspection=inspection,
        intake=intake,
        preprocessor=preprocessor,
        field_extractor=field_extractor,
        perception=perception,
        session_factory=session_factory,
    )


@lru_cache
def get_services() -> Services:
    """Process-wide singleton built from settings (overridable in tests)."""
    return build_services(get_settings())
