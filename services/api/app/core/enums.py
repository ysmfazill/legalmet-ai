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
    # UI-05 — targeted inspection assignment (department act, audited)
    INSPECTION_ASSIGNED = "INSPECTION_ASSIGNED"
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
    # Prompt 8 — human-in-the-loop review, correction and final decision.
    # Every event records WHO acted (actor), with WHAT authority (role), on
    # WHICH entity, and WHY (reason) in the payload. The AI never appears as
    # the actor of any of these events.
    FIELD_REVIEWED = "FIELD_REVIEWED"
    FIELD_CORRECTED = "FIELD_CORRECTED"
    FINDING_CONFIRMED = "FINDING_CONFIRMED"
    FINDING_REJECTED = "FINDING_REJECTED"
    FINDING_OVERRIDDEN = "FINDING_OVERRIDDEN"
    FINDING_ESCALATED = "FINDING_ESCALATED"
    DECISION_SUBMITTED = "DECISION_SUBMITTED"
    DECISION_CHANGED = "DECISION_CHANGED"
    SUPERVISOR_REVIEWED = "SUPERVISOR_REVIEWED"
    # UI-02 — Citizen Mode (anonymous screening + suspected-issue reports).
    # No actor is recorded for citizen events (anonymous by design); the
    # payload carries the public scan/report reference.
    CITIZEN_SCAN_COMPLETED = "CITIZEN_SCAN_COMPLETED"
    CITIZEN_REPORT_SUBMITTED = "CITIZEN_REPORT_SUBMITTED"
    # UI-03 — complaint lifecycle. Department actions record the acting user
    # (actor); CITIZEN_INFO_PROVIDED stays anonymous like the other citizen
    # events. Every transition of a citizen report is audited here AND kept
    # in the citizen_report_events history table the timeline reads.
    COMPLAINT_REVIEW_STARTED = "COMPLAINT_REVIEW_STARTED"
    COMPLAINT_ACCEPTED = "COMPLAINT_ACCEPTED"
    COMPLAINT_REJECTED = "COMPLAINT_REJECTED"
    COMPLAINT_INFO_REQUESTED = "COMPLAINT_INFO_REQUESTED"
    CITIZEN_INFO_PROVIDED = "CITIZEN_INFO_PROVIDED"
    COMPLAINT_ASSIGNED = "COMPLAINT_ASSIGNED"
    COMPLAINT_INSPECTION_CREATED = "COMPLAINT_INSPECTION_CREATED"
    COMPLAINT_INSPECTION_COMPLETED = "COMPLAINT_INSPECTION_COMPLETED"
    COMPLAINT_ACTION_TAKEN = "COMPLAINT_ACTION_TAKEN"
    COMPLAINT_CLOSED = "COMPLAINT_CLOSED"
    # UI-06 — evidence planner verification lifecycle. Every event records the
    # acting human (never the engine) and the task/inspection it belongs to.
    VERIFICATION_CREATED = "VERIFICATION_CREATED"
    VERIFICATION_STARTED = "VERIFICATION_STARTED"
    VERIFICATION_RESULT_RECORDED = "VERIFICATION_RESULT_RECORDED"
    VERIFICATION_COMPLETED = "VERIFICATION_COMPLETED"
    VERIFICATION_CANCELLED = "VERIFICATION_CANCELLED"
    # UI-07 — physical verification + lot intelligence. Lot lifecycle events and
    # the deterministic measurement evaluation always record the acting human;
    # the evaluation event additionally freezes the rule version used.
    LOT_CREATED = "LOT_CREATED"
    LOT_PACKAGE_ADDED = "LOT_PACKAGE_ADDED"
    LOT_SAMPLE_GENERATED = "LOT_SAMPLE_GENERATED"
    MEASUREMENT_EVALUATED = "MEASUREMENT_EVALUATED"
    LOT_DECISION_SUBMITTED = "LOT_DECISION_SUBMITTED"
    # UI-08 — reporting & evidence pack. Every report lifecycle transition is
    # audited (creation, generation, review, finalization, both export
    # formats, amendment). The actor is always the authenticated human.
    REPORT_CREATED = "REPORT_CREATED"
    REPORT_GENERATED = "REPORT_GENERATED"
    REPORT_REVIEWED = "REPORT_REVIEWED"
    REPORT_FINALIZED = "REPORT_FINALIZED"
    REPORT_EXPORTED_PDF = "REPORT_EXPORTED_PDF"
    REPORT_EXPORTED_DOCX = "REPORT_EXPORTED_DOCX"
    REPORT_AMENDED = "REPORT_AMENDED"


