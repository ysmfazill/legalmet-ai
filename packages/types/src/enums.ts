/**
 * Canonical enumerations for the LEGALMET AI domain.
 *
 * These values are the single source of truth for the frontend. The Python
 * backend mirrors the exact same string values in `app/core/enums.py`. When a
 * value changes here it MUST change there too — see docs/architecture.md
 * ("Shared contract & single source of truth").
 *
 * Each enum is expressed as a `const` array plus a derived union type so the
 * values are available at runtime (for dropdowns, validation, iteration) while
 * remaining strictly typed.
 */

// --- People & access -------------------------------------------------------

export const USER_ROLES = ['ADMIN', 'INSPECTOR', 'SUPERVISOR', 'AUDITOR'] as const;
export type UserRole = (typeof USER_ROLES)[number];

// --- Inspection lifecycle --------------------------------------------------

export const INSPECTION_STATUSES = [
  'CREATED',
  'IMAGES_PENDING',
  'READY_FOR_ANALYSIS',
  'ANALYZING',
  'ANALYZED',
  'UNDER_REVIEW',
  'COMPLETED',
  'ARCHIVED',
] as const;
export type InspectionStatus = (typeof INSPECTION_STATUSES)[number];

// --- Package intake lifecycle (Prompt 3) -----------------------------------
// The intake state of a physical package's images. Independent of compliance:
// a package can be READY_FOR_ANALYSIS without any legal conclusion existing.

export const PACKAGE_STATUSES = ['CREATED', 'IMAGE_ATTACHED', 'READY_FOR_ANALYSIS'] as const;
export type PackageStatus = (typeof PACKAGE_STATUSES)[number];

/** How a package image entered the system. */
export const CAPTURE_SOURCES = ['CAMERA', 'UPLOAD', 'BATCH'] as const;
export type CaptureSource = (typeof CAPTURE_SOURCES)[number];

/** Preprocessing / derivative-pipeline state for a stored image. */
export const IMAGE_PROCESSING_STATUSES = ['PENDING', 'PROCESSING', 'READY', 'FAILED'] as const;
export type ImageProcessingStatus = (typeof IMAGE_PROCESSING_STATUSES)[number];

/**
 * Overall image *usability* grade from the deterministic quality analyzer.
 * This is a legibility signal for later analysis — it is explicitly NOT an
 * AI-confidence, accuracy, or Legal-Metrology-compliance judgement.
 */
export const IMAGE_QUALITY_GRADES = [
  'EXCELLENT',
  'GOOD',
  'ACCEPTABLE',
  'POOR',
  'REJECTED',
] as const;
export type ImageQualityGrade = (typeof IMAGE_QUALITY_GRADES)[number];

// --- Compliance outcome states ---------------------------------------------
// NOTE: The system intentionally does NOT collapse to PASS/FAIL. Low-confidence
// or low-quality inputs must never produce a definitive legal conclusion.

export const COMPLIANCE_STATUSES = [
  'COMPLIANT',
  'POTENTIAL_VIOLATION',
  'REVIEW_REQUIRED',
  'NOT_APPLICABLE',
  'LOW_CONFIDENCE',
  'IMAGE_QUALITY_INSUFFICIENT',
] as const;
export type ComplianceStatus = (typeof COMPLIANCE_STATUSES)[number];

// --- Perception field categories -------------------------------------------
// These are *perception targets* the vision/OCR layer attempts to locate on a
// label. They describe what a text region appears to represent — NOT a legal
// assertion. Legal significance is decided only by the deterministic rule
// engine operating on verified regulatory data.

export const FIELD_TYPES = [
  'PRODUCT_NAME',
  'BRAND_NAME',
  'MRP',
  'NET_QUANTITY',
  'GENERIC_NAME',
  'MANUFACTURER_DETAILS',
  'PACKER_DETAILS',
  'IMPORTER_DETAILS',
  'COUNTRY_OF_ORIGIN',
  'ADDRESS',
  'DATE_OF_MANUFACTURE',
  'DATE_OF_PACKING',
  'BEST_BEFORE',
  'EXPIRY_DATE',
  'CONSUMER_CARE',
  'BATCH_NUMBER',
  'DIMENSIONS',
  'UNIT_SALE_PRICE',
  'OTHER',
] as const;
export type FieldType = (typeof FIELD_TYPES)[number];

