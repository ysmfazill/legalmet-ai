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
  'MRP',
  'NET_QUANTITY',
  'GENERIC_NAME',
  'MANUFACTURER_DETAILS',
  'PACKER_DETAILS',
  'IMPORTER_DETAILS',
  'COUNTRY_OF_ORIGIN',
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
  'RULE_ENGINE',
  'LLM_ASSIST',
] as const;
export type ModelServiceType = (typeof MODEL_SERVICE_TYPES)[number];

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
] as const;
export type AuditEventType = (typeof AUDIT_EVENT_TYPES)[number];

// --- Batch -----------------------------------------------------------------

export const BATCH_STATUSES = ['OPEN', 'PROCESSING', 'COMPLETED', 'ARCHIVED'] as const;
export type BatchStatus = (typeof BATCH_STATUSES)[number];