class ReportStatus(StrEnum):
    """Lifecycle of one report record (UI-08).

    DRAFT          created, not yet generated (no snapshot exists)
    UNDER_REVIEW   generated; an authorized human is reviewing the content
    FINALIZED      passed the evidence gate and locked by an authorized human
    EXPORTED       at least one PDF/DOCX export happened after finalization
    AMENDED        a new version superseded a FINALIZED one (reason mandatory)

    AMENDED reports are re-generatable and re-finalizable — the version
    history preserves every superseded snapshot verbatim.
    """

    DRAFT = "DRAFT"
    UNDER_REVIEW = "UNDER_REVIEW"
    FINALIZED = "FINALIZED"
    EXPORTED = "EXPORTED"
    AMENDED = "AMENDED"


class ReportEvidenceType(StrEnum):
    """What one evidence-manifest entry references (UI-08)."""

    IMAGE = "IMAGE"
    IMAGE_REGION = "IMAGE_REGION"
    EXTRACTED_FIELD = "EXTRACTED_FIELD"
    MEASUREMENT = "MEASUREMENT"
    LOT = "LOT"
    COMPLAINT = "COMPLAINT"
    FINDING = "FINDING"


class LotStatus(StrEnum):
    """Lifecycle of one lot under physical verification (UI-07).

    A lot starts IN_PROGRESS and only reaches a decision state through an
    explicit inspector submission — never automatically. While required
    measurements are outstanding the computed assessment state is
    INSUFFICIENT_EVIDENCE (not a stored status: it is derived, so it can never
    be set prematurely).
    """

    IN_PROGRESS = "IN_PROGRESS"
    COMPLIANT = "COMPLIANT"
    NON_COMPLIANT = "NON_COMPLIANT"
    REQUIRES_REVIEW = "REQUIRES_REVIEW"


class LotPackageStatus(StrEnum):
    """One package inside a lot, from the sampling perspective."""

    NOT_SAMPLED = "NOT_SAMPLED"  # in the lot, outside the drawn sample
    PENDING = "PENDING"          # sampled, measurement still outstanding
    MEASURED = "MEASURED"        # a physical measurement is recorded


class SamplingMethod(StrEnum):
    """How a sample was selected."""

    RANDOM = "RANDOM"  # seeded, reproducible random draw
    MANUAL = "MANUAL"  # inspector-picked packages


class MeasurementEvaluationStatus(StrEnum):
    """Outcome of the deterministic declared-vs-measured regulatory check.

    UNAVAILABLE means the applicable permissible-error procedure is NOT
    configured — the system states that honestly and defers to the inspector
    instead of guessing a tolerance.
    """

    EVALUATED = "EVALUATED"
    UNAVAILABLE = "UNAVAILABLE"


class MeasurementOutcome(StrEnum):
    """Result of an EVALUATED measurement (decision support, never a verdict)."""

    WITHIN_TOLERANCE = "WITHIN_TOLERANCE"
    EXCEEDS_TOLERANCE = "EXCEEDS_TOLERANCE"


class RegulatoryProcedureKind(StrEnum):
    """Kinds of versioned regulatory procedures that govern physical work.

    MEASUREMENT_TOLERANCE  the permissible error applied to a declared-vs-
                           measured difference (never hardcoded — read from the
                           configured procedure)
    SAMPLING               the legal sampling method/size for a lot
    """

    MEASUREMENT_TOLERANCE = "MEASUREMENT_TOLERANCE"
    SAMPLING = "SAMPLING"


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


# --- Evidence graph / traceability (Prompt 7) ---------------------------------