// --- Human review actions --------------------------------------------------

export const REVIEW_ACTION_TYPES = [
  'ACCEPT',
  'REJECT',
  'CORRECT',
  'REQUEST_RESCAN',
  'ESCALATE',
  'NOTE',
] as const;
export type ReviewActionType = (typeof REVIEW_ACTION_TYPES)[number];

// --- Imaging ---------------------------------------------------------------

export const IMAGE_TYPES = ['FRONT', 'BACK', 'SIDE', 'TOP', 'BOTTOM', 'LABEL', 'OTHER'] as const;
export type ImageType = (typeof IMAGE_TYPES)[number];

export const IMAGE_QUALITY_STATUSES = [
  'OK',
  'LOW_RESOLUTION',
  'BLURRY',
  'GLARE',
  'INSUFFICIENT',
  'UNKNOWN',
] as const;
export type ImageQualityStatus = (typeof IMAGE_QUALITY_STATUSES)[number];

export const REGION_TYPES = [
  'TEXT_BLOCK',
  'TEXT_LINE',
  'SYMBOL',
  'LOGO',
  'BARCODE',
  'QR_CODE',
  'GRAPHIC',
  'OTHER',
] as const;
export type RegionType = (typeof REGION_TYPES)[number];

// --- Regulatory knowledge --------------------------------------------------

export const REGULATION_VERSION_STATUSES = [
  'DRAFT',
  'ACTIVE',
  'SUPERSEDED',
  'REPEALED',
] as const;
export type RegulationVersionStatus = (typeof REGULATION_VERSION_STATUSES)[number];

export const RULE_STATUSES = ['ACTIVE', 'INACTIVE', 'DRAFT'] as const;
export type RuleStatus = (typeof RULE_STATUSES)[number];

// --- Evidence graph --------------------------------------------------------

export const EVIDENCE_TYPES = [
  'OCR_TEXT',
  'IMAGE_REGION',
  'EXTRACTED_FIELD',
  'VISUAL_ELEMENT',
  'RULE_REFERENCE',
  'VALIDATION_RESULT',
] as const;
export type EvidenceType = (typeof EVIDENCE_TYPES)[number];

// --- Model / service provenance --------------------------------------------

export const MODEL_SERVICE_TYPES = [
  'OCR',
  'VISION',
  'PRODUCT_CLASSIFIER',
  'FIELD_EXTRACTOR',
  'RULE_ENGINE',
  'LLM_ASSIST',
] as const;
export type ModelServiceType = (typeof MODEL_SERVICE_TYPES)[number];

// --- Perception processing runs (Prompt 4) ---------------------------------
// Lifecycle of ONE perception run over ONE image. These assert what the
// pipeline DID to the image — never anything about compliance.

export const PROCESSING_RUN_STATUSES = [
  'QUEUED',
  'PREPROCESSING',
  'OCR_PROCESSING',
  'VISION_PROCESSING',
  'FIELD_EXTRACTION',
  'COMPLETED',
  'PARTIAL',
  'FAILED',
  'REVIEW_REQUIRED',
] as const;
export type ProcessingRunStatus = (typeof PROCESSING_RUN_STATUSES)[number];

// Per-field perception outcome. NOT a compliance verdict: DETECTED means the
// deterministic extractor found evidence with adequate OCR confidence;
// REVIEW_REQUIRED means a pattern matched but OCR confidence was low;
// NOT_EXTRACTED means the field was located but no usable value was read.

export const EXTRACTION_STATUSES = ['DETECTED', 'REVIEW_REQUIRED', 'NOT_EXTRACTED'] as const;
export type ExtractionStatus = (typeof EXTRACTION_STATUSES)[number];

// --- Audit -----------------------------------------------------------------

