"""Service interfaces (the pluggability seam).

Every AI/perception capability and every domain capability is defined here as
an abstract base class with plain-dataclass inputs/outputs. Concrete
implementations (mock today, real models later — PaddleOCR, YOLO, an LLM, an
S3 client) are swapped via the service registry without touching call sites.

Critical separation of concerns encoded by these interfaces:

* Perception services (OCR / vision / product understanding) only *describe*
  what they see, with confidence. They never assert legal conclusions.
* The :class:`RuleEngine` is the ONLY component that decides compliance, and it
  does so deterministically from verified rule data + observations. No LLM is
  in this path.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from uuid import UUID

from app.core.enums import (
    ComplianceStatus,
    FieldType,
    ImageQualityGrade,
    ImageQualityStatus,
    ModelServiceType,
    RegionType,
)

# ---------------------------------------------------------------------------
# Shared value objects
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BBox:
    """Normalised bounding box in 0..1 image coordinates."""

    x: float
    y: float
    width: float
    height: float

    def as_dict(self) -> dict[str, float]:
        return {"x": self.x, "y": self.y, "width": self.width, "height": self.height}


@dataclass(frozen=True)
class ServiceDescriptor:
    """Identity of a concrete service implementation (for provenance)."""

    service_type: ModelServiceType
    name: str
    version: str
    provider: str


@dataclass
class ImageQualityResult:
    status: ImageQualityStatus
    score: float
    notes: str = ""
    # Prompt 3 additive fields. The mock analyzer leaves these unset; the real
    # Pillow analyzer populates `grade` and a camelCase `metrics` breakdown.
    grade: ImageQualityGrade | None = None
    metrics: dict = field(default_factory=dict)


@dataclass
class OcrLine:
    text: str
    bbox: BBox
    confidence: float


@dataclass
class OcrResult:
    lines: list[OcrLine]
    mean_confidence: float
    descriptor: ServiceDescriptor


@dataclass
class DetectedRegion:
    region_type: RegionType
    bbox: BBox
    confidence: float


@dataclass
class VisionRegionsResult:
    regions: list[DetectedRegion]
    descriptor: ServiceDescriptor


@dataclass
class FieldCandidate:
    field_type: FieldType
    raw_text: str
    confidence: float
    bbox: BBox
    normalized_value: str | None = None
    unit: str | None = None


@dataclass
class ProductProfile:
    category: str
    declaration_profile: list[FieldType]
    confidence: float
    descriptor: ServiceDescriptor


# ---------------------------------------------------------------------------
# Rule-engine value objects
# ---------------------------------------------------------------------------


@dataclass
class FieldObservation:
    """A perception claim fed into the deterministic rule engine."""

    id: UUID
    field_type: FieldType
    raw_text: str
    confidence: float
    normalized_value: str | None = None


@dataclass
class RuleSpec:
    """A single verified rule, resolved for a specific version, ready to run."""

    rule_id: UUID
    rule_version_id: UUID
    rule_code: str
    requirement_summary: str
    validation_logic_ref: str
    target_field_type: FieldType | None = None
    params: dict = field(default_factory=dict)


@dataclass
class FindingResult:
    """Deterministic engine output. Not persisted directly — the orchestrator
    maps this onto ComplianceFinding + Evidence rows."""

    rule_id: UUID | None
    rule_version_id: UUID | None
    field_type: FieldType | None
    status: ComplianceStatus
    confidence: float
    rationale: str
    matched_field_ids: list[UUID] = field(default_factory=list)
    validator_output: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Abstract services
# ---------------------------------------------------------------------------


class ImageQualityAnalyzer(abc.ABC):
    @abc.abstractmethod
    def analyze(
        self,
        *,
        image_bytes: bytes | None,
        width: int | None,
        height: int | None,
        mime_type: str,
        seed: str,
    ) -> ImageQualityResult: ...


class OCRService(abc.ABC):
    @property
    @abc.abstractmethod
    def descriptor(self) -> ServiceDescriptor: ...

    @abc.abstractmethod
    def extract_text(
        self, *, image_bytes: bytes | None, storage_key: str, seed: str
    ) -> OcrResult: ...


class VisionService(abc.ABC):
    @property
    @abc.abstractmethod
    def descriptor(self) -> ServiceDescriptor: ...

    @abc.abstractmethod
    def detect_regions(
        self, *, image_bytes: bytes | None, storage_key: str, seed: str
    ) -> VisionRegionsResult: ...

    @abc.abstractmethod
    def detect_fields(
        self, *, ocr: OcrResult, regions: VisionRegionsResult, profile: ProductProfile, seed: str
    ) -> list[FieldCandidate]: ...


class ProductUnderstandingService(abc.ABC):
    @property
    @abc.abstractmethod
    def descriptor(self) -> ServiceDescriptor: ...

    @abc.abstractmethod
    def classify(
        self, *, name: str, category_hint: str | None, gtin: str | None
    ) -> ProductProfile: ...


class RuleEngine(abc.ABC):
    @property
    @abc.abstractmethod
    def descriptor(self) -> ServiceDescriptor: ...

    @abc.abstractmethod
    def validate(
        self,
        *,
        observations: list[FieldObservation],
        rules: list[RuleSpec],
        quality: ImageQualityResult,
        confidence_threshold: float,
    ) -> list[FindingResult]: ...