class EvidenceNodeType(StrEnum):
    """Node vocabulary of the Evidence Graph.

    Every node corresponds to ONE persisted database record — the graph is a
    read-only traceability view over existing entities, never a stored copy of
    them and never a fabricated demonstration structure.
    """

    INSPECTION = "INSPECTION"
    IMAGE = "IMAGE"
    IMAGE_REGION = "IMAGE_REGION"
    OCR_RESULT = "OCR_RESULT"
    EXTRACTED_FIELD = "EXTRACTED_FIELD"
    REGULATORY_SOURCE = "REGULATORY_SOURCE"
    REGULATORY_DOCUMENT = "REGULATORY_DOCUMENT"
    REGULATORY_VERSION = "REGULATORY_VERSION"
    REQUIREMENT = "REQUIREMENT"
    RULE = "RULE"
    EVALUATION = "EVALUATION"
    FINDING = "FINDING"
    PROCESSING_RUN = "PROCESSING_RUN"
    AUDIT_EVENT = "AUDIT_EVENT"
    # Prompt 8 — human-in-the-loop records. Every one of these nodes is a
    # persisted human action with an actor, and carries origin=HUMAN in its
    # metadata. AI outputs and human actions are NEVER represented as
    # identical in the graph.
    FIELD_CORRECTION = "FIELD_CORRECTION"
    FINDING_REVIEW = "FINDING_REVIEW"
    INSPECTION_DECISION = "INSPECTION_DECISION"
    # UI-07 — physical evidence + lot intelligence. Every node is still ONE
    # persisted record: a recorded measurement (VerificationResult), the
    # instrument it names, and the lot / sampling-run / package chain.
    MEASUREMENT = "MEASUREMENT"
    INSTRUMENT = "INSTRUMENT"
    LOT = "LOT"
    LOT_PACKAGE = "LOT_PACKAGE"
    SAMPLING_RUN = "SAMPLING_RUN"
    # The frozen deterministic evaluation of ONE recorded measurement
    # (MeasurementEvaluation): rule code, regulation version and inputs are
    # stored on the row — a later rule update never rewrites it.
    MEASUREMENT_EVALUATION = "MEASUREMENT_EVALUATION"


class EvidenceNodeOrigin(StrEnum):
    """Who produced a graph node (Phase 15 — AI vs HUMAN distinction).

    AI      — machine output (OCR line, region, extracted field, evaluation,
              finding): produced by a pipeline, confidence-annotated.
    HUMAN   — an authorised human action with an actor id (correction,
              review, decision).
    SYSTEM  — neutral recorded data (inspection, image, regulatory records,
              system audit events): neither an AI inference nor a human
              review judgement.

    The distinction is a traceability guarantee: an AI node is never
    relabelled as a human decision and vice versa.
    """

    AI = "AI"
    HUMAN = "HUMAN"
    SYSTEM = "SYSTEM"


