"""Canonical domain enumerations (Python side).

These MUST stay byte-for-byte identical (string values) to the TypeScript
enums in `packages/types/src/enums.ts`. That shared vocabulary is what lets the
frontend, API and database speak about the same states without a translation
layer. See docs/architecture.md — "Shared contract & single source of truth".
"""
from __future__ import annotations

from enum import Enum


class StrEnum(str, Enum):
    """String-valued enum that serialises to its value (JSON-friendly)."""

    def __str__(self) -> str:  # pragma: no cover - trivial
        return str(self.value)


class UserRole(StrEnum):
    ADMIN = "ADMIN"
    INSPECTOR = "INSPECTOR"
    SUPERVISOR = "SUPERVISOR"
    AUDITOR = "AUDITOR"


class InspectionStatus(StrEnum):
    CREATED = "CREATED"
    IMAGES_PENDING = "IMAGES_PENDING"
    READY_FOR_ANALYSIS = "READY_FOR_ANALYSIS"
    ANALYZING = "ANALYZING"
    ANALYZED = "ANALYZED"
    UNDER_REVIEW = "UNDER_REVIEW"
    COMPLETED = "COMPLETED"
    ARCHIVED = "ARCHIVED"


class PackageStatus(StrEnum):
    """Package intake lifecycle (Prompt 3). Independent of compliance."""

    CREATED = "CREATED"
    IMAGE_ATTACHED = "IMAGE_ATTACHED"
    READY_FOR_ANALYSIS = "READY_FOR_ANALYSIS"


class CaptureSource(StrEnum):
    """How a package image entered the system."""

    CAMERA = "CAMERA"
    UPLOAD = "UPLOAD"
    BATCH = "BATCH"


class ImageProcessingStatus(StrEnum):
    """Preprocessing / derivative pipeline state for a stored image."""

    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    READY = "READY"
    FAILED = "FAILED"


class ImageQualityGrade(StrEnum):
    """Overall *usability* grade from the deterministic quality analyzer.

    A usability signal for downstream analysis — explicitly NOT an
    AI-confidence, accuracy, or Legal-Metrology-compliance judgement.
    """

    EXCELLENT = "EXCELLENT"
    GOOD = "GOOD"
    ACCEPTABLE = "ACCEPTABLE"
    POOR = "POOR"
    REJECTED = "REJECTED"


class ComplianceStatus(StrEnum):
    COMPLIANT = "COMPLIANT"
    POTENTIAL_VIOLATION = "POTENTIAL_VIOLATION"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    IMAGE_QUALITY_INSUFFICIENT = "IMAGE_QUALITY_INSUFFICIENT"


class FieldType(StrEnum):
    # Prompt 4 additions: PRODUCT_NAME / BRAND_NAME / ADDRESS let the
    # perception layer record name-plate and address evidence; LOT_NUMBER is
    # intentionally folded into BATCH_NUMBER (same regex family) to avoid two
    # competing types for one physical marking.
    PRODUCT_NAME = "PRODUCT_NAME"
    BRAND_NAME = "BRAND_NAME"
    MRP = "MRP"
    NET_QUANTITY = "NET_QUANTITY"
    GENERIC_NAME = "GENERIC_NAME"
    MANUFACTURER_DETAILS = "MANUFACTURER_DETAILS"
    PACKER_DETAILS = "PACKER_DETAILS"
    IMPORTER_DETAILS = "IMPORTER_DETAILS"
    COUNTRY_OF_ORIGIN = "COUNTRY_OF_ORIGIN"
    ADDRESS = "ADDRESS"
    DATE_OF_MANUFACTURE = "DATE_OF_MANUFACTURE"
    DATE_OF_PACKING = "DATE_OF_PACKING"
    BEST_BEFORE = "BEST_BEFORE"
    EXPIRY_DATE = "EXPIRY_DATE"
    CONSUMER_CARE = "CONSUMER_CARE"
    BATCH_NUMBER = "BATCH_NUMBER"
    DIMENSIONS = "DIMENSIONS"
    UNIT_SALE_PRICE = "UNIT_SALE_PRICE"
    OTHER = "OTHER"


class ReviewActionType(StrEnum):
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"
    CORRECT = "CORRECT"
    REQUEST_RESCAN = "REQUEST_RESCAN"
    ESCALATE = "ESCALATE"
    NOTE = "NOTE"


class ImageType(StrEnum):
    FRONT = "FRONT"
    BACK = "BACK"
    SIDE = "SIDE"
    TOP = "TOP"
    BOTTOM = "BOTTOM"
    LABEL = "LABEL"
    OTHER = "OTHER"


