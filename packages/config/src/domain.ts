/**
 * Presentation metadata for domain enums — labels, semantic tones and short
 * descriptions. Kept separate from `@legalmet/types` (which is pure types) so
 * the UI has one place to resolve how a status/role/field should read and look.
 *
 * `tone` maps to the design-system status palette: the `--tone-*` CSS custom
 * properties defined in `apps/web/src/styles/tokens.css`.
 */
import type {
  ApplicabilityOutcome,
  CandidateMappingStatus,
  ComplianceStatus,
  DocumentType,
  EngineFindingStatus,
  EvaluationStatus,
  EvidenceGraphEdgeKind,
  EvidenceGraphNodeKind,
  EvidenceNodeOrigin,
  EvidenceStrength,
  ExtractionStatus,
  FieldType,
  FindingReviewState,
  FindingSeverity,
  ImageProcessingStatus,
  ImageQualityGrade,
  ImageQualityStatus,
  InspectionDecisionType,
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

// --- Deterministic compliance engine (Prompt 6) --------------------------------
// Engine findings are SYSTEM decision-support outputs. None of the labels below
// is an enforcement determination — the inspector remains responsible for the
// final decision, and the UI must always say so.

export const ENGINE_FINDING_STATUS_META: Record<EngineFindingStatus, EnumMeta> = {
  COMPLIANT: {
    label: 'Compliant',
    tone: 'positive',
    description:
      'Every deterministic rule passed with adequate valid evidence. A system finding — not an enforcement determination.',
  },
  NON_COMPLIANT: {
    label: 'Non-Compliant',
    tone: 'critical',
    description:
      'At least one deterministic rule failed against the detected value. Requires inspector review before any enforcement decision.',
  },
  REVIEW_REQUIRED: {
    label: 'Review Required',
    tone: 'warning',
    description:
      'Evidence was insufficient or ambiguous — the engine does not guess. An inspector must decide.',
  },
  NOT_DETECTED: {
    label: 'Not Detected',
    tone: 'warning',
    description:
      'No field of this type was perceived. This is NOT evidence that the declaration is absent from the package.',
  },
  NOT_APPLICABLE: {
    label: 'Not Applicable',
    tone: 'neutral',
    description: 'The requirement does not apply to this package (recorded with its reason).',
  },
  NOT_EVALUATED: {
    label: 'Not Evaluated',
    tone: 'neutral',
    description: 'The engine has no deterministic check configured for this requirement.',
  },
};

export const EVALUATION_STATUS_META: Record<EvaluationStatus, EnumMeta> = {
  NOT_EVALUATED: {
    label: 'Not Evaluated',
    tone: 'neutral',
    description: 'No compliance evaluation has been run for this inspection yet.',
  },
  EVALUATING: {
    label: 'Evaluating…',
    tone: 'info',
    description: 'The deterministic engine is running.',
  },
  COMPLETED: {
    label: 'Completed',
    tone: 'positive',
    description: 'Every applicable requirement was evaluated deterministically.',
  },
  PARTIAL: {
    label: 'Partial',
    tone: 'warning',
    description: 'Some requirements could not be evaluated (no configured rule).',
  },
  REVIEW_REQUIRED: {
    label: 'Review Required',
    tone: 'warning',
    description: 'One or more findings need an inspector decision.',
  },
  FAILED: {
    label: 'Failed',
    tone: 'critical',
    description: 'The engine could not run (structural error recorded with a code). A failure is never compliance.',
  },
  NO_APPLICABLE_REQUIREMENT: {
    label: 'No Applicable Requirement',
    tone: 'neutral',
    description: 'No regulatory requirement applies to this inspection.',
  },
};

export const FINDING_SEVERITY_META: Record<FindingSeverity, EnumMeta> = {
  INFO: { label: 'Info', tone: 'neutral' },
  MINOR: { label: 'Minor', tone: 'info' },
  MAJOR: { label: 'Major', tone: 'warning' },
  CRITICAL: { label: 'Critical', tone: 'critical' },
  UNKNOWN: { label: 'Unknown', tone: 'neutral' },
};

export const APPLICABILITY_OUTCOME_META: Record<ApplicabilityOutcome, EnumMeta> = {
  YES: { label: 'Applies', tone: 'info', description: 'The requirement applies to this package.' },
  NO: {
    label: 'Does Not Apply',
    tone: 'neutral',
    description: 'Deterministically resolved as not applicable (reason recorded).',
  },
  UNKNOWN: {
    label: 'Unknown',
    tone: 'warning',
    description: 'Applicability could not be determined — never guessed.',
  },
};

// --- Evidence traceability graph (Prompt 7) -------------------------------------
// Presentation metadata for the read-only traceability graph. Every node kind
// maps to one persisted record type; none of these labels is a compliance
// verdict — the graph traces what the system recorded, nothing more.

export const EVIDENCE_GRAPH_NODE_META: Record<EvidenceGraphNodeKind, EnumMeta> = {
  INSPECTION: { label: 'Inspection', tone: 'neutral', description: 'The inspection this trace belongs to.' },
  IMAGE: { label: 'Package Image', tone: 'info', description: 'A real stored image captured for the inspection.' },
  IMAGE_REGION: { label: 'Image Region', tone: 'info', description: 'A detected region on the image (text line, symbol, etc.).' },
  OCR_RESULT: { label: 'OCR Result', tone: 'info', description: 'Raw OCR output for one region — verbatim engine text.' },
  EXTRACTED_FIELD: { label: 'Extracted Field', tone: 'info', description: 'A declaration candidate extracted from OCR evidence.' },
  REGULATORY_SOURCE: { label: 'Regulatory Source', tone: 'info', description: 'The publishing source of regulatory material.' },
  REGULATORY_DOCUMENT: { label: 'Regulatory Document', tone: 'info', description: 'The legal instrument a requirement belongs to.' },
  REGULATORY_VERSION: { label: 'Regulatory Version', tone: 'info', description: 'The version in force at the evaluation context date.' },
  REQUIREMENT: { label: 'Requirement', tone: 'info', description: 'A requirement definition in force.' },
  RULE: { label: 'Compliance Rule', tone: 'info', description: 'A deterministic rule bound to the requirement.' },
  EVALUATION: { label: 'Evaluation Run', tone: 'neutral', description: 'One immutable engine evaluation run.' },
  FINDING: { label: 'System Finding', tone: 'warning', description: 'A system-generated decision-support output — not an enforcement determination.' },
  PROCESSING_RUN: { label: 'Processing Run', tone: 'neutral', description: 'One perception pipeline run over an image.' },
  AUDIT_EVENT: { label: 'Audit Event', tone: 'neutral', description: 'An immutable audit-trail record.' },
  FIELD_CORRECTION: { label: 'Human Correction', tone: 'positive', description: 'A human correction of an AI-extracted value — append-only, actor-attributed.' },
  FINDING_REVIEW: { label: 'Human Review', tone: 'positive', description: 'An inspector review action on a system finding.' },
  INSPECTION_DECISION: { label: 'Final Decision', tone: 'positive', description: 'The final human decision — the only legal conclusion, never an AI output.' },
};

export const EVIDENCE_GRAPH_EDGE_META: Record<EvidenceGraphEdgeKind, EnumMeta> = {
  INSPECTION_CONTAINS_IMAGE: { label: 'contains image', tone: 'neutral' },
  INSPECTION_HAS_EVALUATION: { label: 'has evaluation', tone: 'neutral' },
  IMAGE_HAS_REGION: { label: 'has region', tone: 'neutral' },
  IMAGE_HAS_OCR_RESULT: { label: 'has OCR result', tone: 'neutral' },
  REGION_HAS_OCR_RESULT: { label: 'read as', tone: 'neutral' },
  OCR_SUPPORTS_FIELD: { label: 'supports field', tone: 'neutral' },
  REGION_SUPPORTS_FIELD: { label: 'supports field', tone: 'neutral' },
  PROCESSING_RUN_PROCESSED_IMAGE: { label: 'processed image', tone: 'neutral' },
  PROCESSING_RUN_PRODUCED_REGION: { label: 'produced region', tone: 'neutral' },
  PROCESSING_RUN_PRODUCED_OCR: { label: 'produced OCR', tone: 'neutral' },
  FIELD_EVALUATED_AGAINST_REQUIREMENT: { label: 'evaluated against', tone: 'neutral' },
  REQUIREMENT_EVALUATED_BY_RULE: { label: 'evaluated by', tone: 'neutral' },
  RULE_PRODUCED_FINDING: { label: 'produced finding', tone: 'neutral' },
  FINDING_BELONGS_TO_EVALUATION: { label: 'belongs to evaluation', tone: 'neutral' },
  EVALUATION_USES_REGULATORY_VERSION: { label: 'uses version', tone: 'neutral' },
  REQUIREMENT_BELONGS_TO_VERSION: { label: 'belongs to version', tone: 'neutral' },
  VERSION_ORIGINATES_FROM_DOCUMENT: { label: 'originates from', tone: 'neutral' },
  DOCUMENT_HAS_SOURCE: { label: 'published by', tone: 'neutral' },
  FINDING_SUPPORTED_BY_EVIDENCE: { label: 'supported by evidence', tone: 'neutral' },
  AUDIT_RECORDS_ACTION: { label: 'records action', tone: 'neutral' },
  FIELD_CORRECTION_CORRECTS_FIELD: { label: 'corrects field', tone: 'positive' },
  FINDING_REVIEW_REVIEWS_FINDING: { label: 'reviews finding', tone: 'positive' },
  FINDING_REVIEW_LINKS_CORRECTION: { label: 'links correction', tone: 'positive' },
  DECISION_FOR_INSPECTION: { label: 'decides on', tone: 'positive' },
  DECISION_BASED_ON_EVALUATION: { label: 'based on evaluation', tone: 'positive' },
  DECISION_SUPERSEDES_DECISION: { label: 'supersedes', tone: 'positive' },
};

/**
 * Traceability strength of the evidence behind a finding. A signal about the
 * CHAIN only — never a compliance verdict, and MISSING is never converted
 * into non-compliance.
 */
export const EVIDENCE_STRENGTH_META: Record<EvidenceStrength, EnumMeta> = {
  DIRECT: {
    label: 'Direct',
    tone: 'positive',
    description: 'The finding links to a specific OCR result and/or image region.',
  },
  DERIVED: {
    label: 'Derived',
    tone: 'info',
    description: 'An extracted field exists but no specific OCR result or region is linked to it.',
  },
  AMBIGUOUS: {
    label: 'Ambiguous',
    tone: 'warning',
    description: 'The field is marked for review or its OCR confidence is below 0.6 — verify before relying on it.',
  },
  MISSING: {
    label: 'Missing',
    tone: 'critical',
    description: 'No extracted field backs this finding. This is NOT evidence of absence and never a violation.',
  },
};

// --- Human-in-the-loop review & decision (Prompt 8) ---------------------------
// AI ASSISTS. THE INSPECTOR DECIDES. These vocabularies describe authorised
// human actions only — the engine can never produce any of these values.

/**
 * Who produced an evidence-graph node. The graph NEVER represents an AI
 * output and a human action as identical — origin is the visual distinction.
 */
export const EVIDENCE_NODE_ORIGIN_META: Record<EvidenceNodeOrigin, EnumMeta> = {
  AI: {
    label: 'AI',
    tone: 'info',
    description: 'Machine output from the perception / compliance pipeline.',
  },
  HUMAN: {
    label: 'Human',
    tone: 'positive',
    description: 'An authorised human action with an actor — correction, review or final decision.',
  },
  SYSTEM: {
    label: 'System',
    tone: 'neutral',
    description: 'Neutral recorded data — neither an AI inference nor a human review judgement.',
  },
};

/** Human review state of one system finding (backend-enforced transitions). */
export const FINDING_REVIEW_STATE_META: Record<FindingReviewState, EnumMeta> = {
  PENDING_REVIEW: {
    label: 'Pending Review',
    tone: 'warning',
    description: 'The system has produced a finding; the authorised inspector has not yet reviewed it.',
  },
  CONFIRMED: {
    label: 'Confirmed',
    tone: 'positive',
    description: 'The inspector agrees with the system finding.',
  },
  CORRECTED: {
    label: 'Corrected',
    tone: 'info',
    description: 'The underlying value was human-corrected; the finding was re-evaluated against the correction.',
  },
  REJECTED: {
    label: 'Rejected',
    tone: 'critical',
    description: 'The inspector rejects the system finding (a reason is mandatory).',
  },
  OVERRIDDEN: {
    label: 'Overridden',
    tone: 'warning',
    description: 'A supervisor overrode the reviewed outcome (supervisor/admin only, reason mandatory).',
  },
  ESCALATED: {
    label: 'Escalated',
    tone: 'warning',
    description: 'Routed to a supervisor / senior review (reason mandatory).',
  },
};

/** The final human decision — the only legal conclusion the system records. */
export const INSPECTION_DECISION_META: Record<InspectionDecisionType, EnumMeta> = {
  COMPLIANT: {
    label: 'Compliant',
    tone: 'positive',
    description: 'The authorised inspector decided the package is compliant. Recorded by a human, never by the engine.',
  },
  NON_COMPLIANT: {
    label: 'Non-Compliant',
    tone: 'critical',
    description: 'The authorised inspector decided the package is non-compliant. A reason is mandatory.',
  },
  REQUIRES_FURTHER_REVIEW: {
    label: 'Requires Further Review',
    tone: 'warning',
    description: 'Deferred — unresolved findings need attention before a final conclusion. A reason is mandatory.',
  },
  NOT_EVALUATED: {
    label: 'Not Evaluated',
    tone: 'neutral',
    description: 'No decision recorded yet.',
  },
};
