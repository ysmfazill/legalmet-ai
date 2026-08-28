/**
 * Presentation metadata for domain enums — labels, semantic tones and short
 * descriptions. Kept separate from `@legalmet/types` (which is pure types) so
 * the UI has one place to resolve how a status/role/field should read and look.
 *
 * `tone` maps to the design-system status palette: the `--tone-*` CSS custom
 * properties defined in `apps/web/src/styles/tokens.css`.
 */
import type {
  CandidateMappingStatus,
  ComplianceStatus,
  DocumentType,
  ExtractionStatus,
  FieldType,
  ImageProcessingStatus,
  ImageQualityGrade,
  ImageQualityStatus,
  InspectionStatus,
  PackageStatus,
  ProcessingRunStatus,
  RequirementType,
  ReviewActionType,
  SourceType,
  UserRole,
  VerificationStatus,
  VersionSelectionStatus,
} from '@legalmet/types';

export type Tone = 'positive' | 'warning' | 'critical' | 'neutral' | 'info';

export interface EnumMeta {
  label: string;
  tone: Tone;
  description?: string;
}

export const COMPLIANCE_STATUS_META: Record<ComplianceStatus, EnumMeta> = {
  COMPLIANT: {
    label: 'Compliant',
    tone: 'positive',
    description: 'Deterministic validation passed against the applicable rule version.',
  },
  POTENTIAL_VIOLATION: {
    label: 'Potential Violation',
    tone: 'critical',
    description: 'Validation indicates a likely issue. Requires inspector confirmation.',
  },
  REVIEW_REQUIRED: {
    label: 'Review Required',
    tone: 'warning',
    description: 'The system cannot conclude automatically; a human decision is needed.',
  },
  NOT_APPLICABLE: {
    label: 'Not Applicable',
    tone: 'neutral',
    description: 'No applicable rule for this product context.',
  },
  LOW_CONFIDENCE: {
    label: 'Low Confidence',
    tone: 'warning',
    description: 'Perception confidence too low to assert a legal conclusion.',
  },
  IMAGE_QUALITY_INSUFFICIENT: {
    label: 'Image Quality Insufficient',
    tone: 'warning',
    description: 'Input image quality prevents reliable analysis. Rescan recommended.',
  },
};

export const INSPECTION_STATUS_META: Record<InspectionStatus, EnumMeta> = {
  CREATED: { label: 'Created', tone: 'neutral' },
  IMAGES_PENDING: { label: 'Images Pending', tone: 'info' },
  READY_FOR_ANALYSIS: {
    label: 'Ready for Analysis',
    tone: 'info',
    description: 'Package images are captured, validated and stored. No analysis has run yet.',
  },
  ANALYZING: { label: 'Analyzing', tone: 'info' },
  ANALYZED: { label: 'Analyzed', tone: 'info' },
  UNDER_REVIEW: { label: 'Under Review', tone: 'warning' },
  COMPLETED: { label: 'Completed', tone: 'positive' },
  ARCHIVED: { label: 'Archived', tone: 'neutral' },
};

/** Package intake lifecycle (Prompt 3) — independent of any compliance verdict. */
export const PACKAGE_STATUS_META: Record<PackageStatus, EnumMeta> = {
  CREATED: { label: 'Created', tone: 'neutral' },
  IMAGE_ATTACHED: { label: 'Image Attached', tone: 'info' },
  READY_FOR_ANALYSIS: { label: 'Ready for Analysis', tone: 'info' },
};

/** Preprocessing/derivative pipeline state for a stored image. */
export const IMAGE_PROCESSING_STATUS_META: Record<ImageProcessingStatus, EnumMeta> = {
  PENDING: { label: 'Pending', tone: 'neutral', description: 'Stored; derivative not yet generated.' },
  PROCESSING: { label: 'Processing', tone: 'info' },
  READY: { label: 'Ready', tone: 'positive', description: 'A metadata-stripped, resized derivative is available.' },
  FAILED: { label: 'Failed', tone: 'critical' },
};

/**
 * Usability grade from the deterministic quality analyzer. This describes how
 * legible/usable the image is for later analysis — it is explicitly NOT an
 * AI-confidence, accuracy, or Legal-Metrology-compliance judgement.
 */
