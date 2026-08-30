/**
 * Canonical enumerations for the METRASIGHT domain.
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

// --- Deterministic compliance engine (Prompt 6) -----------------------------
// The engine converts (detected field + applicable requirement + deterministic
// rule) into a finding. Findings are SYSTEM decision-support outputs — not, by
// themselves, legal enforcement determinations. The inspector remains
// responsible for the final enforcement decision.

/** Lifecycle of one compliance-engine evaluation run over an inspection. */
export const EVALUATION_STATUSES = [
  'NOT_EVALUATED',
  'EVALUATING',
  'COMPLETED',
  'PARTIAL',
  'REVIEW_REQUIRED',
  'FAILED',
  'NO_APPLICABLE_REQUIREMENT',
] as const;
export type EvaluationStatus = (typeof EVALUATION_STATUSES)[number];

/**
 * Status of one engine finding. COMPLIANT / NON_COMPLIANT only ever appear
 * with adequate valid evidence AND positive applicability — anything less is
 * an honest REVIEW_REQUIRED / NOT_DETECTED / NOT_EVALUATED, never a guess.
 */
export const ENGINE_FINDING_STATUSES = [
  'COMPLIANT',
  'NON_COMPLIANT',
  'REVIEW_REQUIRED',
  'NOT_DETECTED',
  'NOT_APPLICABLE',
  'NOT_EVALUATED',
] as const;
export type EngineFindingStatus = (typeof ENGINE_FINDING_STATUSES)[number];

/**
 * Triage label assigned deterministically from the finding status. It is a
 * review-prioritisation hint only — never a legal penalty.
 */
export const FINDING_SEVERITIES = ['INFO', 'MINOR', 'MAJOR', 'CRITICAL', 'UNKNOWN'] as const;
export type FindingSeverity = (typeof FINDING_SEVERITIES)[number];

/** Deterministic applicability resolution outcome (never guessed). */
export const APPLICABILITY_OUTCOMES = ['YES', 'NO', 'UNKNOWN'] as const;
export type ApplicabilityOutcome = (typeof APPLICABILITY_OUTCOMES)[number];

/** The closed rule-type vocabulary of the deterministic engine (no LLM). */
export const DETERMINISTIC_RULE_TYPES = [
  'PRESENCE',
  'TEXT_MATCH',
  'TEXT_PATTERN',
  'NUMERIC_VALUE',
  'UNIT_MATCH',
  'MRP_FORMAT',
  'DATE_FORMAT',
  'CONTACT_FORMAT',
  'DECLARATION_FORMAT',
  'FIELD_REQUIRED',
  'FIELD_NOT_REQUIRED',
  'RANGE',
  'COMPARISON',
] as const;
export type DeterministicRuleType = (typeof DETERMINISTIC_RULE_TYPES)[number];

/** Structured engine error codes (a failure is never COMPLIANT). */
export const COMPLIANCE_ERROR_CODES = [
  'REGULATORY_DATA_UNAVAILABLE',
  'NO_APPLICABLE_VERSION',
  'NO_APPLICABLE_REQUIREMENT',
  'INSUFFICIENT_EVIDENCE',
  'AMBIGUOUS_VALUE',
  'RULE_EXECUTION_FAILED',
  'INVALID_REGULATORY_DATA',
] as const;
export type ComplianceErrorCode = (typeof COMPLIANCE_ERROR_CODES)[number];

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

// --- Evidence graph (Prompt 7) -----------------------------------------------
// The Evidence Graph is a READ-ONLY traceability representation over real
// persisted records (Prompt 4 perception, Prompt 5 regulatory, Prompt 6
// compliance, audit). Node ids are `"<TYPE>:<entity-uuid>"` and every edge
// corresponds to an actual foreign-key / provenance relationship in the
// database — the graph never invents nodes and never determines compliance.

export const EVIDENCE_GRAPH_NODE_TYPES = [
  'INSPECTION',
  'IMAGE',
  'IMAGE_REGION',
  'OCR_RESULT',
  'EXTRACTED_FIELD',
  'REGULATORY_SOURCE',
  'REGULATORY_DOCUMENT',
  'REGULATORY_VERSION',
  'REQUIREMENT',
  'RULE',
  'EVALUATION',
  'FINDING',
  'PROCESSING_RUN',
  'AUDIT_EVENT',
  // Prompt 8 — human-in-the-loop records (origin=HUMAN nodes with an actor).
  'FIELD_CORRECTION',
  'FINDING_REVIEW',
  'INSPECTION_DECISION',
] as const;
export type EvidenceGraphNodeKind = (typeof EVIDENCE_GRAPH_NODE_TYPES)[number];

