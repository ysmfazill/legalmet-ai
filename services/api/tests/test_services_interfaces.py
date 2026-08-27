"""Service interfaces + the pluggability (dependency-injection) seam.

Verifies that every concrete mock honours its abstract interface, that
perception services only *describe* (never conclude), and that the registry
wires a deterministic (non-LLM) rule engine as the compliance authority.
"""
from __future__ import annotations

from app.core.config import get_settings
from app.core.enums import FieldType, ImageQualityStatus, ModelServiceType
from app.services.interfaces import (
    BBox,
    ImageQualityAnalyzer,
    OcrLine,
    OcrResult,
    OCRService,
    ProductUnderstandingService,
    RuleEngine,
    VisionService,
)
from app.services.ocr.mock import MockOCRService
from app.services.product.mock import MockProductUnderstandingService
from app.services.quality.mock import MockImageQualityAnalyzer
from app.services.registry import build_services
from app.services.rules.engine import DeterministicRuleEngine
from app.services.vision.mock import MockVisionService


def test_mocks_conform_to_interfaces():
    assert isinstance(MockOCRService(), OCRService)
    assert isinstance(MockVisionService(), VisionService)
    assert isinstance(MockProductUnderstandingService(), ProductUnderstandingService)
    assert isinstance(MockImageQualityAnalyzer(), ImageQualityAnalyzer)
    assert isinstance(DeterministicRuleEngine(), RuleEngine)


def test_ocr_returns_scored_lines():
    result = MockOCRService().extract_text(image_bytes=None, storage_key="k", seed="seed-1")
    assert isinstance(result, OcrResult)
    assert result.lines
    assert 0.0 <= result.mean_confidence <= 1.0
    assert result.descriptor.service_type == ModelServiceType.OCR


def test_product_profile_is_a_perception_hint_not_law():
    profile = MockProductUnderstandingService().classify(
        name="DEMO Snack", category_hint="food", gtin=None
    )
    assert profile.category == "food"
    # Category hint adds expected declarations (perception only).
    assert FieldType.BEST_BEFORE in profile.declaration_profile


def test_vision_maps_text_to_field_candidates():
    ocr = OcrResult(
        lines=[
            OcrLine("M.R.P. Rs. 199.00", BBox(0.1, 0.2, 0.5, 0.05), 0.95),
            OcrLine("Net Qty: 500 g", BBox(0.1, 0.3, 0.4, 0.05), 0.92),
        ],
        mean_confidence=0.93,
        descriptor=MockOCRService().descriptor,
    )
    profile = MockProductUnderstandingService().classify(name="x", category_hint="food", gtin=None)
    candidates = MockVisionService().detect_fields(
        ocr=ocr, regions=MockVisionService().regions_from_ocr(ocr), profile=profile, seed="s"
    )
    found = {c.field_type for c in candidates}
    assert FieldType.MRP in found
    assert FieldType.NET_QUANTITY in found


def test_quality_low_resolution_is_deterministic():
    verdict = MockImageQualityAnalyzer().analyze(
        image_bytes=None, width=100, height=100, mime_type="image/png", seed="s"
    )
    assert verdict.status == ImageQualityStatus.LOW_RESOLUTION


def test_registry_wires_a_deterministic_rule_engine():
    services = build_services(get_settings())
    # Every capability is present behind its interface.
    assert isinstance(services.ocr, OCRService)
    assert isinstance(services.vision, VisionService)
    assert isinstance(services.product, ProductUnderstandingService)
    assert isinstance(services.quality, ImageQualityAnalyzer)
    assert isinstance(services.rule_engine, RuleEngine)
    # Compliance authority MUST be the deterministic engine — never an LLM.
    assert isinstance(services.rule_engine, DeterministicRuleEngine)
    assert services.rule_engine.descriptor.service_type == ModelServiceType.RULE_ENGINE
