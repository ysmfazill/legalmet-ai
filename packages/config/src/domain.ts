/**
 * Presentation metadata for domain enums — labels, semantic tones and short
 * descriptions. Kept separate from `@legalmet/types` (which is pure types) so
 * the UI has one place to resolve how a status/role/field should read and look.
 *
 * `tone` maps to the design-system status palette: the `--tone-*` CSS custom
 * properties defined in `apps/web/src/styles/tokens.css`.
 */
import type {
  ComplianceStatus,
  FieldType,
  ImageProcessingStatus,
  ImageQualityGrade,
  ImageQualityStatus,
  InspectionStatus,
  PackageStatus,
  ReviewActionType,
  UserRole,
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
  MRP: 'Maximum Retail Price',
  NET_QUANTITY: 'Net Quantity',
  GENERIC_NAME: 'Generic / Common Name',
  MANUFACTURER_DETAILS: 'Manufacturer Details',
  PACKER_DETAILS: 'Packer Details',
  IMPORTER_DETAILS: 'Importer Details',
  COUNTRY_OF_ORIGIN: 'Country of Origin',
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