export const IMAGE_QUALITY_GRADE_META: Record<ImageQualityGrade, EnumMeta> = {
  EXCELLENT: { label: 'Excellent', tone: 'positive', description: 'Highly usable image (usability only, not a compliance judgement).' },
  GOOD: { label: 'Good', tone: 'positive', description: 'Usable image (usability only, not a compliance judgement).' },
  ACCEPTABLE: { label: 'Acceptable', tone: 'info', description: 'Usable, though sharpness/lighting could be improved.' },
  POOR: { label: 'Poor', tone: 'warning', description: 'Low usability — a rescan is recommended before analysis.' },
  REJECTED: { label: 'Rejected', tone: 'critical', description: 'Not usable (e.g. below the minimum resolution).' },
};

export const REVIEW_ACTION_META: Record<ReviewActionType, EnumMeta> = {
  ACCEPT: { label: 'Accept', tone: 'positive' },
  REJECT: { label: 'Reject', tone: 'critical' },
  CORRECT: { label: 'Correct', tone: 'warning' },
  REQUEST_RESCAN: { label: 'Request Rescan', tone: 'info' },
  ESCALATE: { label: 'Escalate', tone: 'critical' },
  NOTE: { label: 'Add Note', tone: 'neutral' },
};

export const USER_ROLE_META: Record<UserRole, EnumMeta> = {
  ADMIN: { label: 'Administrator', tone: 'critical' },
  INSPECTOR: { label: 'Inspector', tone: 'info' },
  SUPERVISOR: { label: 'Supervisor', tone: 'warning' },
  AUDITOR: { label: 'Auditor', tone: 'neutral' },
};

export const IMAGE_QUALITY_META: Record<ImageQualityStatus, EnumMeta> = {
  OK: { label: 'OK', tone: 'positive' },
  LOW_RESOLUTION: { label: 'Low Resolution', tone: 'warning' },
  BLURRY: { label: 'Blurry', tone: 'warning' },
  GLARE: { label: 'Glare / Reflection', tone: 'warning' },
  INSUFFICIENT: { label: 'Insufficient', tone: 'critical' },
  UNKNOWN: { label: 'Unknown', tone: 'neutral' },
};

/** Human-readable labels for perception field categories. */
export const FIELD_TYPE_LABELS: Record<FieldType, string> = {
  PRODUCT_NAME: 'Product Name',
  BRAND_NAME: 'Brand Name',
  MRP: 'Maximum Retail Price',
  NET_QUANTITY: 'Net Quantity',
  GENERIC_NAME: 'Generic / Common Name',
  MANUFACTURER_DETAILS: 'Manufacturer Details',
  PACKER_DETAILS: 'Packer Details',
  IMPORTER_DETAILS: 'Importer Details',
  COUNTRY_OF_ORIGIN: 'Country of Origin',
  ADDRESS: 'Address',
  DATE_OF_MANUFACTURE: 'Date of Manufacture',
  DATE_OF_PACKING: 'Date of Packing',
  BEST_BEFORE: 'Best Before',
  EXPIRY_DATE: 'Expiry Date',
  CONSUMER_CARE: 'Consumer Care Details',
  BATCH_NUMBER: 'Batch / Lot Number',
  DIMENSIONS: 'Dimensions',
  UNIT_SALE_PRICE: 'Unit Sale Price',
  OTHER: 'Other',
};

// --- Perception processing runs (Prompt 4) -----------------------------------
// These describe what the perception PIPELINE did to an image. None of them
// is a compliance verdict — the strongest statement a run can make is
// "these are the declarations the system perceived".

export const PROCESSING_RUN_STATUS_META: Record<ProcessingRunStatus, EnumMeta> = {
  QUEUED: { label: 'Queued', tone: 'neutral', description: 'Run accepted; waiting to start.' },
  PREPROCESSING: { label: 'Preprocessing', tone: 'info', description: 'Preparing the OCR-oriented image derivative.' },
  OCR_PROCESSING: { label: 'Reading Text (OCR)', tone: 'info', description: 'Running real OCR over the package image.' },
  VISION_PROCESSING: { label: 'Detecting Symbols', tone: 'info', description: 'Detecting QR codes / barcodes / visual regions.' },
  FIELD_EXTRACTION: { label: 'Extracting Declarations', tone: 'info', description: 'Applying deterministic extraction rules to OCR output.' },
  COMPLETED: { label: 'Completed', tone: 'positive', description: 'Perception finished. Awaiting regulatory evaluation.' },
  PARTIAL: { label: 'Partially Completed', tone: 'warning', description: 'OCR succeeded but a later stage (e.g. symbol detection) failed; text evidence is preserved.' },
  FAILED: { label: 'Failed', tone: 'critical', description: 'The perception pipeline could not process this image.' },
  REVIEW_REQUIRED: { label: 'Review Required', tone: 'warning', description: 'Perception finished but some evidence is low-confidence; a human should verify.' },
};