class ImageQualityStatus(StrEnum):
    OK = "OK"
    LOW_RESOLUTION = "LOW_RESOLUTION"
    BLURRY = "BLURRY"
    GLARE = "GLARE"
    INSUFFICIENT = "INSUFFICIENT"
    UNKNOWN = "UNKNOWN"


class RegionType(StrEnum):
    TEXT_BLOCK = "TEXT_BLOCK"
    TEXT_LINE = "TEXT_LINE"
    SYMBOL = "SYMBOL"
    LOGO = "LOGO"
    BARCODE = "BARCODE"
    QR_CODE = "QR_CODE"
    GRAPHIC = "GRAPHIC"
    OTHER = "OTHER"


class RegulationVersionStatus(StrEnum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    REPEALED = "REPEALED"


class RuleStatus(StrEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    DRAFT = "DRAFT"


class SourceType(StrEnum):
    """Kind of repository/authority a regulatory source is (Prompt 5)."""

    GOVERNMENT_DEPARTMENT = "GOVERNMENT_DEPARTMENT"
    OFFICIAL_REPOSITORY = "OFFICIAL_REPOSITORY"
    GAZETTE_PUBLICATION = "GAZETTE_PUBLICATION"
    LEGAL_DATABASE = "LEGAL_DATABASE"
    OTHER = "OTHER"


class VerificationStatus(StrEnum):
    """Verification state of a regulatory SOURCE (Prompt 5).

    This is a property of the *source provenance* — how much the system trusts
    that the recorded regulatory content matches an authoritative government
    publication. It is completely separate from OCR confidence and is never an
    AI confidence. Only VERIFIED sources may be approved for production
    compliance evaluation (Prompt 6).
    """

    UNVERIFIED = "UNVERIFIED"
    VERIFIED = "VERIFIED"
    SUPERSEDED = "SUPERSEDED"
    ARCHIVED = "ARCHIVED"


class DocumentType(StrEnum):
    """Kind of regulatory document (Prompt 5)."""

    RULES = "RULES"
    ACT = "ACT"
    AMENDMENT_NOTIFICATION = "AMENDMENT_NOTIFICATION"
    CIRCULAR = "CIRCULAR"
    GUIDANCE = "GUIDANCE"
    OTHER = "OTHER"


class RequirementType(StrEnum):
    """Kind of regulatory requirement (Prompt 5). Not a compliance verdict."""

    DECLARATION = "DECLARATION"
    FORMAT = "FORMAT"
    PROHIBITION = "PROHIBITION"
    PROCEDURAL = "PROCEDURAL"


class VersionSelectionStatus(StrEnum):
    """Outcome of deterministic effective-date version selection (Prompt 5).

    NO_APPLICABLE_VERSION is an explicit state — the resolver never silently
    falls back to the newest version.
    """

    FOUND = "FOUND"
    NO_APPLICABLE_VERSION = "NO_APPLICABLE_VERSION"


class CandidateMappingStatus(StrEnum):
    """Status of a field → requirement candidate mapping (Prompt 5).

    A candidate mapping is a *possible* association between perceived evidence
    and a requirement definition. Applicability is NOT evaluated here and NO
    compliance conclusion is ever drawn (that is Prompt 6).
    """

    CANDIDATE = "CANDIDATE"
    APPLICABILITY_NOT_EVALUATED = "APPLICABILITY_NOT_EVALUATED"
    AWAITING_COMPLIANCE_ENGINE = "AWAITING_COMPLIANCE_ENGINE"



class EvidenceType(StrEnum):
    OCR_TEXT = "OCR_TEXT"
    IMAGE_REGION = "IMAGE_REGION"
    EXTRACTED_FIELD = "EXTRACTED_FIELD"
    VISUAL_ELEMENT = "VISUAL_ELEMENT"
    RULE_REFERENCE = "RULE_REFERENCE"
    VALIDATION_RESULT = "VALIDATION_RESULT"


class ModelServiceType(StrEnum):
    OCR = "OCR"
    VISION = "VISION"
    PRODUCT_CLASSIFIER = "PRODUCT_CLASSIFIER"
    FIELD_EXTRACTOR = "FIELD_EXTRACTOR"
    RULE_ENGINE = "RULE_ENGINE"
    LLM_ASSIST = "LLM_ASSIST"


class ProcessingRunStatus(StrEnum):
    """Lifecycle of one perception processing run (Prompt 4).

    Perception-only states — they assert what the pipeline did to the image,
    never anything about compliance. REVIEW_REQUIRED means the run finished but
    produced low-confidence evidence a human should look at.
    """

    QUEUED = "QUEUED"
    PREPROCESSING = "PREPROCESSING"
    OCR_PROCESSING = "OCR_PROCESSING"
    VISION_PROCESSING = "VISION_PROCESSING"
    FIELD_EXTRACTION = "FIELD_EXTRACTION"
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"

    @property
    def is_terminal(self) -> bool:
        return self in _TERMINAL_RUN_STATUSES


_TERMINAL_RUN_STATUSES = frozenset(
    {
        ProcessingRunStatus.COMPLETED,
        ProcessingRunStatus.PARTIAL,
        ProcessingRunStatus.FAILED,
        ProcessingRunStatus.REVIEW_REQUIRED,
    }
)


class ExtractionStatus(StrEnum):
    """Per-field perception outcome (Prompt 4). Not a compliance verdict.

    DETECTED — deterministic evidence found with adequate OCR confidence.
    REVIEW_REQUIRED — a pattern matched but OCR confidence is low; a human
    must confirm before anything downstream trusts the value.
    NOT_EXTRACTED — the field was located (e.g. an "MRP" label was seen) but
    no usable value could be read. Never silently guessed.
    """

    DETECTED = "DETECTED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    NOT_EXTRACTED = "NOT_EXTRACTED"


class AuditEventType(StrEnum):
    INSPECTION_CREATED = "INSPECTION_CREATED"
    IMAGE_UPLOADED = "IMAGE_UPLOADED"
    ANALYSIS_STARTED = "ANALYSIS_STARTED"
    ANALYSIS_COMPLETED = "ANALYSIS_COMPLETED"
    FINDING_CREATED = "FINDING_CREATED"
    REVIEW_RECORDED = "REVIEW_RECORDED"
    INSPECTION_COMPLETED = "INSPECTION_COMPLETED"
    INSPECTION_ARCHIVED = "INSPECTION_ARCHIVED"
    # Prompt 3 — real package intake pipeline
    PACKAGE_CREATED = "PACKAGE_CREATED"
    IMAGE_UPLOAD_STARTED = "IMAGE_UPLOAD_STARTED"
    IMAGE_REJECTED = "IMAGE_REJECTED"
    QUALITY_CHECK_COMPLETED = "QUALITY_CHECK_COMPLETED"
    IMAGE_PREPARED = "IMAGE_PREPARED"
    IMAGE_DELETED = "IMAGE_DELETED"
    INSPECTION_READY = "INSPECTION_READY"
    # Prompt 4 — real perception pipeline
    PERCEPTION_STARTED = "PERCEPTION_STARTED"
    PERCEPTION_COMPLETED = "PERCEPTION_COMPLETED"
    PERCEPTION_FAILED = "PERCEPTION_FAILED"
    IMAGE_REANALYZED = "IMAGE_REANALYZED"
    # Prompt 5 — regulatory intelligence (authoritative data lifecycle)
    REGULATORY_SOURCE_CREATED = "REGULATORY_SOURCE_CREATED"
    REGULATORY_SOURCE_UPDATED = "REGULATORY_SOURCE_UPDATED"
    REGULATORY_DOCUMENT_CREATED = "REGULATORY_DOCUMENT_CREATED"
    REGULATORY_VERSION_CREATED = "REGULATORY_VERSION_CREATED"
    REGULATORY_VERSION_SUPERSEDED = "REGULATORY_VERSION_SUPERSEDED"
    REGULATORY_REQUIREMENT_CREATED = "REGULATORY_REQUIREMENT_CREATED"
    REGULATORY_REQUIREMENT_UPDATED = "REGULATORY_REQUIREMENT_UPDATED"
    REGULATORY_DATA_SEEDED = "REGULATORY_DATA_SEEDED"
    # Prompt 6 — deterministic compliance engine lifecycle
    COMPLIANCE_EVALUATION_STARTED = "COMPLIANCE_EVALUATION_STARTED"
    COMPLIANCE_EVALUATION_COMPLETED = "COMPLIANCE_EVALUATION_COMPLETED"
    COMPLIANCE_EVALUATION_FAILED = "COMPLIANCE_EVALUATION_FAILED"
    COMPLIANCE_FINDING_CREATED = "COMPLIANCE_FINDING_CREATED"


class BatchStatus(StrEnum):
    OPEN = "OPEN"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    ARCHIVED = "ARCHIVED"


# --- Prompt 6 — deterministic compliance engine -------------------------------


class EvaluationStatus(StrEnum):
    """Lifecycle of one compliance evaluation over an inspection.

    An evaluation is a SYSTEM-GENERATED DECISION-SUPPORT ARTIFACT. None of these
    states is an enforcement determination — the inspector remains responsible
    for the final enforcement decision.
    """

    NOT_EVALUATED = "NOT_EVALUATED"
    EVALUATING = "EVALUATING"
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"  # some rules evaluated, some could not (engine failure)
    REVIEW_REQUIRED = "REVIEW_REQUIRED"  # one or more findings need a human
    FAILED = "FAILED"  # engine error — no findings may be trusted from this run
    NO_APPLICABLE_REQUIREMENT = "NO_APPLICABLE_REQUIREMENT"


class EngineFindingStatus(StrEnum):
    """Outcome of ONE requirement against ONE detected field.

    COMPLIANT / NON_COMPLIANT are only produced with adequate valid evidence
    AND a positive applicability determination. Insufficient evidence downgrades
    the finding to REVIEW_REQUIRED — the engine never guesses.
    """

    COMPLIANT = "COMPLIANT"
    NON_COMPLIANT = "NON_COMPLIANT"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    NOT_DETECTED = "NOT_DETECTED"  # applicable, but no field was extracted
    NOT_APPLICABLE = "NOT_APPLICABLE"  # applicability resolved NO — no violation
    NOT_EVALUATED = "NOT_EVALUATED"  # rule exists but engine could not evaluate


class FindingSeverity(StrEnum):
    """Severity classification of a system-generated finding.

    An informational severity vocabulary for triage — never a penalty or a
    legal consequence, which only a human enforcement decision may assign.
    """

    INFO = "INFO"
    MINOR = "MINOR"
    MAJOR = "MAJOR"
    CRITICAL = "CRITICAL"
    UNKNOWN = "UNKNOWN"


class DeterministicRuleType(StrEnum):
    """Vocabulary of deterministic rule types the compliance engine executes.

    Deliberately small: every type maps to code in
    ``app/services/compliance/evaluators.py`` and every seeded rule must
    correspond to a verified requirement from the Prompt 5 regulatory data —
    the engine never invents requirements.
    """

    PRESENCE = "PRESENCE"
    TEXT_MATCH = "TEXT_MATCH"
    TEXT_PATTERN = "TEXT_PATTERN"
    NUMERIC_VALUE = "NUMERIC_VALUE"
    UNIT_MATCH = "UNIT_MATCH"
    MRP_FORMAT = "MRP_FORMAT"
    DATE_FORMAT = "DATE_FORMAT"
    CONTACT_FORMAT = "CONTACT_FORMAT"
    DECLARATION_FORMAT = "DECLARATION_FORMAT"
    FIELD_REQUIRED = "FIELD_REQUIRED"
    FIELD_NOT_REQUIRED = "FIELD_NOT_REQUIRED"
    RANGE = "RANGE"
    COMPARISON = "COMPARISON"


class ApplicabilityOutcome(StrEnum):
    """Result of deterministic applicability evaluation for one requirement.

    UNKNOWN means the applicability inputs (category, import status, …) were
    themselves unavailable — the requirement then goes to REVIEW_REQUIRED,
    never to silent skip or silent violation.
    """

    YES = "YES"
    NO = "NO"
    UNKNOWN = "UNKNOWN"


class ComplianceErrorCode(StrEnum):
    """Machine-readable error codes for the compliance engine (Prompt 6).

    These codes are the ONLY failure vocabulary of the engine. An engine
    failure is NEVER converted into COMPLIANT — it surfaces as FAILED /
    NOT_EVALUATED with one of these codes attached.
    """

    REGULATORY_DATA_UNAVAILABLE = "REGULATORY_DATA_UNAVAILABLE"
    NO_APPLICABLE_VERSION = "NO_APPLICABLE_VERSION"
    NO_APPLICABLE_REQUIREMENT = "NO_APPLICABLE_REQUIREMENT"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    AMBIGUOUS_VALUE = "AMBIGUOUS_VALUE"
    RULE_EXECUTION_FAILED = "RULE_EXECUTION_FAILED"
    INVALID_REGULATORY_DATA = "INVALID_REGULATORY_DATA"


class AbsenceReason(StrEnum):
    """Why a field is missing — FIELD_NOT_FOUND is never assumed to be absent.

    Phase 5 of the engine spec: missing OCR must never be automatically
    converted into legal non-compliance. A field with no evidence is
    FIELD_NOT_FOUND; only explicit structured evidence that the declaration
    is absent can produce FIELD_CONFIRMED_ABSENT.
    """

    FIELD_NOT_FOUND = "FIELD_NOT_FOUND"
    FIELD_CONFIRMED_ABSENT = "FIELD_CONFIRMED_ABSENT"