export const AUDIT_EVENT_TYPES = [
  'INSPECTION_CREATED',
  'IMAGE_UPLOADED',
  'ANALYSIS_STARTED',
  'ANALYSIS_COMPLETED',
  'FINDING_CREATED',
  'REVIEW_RECORDED',
  'INSPECTION_COMPLETED',
  'INSPECTION_ARCHIVED',
  // Prompt 3 — real package intake pipeline
  'PACKAGE_CREATED',
  'IMAGE_UPLOAD_STARTED',
  'IMAGE_REJECTED',
  'QUALITY_CHECK_COMPLETED',
  'IMAGE_PREPARED',
  'IMAGE_DELETED',
  'INSPECTION_READY',
  // Prompt 4 — real perception pipeline
  'PERCEPTION_STARTED',
  'PERCEPTION_COMPLETED',
  'PERCEPTION_FAILED',
  'IMAGE_REANALYZED',
] as const;
export type AuditEventType = (typeof AUDIT_EVENT_TYPES)[number];

// --- Batch -----------------------------------------------------------------

export const BATCH_STATUSES = ['OPEN', 'PROCESSING', 'COMPLETED', 'ARCHIVED'] as const;
export type BatchStatus = (typeof BATCH_STATUSES)[number];

// --- Regulatory intelligence (Prompt 5) -------------------------------------
// Provenance hierarchy: SOURCE → DOCUMENT → VERSION → REQUIREMENT. Verification
// status describes the *data's* verification against an official publication —
// it is completely separate from OCR/perception confidence.

/** Who publishes the regulatory material a document was sourced from. */
export const SOURCE_TYPES = [
  'GOVERNMENT_DEPARTMENT',
  'OFFICIAL_REPOSITORY',
  'GAZETTE_PUBLICATION',
  'LEGAL_DATABASE',
  'OTHER',
] as const;
export type SourceType = (typeof SOURCE_TYPES)[number];

/**
 * Whether a source's content has been checked against an official publication.
 * Only VERIFIED data is eligible for production compliance evaluation;
 * flipping to VERIFIED is an audited ADMIN action.
 */
export const VERIFICATION_STATUSES = ['UNVERIFIED', 'VERIFIED', 'SUPERSEDED', 'ARCHIVED'] as const;
export type VerificationStatus = (typeof VERIFICATION_STATUSES)[number];

/** Kind of legal instrument a document represents. */
export const DOCUMENT_TYPES = [
  'RULES',
  'ACT',
  'AMENDMENT_NOTIFICATION',
  'CIRCULAR',
  'GUIDANCE',
  'OTHER',
] as const;
export type DocumentType = (typeof DOCUMENT_TYPES)[number];

/** Nature of a requirement definition. */
export const REQUIREMENT_TYPES = ['DECLARATION', 'FORMAT', 'PROHIBITION', 'PROCEDURAL'] as const;
export type RequirementType = (typeof REQUIREMENT_TYPES)[number];

/** Outcome of deterministic effective-date version selection. */
export const VERSION_SELECTION_STATUSES = ['FOUND', 'NO_APPLICABLE_VERSION'] as const;
export type VersionSelectionStatus = (typeof VERSION_SELECTION_STATUSES)[number];

/**
 * Markers on a detected-field → requirement mapping. Every value is a boundary
 * statement — none of them is a compliance verdict (the Prompt 6 engine owns
 * conclusions).
 */
export const CANDIDATE_MAPPING_STATUSES = [
  'CANDIDATE',
  'APPLICABILITY_NOT_EVALUATED',
  'AWAITING_COMPLIANCE_ENGINE',
] as const;
export type CandidateMappingStatus = (typeof CANDIDATE_MAPPING_STATUSES)[number];

// --- Audit events (Prompt 5 additions) ---------------------------------------

export const REGULATORY_AUDIT_EVENT_TYPES = [
  'REGULATORY_SOURCE_CREATED',
  'REGULATORY_SOURCE_UPDATED',
  'REGULATORY_DOCUMENT_CREATED',
  'REGULATORY_VERSION_CREATED',
  'REGULATORY_VERSION_SUPERSEDED',
  'REGULATORY_REQUIREMENT_CREATED',
  'REGULATORY_REQUIREMENT_UPDATED',
  'REGULATORY_DATA_SEEDED',
] as const;
export type RegulatoryAuditEventType = (typeof REGULATORY_AUDIT_EVENT_TYPES)[number];