class EvidenceEdgeType(StrEnum):
    """Relationship vocabulary of the Evidence Graph.

    Every edge points at two REAL entity ids (node ids are ``"<type>:<uuid>"``).
    Edge semantics are fixed by this enum — never free-form strings.
    """

    INSPECTION_CONTAINS_IMAGE = "INSPECTION_CONTAINS_IMAGE"
    INSPECTION_HAS_EVALUATION = "INSPECTION_HAS_EVALUATION"
    IMAGE_HAS_REGION = "IMAGE_HAS_REGION"
    IMAGE_HAS_OCR_RESULT = "IMAGE_HAS_OCR_RESULT"
    REGION_HAS_OCR_RESULT = "REGION_HAS_OCR_RESULT"
    OCR_SUPPORTS_FIELD = "OCR_SUPPORTS_FIELD"
    REGION_SUPPORTS_FIELD = "REGION_SUPPORTS_FIELD"
    PROCESSING_RUN_PROCESSED_IMAGE = "PROCESSING_RUN_PROCESSED_IMAGE"
    PROCESSING_RUN_PRODUCED_REGION = "PROCESSING_RUN_PRODUCED_REGION"
    PROCESSING_RUN_PRODUCED_OCR = "PROCESSING_RUN_PRODUCED_OCR"
    FIELD_EVALUATED_AGAINST_REQUIREMENT = "FIELD_EVALUATED_AGAINST_REQUIREMENT"
    REQUIREMENT_EVALUATED_BY_RULE = "REQUIREMENT_EVALUATED_BY_RULE"
    RULE_PRODUCED_FINDING = "RULE_PRODUCED_FINDING"
    FINDING_BELONGS_TO_EVALUATION = "FINDING_BELONGS_TO_EVALUATION"
    EVALUATION_USES_REGULATORY_VERSION = "EVALUATION_USES_REGULATORY_VERSION"
    REQUIREMENT_BELONGS_TO_VERSION = "REQUIREMENT_BELONGS_TO_VERSION"
    VERSION_ORIGINATES_FROM_DOCUMENT = "VERSION_ORIGINATES_FROM_DOCUMENT"
    DOCUMENT_HAS_SOURCE = "DOCUMENT_HAS_SOURCE"
    FINDING_SUPPORTED_BY_EVIDENCE = "FINDING_SUPPORTED_BY_EVIDENCE"
    AUDIT_RECORDS_ACTION = "AUDIT_RECORDS_ACTION"
    # Prompt 8 — human-in-the-loop relations. Sources of these edges are
    # always origin=HUMAN nodes (correction / review / decision records).
    FIELD_CORRECTION_CORRECTS_FIELD = "FIELD_CORRECTION_CORRECTS_FIELD"
    FINDING_REVIEW_REVIEWS_FINDING = "FINDING_REVIEW_REVIEWS_FINDING"
    FINDING_REVIEW_LINKS_CORRECTION = "FINDING_REVIEW_LINKS_CORRECTION"
    DECISION_FOR_INSPECTION = "DECISION_FOR_INSPECTION"
    DECISION_BASED_ON_EVALUATION = "DECISION_BASED_ON_EVALUATION"
    DECISION_SUPERSEDES_DECISION = "DECISION_SUPERSEDES_DECISION"
    # UI-07 — physical verification + lot intelligence relations. The physical
    # half of the quantity chain: a MEASUREMENT (a recorded VerificationResult,
    # origin=HUMAN) verifies a DECLARATION (extracted field) or a LOT PACKAGE,
    # names the INSTRUMENT it was read from, and is evaluated by a frozen
    # MEASUREMENT_EVALUATION that references the rule version it used.
    MEASUREMENT_VERIFIES_FIELD = "MEASUREMENT_VERIFIES_FIELD"
    MEASUREMENT_VERIFIES_LOT_PACKAGE = "MEASUREMENT_VERIFIES_LOT_PACKAGE"
    INSTRUMENT_USED_FOR_MEASUREMENT = "INSTRUMENT_USED_FOR_MEASUREMENT"
    MEASUREMENT_HAS_EVALUATION = "MEASUREMENT_HAS_EVALUATION"
    INSPECTION_HAS_LOT = "INSPECTION_HAS_LOT"
    LOT_HAS_PACKAGE = "LOT_HAS_PACKAGE"
    LOT_HAS_SAMPLING_RUN = "LOT_HAS_SAMPLING_RUN"
    SAMPLING_RUN_SELECTED_PACKAGE = "SAMPLING_RUN_SELECTED_PACKAGE"
    LOT_DECISION_FOR_INSPECTION = "LOT_DECISION_FOR_INSPECTION"


class EvidenceStrength(StrEnum):
    """Evidence-quality label on the FINDING_SUPPORTED_BY_EVIDENCE relation.

    A traceability signal ONLY — it never upgrades a finding's compliance
    status and MISSING evidence is never converted into compliance.

    DIRECT — the finding has direct evidence from an image region / OCR line.
    DERIVED — the value was deterministically normalized/derived from source.
    AMBIGUOUS — evidence exists but is insufficient (low confidence / review).
    MISSING — no valid evidence exists (e.g. a NOT_DETECTED finding).
    """

    DIRECT = "DIRECT"
    DERIVED = "DERIVED"
    AMBIGUOUS = "AMBIGUOUS"
    MISSING = "MISSING"


# --- Human-in-the-loop review & decision (Prompt 8) ----------------------------