/** Per-field perception outcome — explicitly NOT a compliance status. */
export const EXTRACTION_STATUS_META: Record<ExtractionStatus, EnumMeta> = {
  DETECTED: {
    label: 'Detected',
    tone: 'positive',
    description: 'Deterministic evidence found with adequate OCR confidence. Awaiting regulatory evaluation.',
  },
  REVIEW_REQUIRED: {
    label: 'Low Confidence',
    tone: 'warning',
    description: 'A pattern matched but OCR confidence is low. Verify the highlighted region before trusting the value.',
  },
  NOT_EXTRACTED: {
    label: 'Not Extracted',
    tone: 'neutral',
    description: 'The field was located (e.g. an "MRP" label was seen) but no usable value could be read.',
  },
};

// --- Regulatory intelligence (Prompt 5) ---------------------------------------
// Verification status describes whether regulatory DATA was checked against an
// official publication. It is NOT OCR confidence and NOT a compliance verdict.

export const VERIFICATION_STATUS_META: Record<VerificationStatus, EnumMeta> = {
  UNVERIFIED: {
    label: 'Unverified',
    tone: 'warning',
    description:
      'Research-grade content not yet checked against the official publication. Ineligible for production compliance evaluation.',
  },
  VERIFIED: {
    label: 'Verified Source',
    tone: 'positive',
    description:
      'A human checked the content against the official Gazette / India Code text (audited ADMIN action).',
  },
  SUPERSEDED: {
    label: 'Superseded',
    tone: 'neutral',
    description: 'A newer verified source has replaced this one.',
  },
  ARCHIVED: {
    label: 'Archived',
    tone: 'neutral',
    description: 'Retained for audit; no longer active.',
  },
};

export const SOURCE_TYPE_META: Record<SourceType, EnumMeta> = {
  GOVERNMENT_DEPARTMENT: { label: 'Government Department', tone: 'info' },
  OFFICIAL_REPOSITORY: { label: 'Official Repository', tone: 'info' },
  GAZETTE_PUBLICATION: { label: 'Gazette Publication', tone: 'info' },
  LEGAL_DATABASE: { label: 'Legal Database', tone: 'neutral' },
  OTHER: { label: 'Other', tone: 'neutral' },
};

export const DOCUMENT_TYPE_META: Record<DocumentType, EnumMeta> = {
  RULES: { label: 'Rules', tone: 'info' },
  ACT: { label: 'Act', tone: 'info' },
  AMENDMENT_NOTIFICATION: { label: 'Amendment Notification', tone: 'info' },
  CIRCULAR: { label: 'Circular', tone: 'neutral' },
  GUIDANCE: { label: 'Guidance', tone: 'neutral' },
  OTHER: { label: 'Other', tone: 'neutral' },
};

export const REQUIREMENT_TYPE_META: Record<RequirementType, EnumMeta> = {
  DECLARATION: {
    label: 'Declaration',
    tone: 'info',
    description: 'A mandatory on-package declaration.',
  },
  FORMAT: { label: 'Format', tone: 'info', description: 'How a declaration must be expressed.' },
  PROHIBITION: { label: 'Prohibition', tone: 'critical' },
  PROCEDURAL: { label: 'Procedural', tone: 'neutral' },
};

export const VERSION_SELECTION_META: Record<VersionSelectionStatus, EnumMeta> = {
  FOUND: {
    label: 'Version Found',
    tone: 'positive',
    description: 'A version is in force at the requested date.',
  },
  NO_APPLICABLE_VERSION: {
    label: 'No Applicable Version',
    tone: 'warning',
    description:
      'No version is in force at the requested date. The resolver never silently falls back to the newest version.',
  },
};

/** Boundary markers on field → requirement mappings. Never compliance verdicts. */
export const CANDIDATE_MAPPING_META: Record<CandidateMappingStatus, EnumMeta> = {
  CANDIDATE: {
    label: 'Candidate Requirement',
    tone: 'info',
    description: 'A requirement definition whose field key matches this detected field.',
  },
  APPLICABILITY_NOT_EVALUATED: {
    label: 'Applicability Not Evaluated',
    tone: 'neutral',
    description: 'Whether the requirement applies to this package has not been determined.',
  },
  AWAITING_COMPLIANCE_ENGINE: {
    label: 'Awaiting Compliance Engine',
    tone: 'neutral',
    description: 'No compliance conclusion exists for this field yet.',
  },
};