export const EVIDENCE_GRAPH_EDGE_TYPES = [
  'INSPECTION_CONTAINS_IMAGE',
  'INSPECTION_HAS_EVALUATION',
  'IMAGE_HAS_REGION',
  'IMAGE_HAS_OCR_RESULT',
  'REGION_HAS_OCR_RESULT',
  'OCR_SUPPORTS_FIELD',
  'REGION_SUPPORTS_FIELD',
  'PROCESSING_RUN_PROCESSED_IMAGE',
  'PROCESSING_RUN_PRODUCED_REGION',
  'PROCESSING_RUN_PRODUCED_OCR',
  'FIELD_EVALUATED_AGAINST_REQUIREMENT',
  'REQUIREMENT_EVALUATED_BY_RULE',
  'RULE_PRODUCED_FINDING',
  'FINDING_BELONGS_TO_EVALUATION',
  'EVALUATION_USES_REGULATORY_VERSION',
  'REQUIREMENT_BELONGS_TO_VERSION',
  'VERSION_ORIGINATES_FROM_DOCUMENT',
  'DOCUMENT_HAS_SOURCE',
  'FINDING_SUPPORTED_BY_EVIDENCE',
  'AUDIT_RECORDS_ACTION',
  // Prompt 8 — human-in-the-loop relations (sources are HUMAN nodes).
  'FIELD_CORRECTION_CORRECTS_FIELD',
  'FINDING_REVIEW_REVIEWS_FINDING',
  'FINDING_REVIEW_LINKS_CORRECTION',
  'DECISION_FOR_INSPECTION',
  'DECISION_BASED_ON_EVALUATION',
  'DECISION_SUPERSEDES_DECISION',
] as const;
export type EvidenceGraphEdgeKind = (typeof EVIDENCE_GRAPH_EDGE_TYPES)[number];

/**
 * Who produced a graph node — the Phase 15 AI-vs-HUMAN distinction.
 * AI outputs and human actions are never represented as identical:
 * a correction / review / decision is its own HUMAN node with an actor,
 * never a mutation of the AI node it acts upon.
 */
export const EVIDENCE_NODE_ORIGINS = ['AI', 'HUMAN', 'SYSTEM'] as const;
export type EvidenceNodeOrigin = (typeof EVIDENCE_NODE_ORIGINS)[number];

/**
 * Traceability strength of the evidence behind a finding — a signal about the
 * CHAIN, never a compliance verdict. MISSING evidence is never converted into
 * non-compliance by the graph; it is reported as MISSING.
 */
export const EVIDENCE_STRENGTHS = ['DIRECT', 'DERIVED', 'AMBIGUOUS', 'MISSING'] as const;
export type EvidenceStrength = (typeof EVIDENCE_STRENGTHS)[number];

// --- Human-in-the-loop review & decision (Prompt 8) ---------------------------
// AI ASSISTS. THE INSPECTOR DECIDES. The engine never produces a review state
// or a final decision — these vocabularies exist ONLY for authorised human
// actions, enforced by the backend state machine (never the frontend).

/**
 * Human review state of one engine finding. PENDING_REVIEW is the default:
 * the system has spoken, the human has not. Transitions are enforced in the
 * backend service layer — the frontend can only request them.
 */
export const FINDING_REVIEW_STATES = [
  'PENDING_REVIEW',
  'CONFIRMED',
  'CORRECTED',
  'REJECTED',
  'OVERRIDDEN',
  'ESCALATED',
] as const;
export type FindingReviewState = (typeof FINDING_REVIEW_STATES)[number];

/**
 * The FINAL human decision on an inspection — the only legal conclusion.
 * The deterministic engine NEVER produces any of these values.
 */
export const INSPECTION_DECISION_TYPES = [
  'COMPLIANT',
  'NON_COMPLIANT',
  'REQUIRES_FURTHER_REVIEW',
  'NOT_EVALUATED',
] as const;
export type InspectionDecisionType = (typeof INSPECTION_DECISION_TYPES)[number];

/** Review actions an authorised human can request for a finding. */
export const FINDING_REVIEW_ACTIONS = [
  'CONFIRM',
  'CORRECT',
  'REJECT',
  'OVERRIDE',
  'ESCALATE',
] as const;
export type FindingReviewAction = (typeof FINDING_REVIEW_ACTIONS)[number];

// --- Audit events (Prompt 8 additions) ----------------------------------------

export const HITL_AUDIT_EVENT_TYPES = [
  'FIELD_REVIEWED',
  'FIELD_CORRECTED',
  'FINDING_CONFIRMED',
  'FINDING_REJECTED',
  'FINDING_OVERRIDDEN',
  'FINDING_ESCALATED',
  'DECISION_SUBMITTED',
  'DECISION_CHANGED',
  'SUPERVISOR_REVIEWED',
] as const;
export type HitlAuditEventType = (typeof HITL_AUDIT_EVENT_TYPES)[number];