class FindingReviewState(StrEnum):
    """Human review state of ONE engine finding — the inspector's verdict.

    The engine finding itself (status, explanation, evidence) is a frozen
    system output; this state records what the AUTHORISED HUMAN decided about
    it. PENDING_REVIEW is the default: the system has spoken, the human has
    not. Transitions are enforced in the backend service layer — never in the
    frontend.
    """

    PENDING_REVIEW = "PENDING_REVIEW"
    CONFIRMED = "CONFIRMED"  # inspector agrees with the system finding
    CORRECTED = "CORRECTED"  # the underlying value was human-corrected
    REJECTED = "REJECTED"  # inspector rejects the system finding
    OVERRIDDEN = "OVERRIDDEN"  # supervisor overrode a confirmed outcome
    ESCALATED = "ESCALATED"  # routed to a supervisor / senior review


class InspectionDecisionType(StrEnum):
    """The FINAL human decision on an inspection — the only legal conclusion.

    The deterministic engine NEVER produces any of these values. An inspector
    (or supervisor) records the decision explicitly, with reason and audit
    trail. NOT_EVALUATED records the honest "no decision yet" state.
    """

    COMPLIANT = "COMPLIANT"
    NON_COMPLIANT = "NON_COMPLIANT"
    REQUIRES_FURTHER_REVIEW = "REQUIRES_FURTHER_REVIEW"
    NOT_EVALUATED = "NOT_EVALUATED"


# --- UI-06 — Evidence Planner & verification tasks ------------------------------


class EvidenceItemStatus(StrEnum):
    """Status of ONE piece of evidence behind a finding or declaration.

    A traceability label ONLY — it never upgrades or downgrades a compliance
    status and it is never a probability of violation.
    """

    AVAILABLE = "AVAILABLE"  # the artifact exists and supports the row
    MISSING = "MISSING"  # the artifact does not exist (yet)
    REQUIRES_VERIFICATION = "REQUIRES_VERIFICATION"  # an inspector action can close this
    VERIFIED = "VERIFIED"  # an authorised human recorded the verification
    REJECTED = "REJECTED"  # an authorised human rejected the finding
    NOT_APPLICABLE = "NOT_APPLICABLE"  # the requirement does not apply


class EvidenceRequirementKind(StrEnum):
    """What KIND of evidence an evidence-plan row needs.

    Deliberately limited to what the system actually supports: perception
    artifacts (IMAGE / OCR / REGION / FIELD), the deterministic evaluation, and
    the two human verification channels (MEASUREMENT, INSPECTOR_OBSERVATION).
    """

    IMAGE = "IMAGE"
    OCR = "OCR"
    REGION = "REGION"
    FIELD = "FIELD"
    EVALUATION = "EVALUATION"
    MEASUREMENT = "MEASUREMENT"
    INSPECTOR_OBSERVATION = "INSPECTOR_OBSERVATION"


class VerificationTaskType(StrEnum):
    """The kind of physical/field verification a task asks the inspector to do.

    The system can READ a declared value; it can never MEASURE contents. A
    MEASUREMENT task is closed only by a human recording a reading from an
    appropriate Legal Metrology instrument (manual entry in this prototype).
    """

    MEASUREMENT = "MEASUREMENT"
    INSPECTOR_OBSERVATION = "INSPECTOR_OBSERVATION"


class VerificationTaskStatus(StrEnum):
    """Lifecycle of one verification task (UI-06).

    PENDING → IN_PROGRESS → COMPLETED, or PENDING/IN_PROGRESS → CANCELLED.
    Transitions are enforced in the service layer, never in the frontend.
    """

    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"

    @property
    def is_open(self) -> bool:
        return self in (VerificationTaskStatus.PENDING, VerificationTaskStatus.IN_PROGRESS)


class VerificationLevel(StrEnum):
    """Whether a verification task MUST be closed before a final decision.

    REQUIRED tasks block COMPLIANT / NON_COMPLIANT decisions while open.
    RECOMMENDED tasks are advisory — they never block finalization.
    """

    REQUIRED = "REQUIRED"
    RECOMMENDED = "RECOMMENDED"
