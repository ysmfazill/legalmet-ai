/**
 * Domain entity DTOs — the JSON shapes returned by the METRASIGHT API.
 *
 * Convention: the API serialises using camelCase (configured in the backend via
 * a Pydantic alias generator), so these interfaces use camelCase throughout.
 *
 * `isDemo` appears on any entity that may currently be backed by placeholder /
 * mock data during the foundation phase. The UI uses it to render a clear
 * "DEMO DATA — NOT LEGAL ADVICE" marker. It must never be silently dropped.
 */
import type {
  ApplicabilityOutcome,
  AuditEventType,
  CaptureSource,
  CitizenReportStatus,
  CitizenScreenOutcome,
  ComplaintAction,
  ComplianceErrorCode,
  ComplianceStatus,
  DeterministicRuleType,
  DocumentType,
  EngineFindingStatus,
  EvaluationStatus,
  EvidenceType,
  ExtractionStatus,
  FieldType,
  FindingReviewAction,
  FindingReviewState,
  FindingSeverity,
  ImageProcessingStatus,
  ImageQualityGrade,
  ImageQualityStatus,
  ImageType,
  InspectionDecisionType,
  InspectionStatus,
  ModelServiceType,
  PackageStatus,
  ProcessingRunStatus,
  RegionType,
  RegulationVersionStatus,
  RequirementType,
  ReviewActionType,
  RuleStatus,
  BatchStatus,
  SourceType,
  UserRole,
  VerificationStatus,
  VersionSelectionStatus,
  CandidateMappingStatus,
  EvidenceGraphEdgeKind,
  EvidenceGraphNodeKind,
  EvidenceStrength,
  EvidenceItemStatus,
  EvidenceRequirementKind,
  LotPackageStatus,
  ReportStatus,
  ReportEvidenceType,
  LotStatus,
  MeasurementEvaluationStatus,
  MeasurementOutcome,
  SamplingMethod,
  VerificationLevel,
  VerificationTaskStatus,
  VerificationTaskType,
} from './enums';

/** Arbitrary JSON payload (e.g. jsonb columns). */
export type Json = null | boolean | number | string | Json[] | { [key: string]: Json };

/** Normalised bounding box in fractional image coordinates (0..1). */
export interface BoundingBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface User {
  id: string;
  email: string;
  fullName: string;
  role: UserRole;
  isActive: boolean;
  createdAt: string;
}

export interface Product {
  id: string;
  name: string;
  category: string;
  gtin?: string | null;
  /** Expected declaration profile for the category (perception hint, not law). */
  declarationProfile?: FieldType[];
  isDemo: boolean;
  createdAt: string;
}

export interface FindingCounts {
  total: number;
  compliant: number;
  potentialViolation: number;
  reviewRequired: number;
  notApplicable: number;
  lowConfidence: number;
  imageQualityInsufficient: number;
}

export interface Inspection {
  id: string;
  referenceNo: string;
  status: InspectionStatus;
  productId?: string | null;
  product?: Product | null;
  inspectorId?: string | null;
  /** UI-05: the assigned inspector's display name (API-computed). */
  inspectorName?: string | null;
  batchId?: string | null;
  note?: string | null;
  isDemo: boolean;
  createdAt: string;
  updatedAt: string;
  completedAt?: string | null;
  packages?: Package[];
  findingCounts?: FindingCounts;
  /** UI-05: when this inspection was targeted from an accepted citizen
   * complaint, the complaint it originated from (view-only reference). */
  sourceComplaint?: SourceComplaintRef | null;
}

/** Complaint provenance carried on an inspection (UI-05) — enough to trace
 * the origin and label the inspection as TARGETED, without duplicating the
 * complaint object. */
export interface SourceComplaintRef {
  id: string;
  reference: string;
  status: CitizenReportStatus;
  issue: string;
  location?: string | null;
  /** Official priority when set, else the system screening risk. */
  priority?: string | null;
}

export interface Package {
  id: string;
  inspectionId: string;
  productId?: string | null;
  label: string;
  status: PackageStatus;
  createdAt: string;
  images?: PackageImage[];
}

export interface PackageImage {
  id: string;
  packageId: string;
  storageKey: string;
  originalFilename: string;
  mimeType: string;
  width?: number | null;
  height?: number | null;
  fileSize?: number | null;
  imageType: ImageType;
  qualityScore?: number | null;
  qualityStatus: ImageQualityStatus;
  isDemo: boolean;
  createdAt: string;
  regions?: ImageRegion[];
  // --- Prompt 3: real intake provenance + preprocessing --------------------
  /** SHA-256 hex of the ORIGINAL bytes (provenance + duplicate detection). */
  checksum?: string | null;
  captureSource: CaptureSource;
  processingStatus: ImageProcessingStatus;
  /** Usability grade — NOT compliance/AI confidence. */
  qualityGrade?: ImageQualityGrade | null;
  /** Deterministic usability breakdown (resolution/sharpness/contrast/...). */
  qualityMetrics?: Json | null;
  /** Metadata-stripped, resized derivative; the original is preserved. */
  processedStorageKey?: string | null;
  /** Retrieval URL for the original object (populated by the API). */
  url?: string | null;
  /** Retrieval URL for the processed derivative, when prepared. */
  processedUrl?: string | null;
}

export interface ImageRegion {
  id: string;
  imageId: string;
  regionType: RegionType;
  bbox: BoundingBox;
  confidence: number;
  createdAt: string;
  // --- Prompt 4: perception provenance + decoded symbols -------------------
  processingRunId?: string | null;
  /** Decoded symbol evidence, e.g. {symbology: "EAN_13", value: "890..."}. */
  payload?: Json | null;
}

export interface ExtractedField {
  id: string;
  imageId: string;
  imageRegionId?: string | null;
  packageId: string;
  fieldType: FieldType;
  rawText: string;
  normalizedValue?: string | null;
  unit?: string | null;
  confidence: number;
  extractionMethod: string;
  modelVersionId?: string | null;
  isDemo: boolean;
  createdAt: string;
  // --- Prompt 4: perception outcome + provenance ---------------------------
  /** Perception outcome (DETECTED / REVIEW_REQUIRED / NOT_EXTRACTED) — NOT a
   * compliance status. */
  status: ExtractionStatus;
  processingRunId?: string | null;
  sourceOcrResultId?: string | null;
  /** Human-correction foundation — populated only by a future human action. */
  correctedValue?: string | null;
  correctedAt?: string | null;
}

// --- Perception processing runs (Prompt 4) -----------------------------------

/** One auditable OCR/vision execution over ONE image. */
export interface ProcessingRun {
  id: string;
  reference: string;
  inspectionId: string;
  imageId: string;
  status: ProcessingRunStatus;
  startedAt?: string | null;
  completedAt?: string | null;
  durationMs?: number | null;
  ocrProvider?: string | null;
  ocrModel?: string | null;
  ocrVersion?: string | null;
  visionProvider?: string | null;
  visionModel?: string | null;
  visionVersion?: string | null;
  pipelineVersion: string;
  configuration?: Json | null;
  summary?: Json | null;
  error?: Json | null;
  isDemo: boolean;
  createdAt: string;
}

/** Run detail including the evidence produced by that exact run. */
export interface ProcessingRunDetail extends ProcessingRun {
  ocrResults: OcrTextResult[];
  regions: ImageRegion[];
  fields: ExtractedField[];
}

/** One OCR line — raw engine output is immutable evidence. */
export interface OcrTextResult {
  id: string;
  imageId: string;
  processingRunId: string;
  regionId?: string | null;
  /** Verbatim engine output — never modified. */
  rawText: string;
  /** Derived tidy-up; the raw text above is never touched. */
  normalizedText?: string | null;
  bbox: BoundingBox;
  /** The OCR engine's own recognition confidence (never legal confidence). */
  confidence: number;
  language?: string | null;
  provider: string;
  modelName: string;
  modelVersion: string;
  createdAt: string;
}

export interface PerceptionKickoffRun {
  runId: string;
  reference: string;
  imageId: string;
}

export interface PerceptionKickoff {
  inspectionId: string;
  status: string;
  runs: PerceptionKickoffRun[];
  note: string;
}

export interface PerceptionImageSummary {
  imageId: string;
  imageType: string;
  latestRun?: ProcessingRun | null;
  ocrCount: number;
  regionCount: number;
  fieldCount: number;
}

export interface PerceptionSummary {
  textElements: number;
  visualRegions: number;
  fieldsExtracted: number;
  lowConfidenceItems: number;
  totalProcessingMs: number;
  ocrModel?: string | null;
  visionModel?: string | null;
}

export interface PerceptionAnalysis {
  inspectionId: string;
  hasRuns: boolean;
  /** True while any latest run is in a non-terminal stage (poll while set). */
  active: boolean;
  summary: PerceptionSummary;
  images: PerceptionImageSummary[];
  /** Marker for the workspace UI: perception is done, law is not applied yet. */
  regulatoryEvaluation: 'AWAITING_REGULATORY_EVALUATION';
}

// --- Regulatory knowledge system ---------------------------------------------
// Prompt 5 extends this into a provenance hierarchy:
//   SOURCE → DOCUMENT (Regulation) → VERSION → REQUIREMENT (Rule)
// `Regulation`/`RegulationVersion`/`Rule` gain provenance fields; the new
// `Regulatory*` interfaces are the Prompt 5 read-models over the same tables.

/** The authoritative publisher a regulatory document was sourced from. */
export interface RegulatorySource {
  id: string;
  name: string;
  authority: string;
  sourceType: SourceType;
  canonicalUrl?: string | null;
  jurisdiction: string;
  verificationStatus: VerificationStatus;
  /** Why this source is (or is not) verified — required when VERIFIED. */
  verificationNote?: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface Regulation {
  id: string;
  code: string;
  title: string;
  jurisdiction: string;
  authority: string;
  description?: string | null;
  officialSourceUrl?: string | null;
  isDemo: boolean;
  /** Provenance (Prompt 5): FK to the publishing source. */
  sourceId?: string | null;
  /** Official identifier, e.g. "G.S.R. 202(E)". */
  documentIdentifier?: string | null;
  documentType: DocumentType;
  publicationDate?: string | null;
  /** Content hash of the source text this document was imported from. */
  contentHash?: string | null;
  /** Version window list (populated by the regulatory documents endpoint). */
  versions?: RegulationVersion[];
  createdAt: string;
}

export interface RegulationVersion {
  id: string;
  regulationId: string;
  versionLabel: string;
  status: RegulationVersionStatus;
  /** In-force window [effectiveFrom, effectiveUntil). */
  effectiveFrom?: string | null;
  effectiveUntil?: string | null;
  amendmentOfId?: string | null;
  sourceDocumentRef?: string | null;
  isDemo: boolean;
  publicationDate?: string | null;
  createdAt: string;
}

export interface Rule {
  id: string;
  regulationVersionId: string;
  ruleCode: string;
  title: string;
  requirementSummary: string;
  /** Key referencing a deterministic validator in the rule engine registry. */
  validationLogicRef: string;
  evidenceRequirement?: string | null;
  status: RuleStatus;
  isDemo: boolean;
  createdAt: string;
}

/** Prompt 5 requirement read-model — a Rule with regulatory provenance. */
export interface RegulatoryRequirement {
  id: string;
  versionId: string;
  ruleCode: string;
  title: string;
  description: string;
  requirementType: RequirementType;
  /** Perception field type this requirement maps to, when any. */
  fieldKey?: string | null;
  expectedFormat?: string | null;
  mandatory: boolean;
  applicabilityDefinition: Json;
  sourceReference?: string | null;
  status: RuleStatus;
  isDemo: boolean;
  createdAt: string;
}

/** Answer to "where did this requirement come from?" */
export interface RequirementProvenance {
  authority: string;
  documentTitle: string;
  documentIdentifier?: string | null;
  versionLabel: string;
  effectiveFrom?: string | null;
  effectiveTo?: string | null;
  sourceReference?: string | null;
  requirementReference?: string | null;
  sourceName?: string | null;
  sourceVerificationStatus?: VerificationStatus | null;
  canonicalUrl?: string | null;
}

export interface RegulatoryRequirementDetail extends RegulatoryRequirement {
  provenance: RequirementProvenance;
  version: RegulationVersion;
}

/** Result of deterministic effective-date version selection. */
export interface VersionSelection {
  documentId: string;
  requestedDate: string;
  status: VersionSelectionStatus;
  version?: RegulationVersion | null;
}

/**
 * A candidate requirement mapped to a detected perception field. Candidate
 * association ONLY — applicability is not evaluated and no compliance
 * conclusion exists here.
 */
export interface CandidateRequirement {
  requirementId: string;
  ruleCode: string;
  title: string;
  sourceReference?: string | null;
  versionLabel: string;
  effectiveFrom?: string | null;
  sourceVerificationStatus?: VerificationStatus | null;
}

export interface FieldCandidate {
  fieldId: string;
  fieldType: string;
  fieldValue?: string | null;
  fieldStatus: string;
  candidates: CandidateRequirement[];
  mappingStatus: CandidateMappingStatus;
  applicabilityStatus: CandidateMappingStatus;
  evaluationStatus: CandidateMappingStatus;
}

export interface FieldCandidates {
  inspectionId: string;
  contextDate: string;
  fields: FieldCandidate[];
  /** Constant, explicit boundary marker — never a compliance verdict. */
  regulatoryEvaluation: 'AWAITING_REGULATORY_EVALUATION';
}

export interface RuleApplicability {
  id: string;
  ruleId: string;
  productCategory: string;
  conditionExpression: Json;
  isDemo: boolean;
  createdAt: string;
}

// --- Deterministic compliance engine (Prompt 6) -------------------------------
// One evaluation run + one finding per (requirement, detected field). These are
// SYSTEM decision-support outputs: the boundary note travels with every payload
// so no consumer can mistake a finding for a legal enforcement determination.

/** Mandated boundary statement attached to every compliance-engine payload. */
export const FINDING_BOUNDARY_NOTE =
  'System finding — inspector decision pending. Compliance findings are ' +
  'system-generated decision-support outputs. They are not, by themselves, ' +
  'legal enforcement determinations.';

/** One immutable evaluation run (history is never overwritten). */
export interface ComplianceEvaluation {
  id: string;
  inspectionId: string;
  imageId?: string | null;
  regulatoryVersionId?: string | null;
  status: EvaluationStatus;
  engineVersion: string;
  contextDate: string;
  /** COUNTS ONLY — never a percentage or fake confidence score. */
  summary: {
    totalFindings: number;
    byStatus: Record<string, number>;
    reviewQueueCount: number;
    requirementsEvaluated: number;
  };
  error?: { code: ComplianceErrorCode; message: string } | null;
  startedAt: string;
  completedAt?: string | null;
  actorId?: string | null;
  createdAt: string;
  findings?: EngineFinding[];
  boundaryNote: string;
}

/** Frozen provenance snapshot recorded on each finding at evaluation time. */
export interface FindingProvenance {
  requirementCode?: string;
  requirementTitle?: string;
  reference?: string | null;
  versionId?: string;
  versionLabel?: string;
  effectiveFrom?: string | null;
  effectiveUntil?: string | null;
  documentTitle?: string;
  documentIdentifier?: string | null;
  sourceName?: string;
  sourceVerificationStatus?: string;
}

/** Per-rule outcome entries recorded on a finding (the deterministic trace). */
export interface EngineRuleOutcome {
  ruleCode: string;
  ruleType: string;
  passed: boolean | null;
  reason: string;
  expected?: string;
  errorCode?: string;
}

/** Deterministic evaluation trace stored on a finding. */
export interface EngineFindingDetail {
  rules?: EngineRuleOutcome[];
  evidenceFieldIds?: string[];
  searchedRunIds?: string[];
  fieldKey?: string | null;
  evidenceCount?: number;
  absence?: 'FIELD_NOT_FOUND' | 'FIELD_CONFIRMED_ABSENT';
  errorCode?: string;
  message?: string;
}

/** One engine finding: requirement + evidence + deterministic conclusion. */
export interface EngineFinding {
  id: string;
  evaluationId: string;
  inspectionId: string;
  requirementId: string;
  ruleId?: string | null;
  extractedFieldId?: string | null;
  evidenceRegionId?: string | null;
  imageId?: string | null;
  status: EngineFindingStatus;
  severity: FindingSeverity;
  applicability: ApplicabilityOutcome;
  detectedValue?: string | null;
  expectedValue?: string | null;
  /** Deterministic explanation answering the seven transparency questions. */
  explanation: string;
  provenance: FindingProvenance;
  detail: EngineFindingDetail;
  /**
   * Human review overlay (Prompt 8): PENDING_REVIEW until an authorised
   * inspector acts. The engine NEVER writes this field beyond the default.
   */
  reviewState: FindingReviewState;
  reviewedBy?: string | null;
  reviewedAt?: string | null;
  reviewReason?: string | null;
  createdAt: string;
  boundaryNote: string;
}

/** GET /compliance/engine — vocabulary + the no-LLM contract. */
export interface EngineInfo {
  engineVersion: string;
  ruleTypes: Array<{ ruleType: DeterministicRuleType; description: string }>;
  usesLlm: false;
  boundaryNote: string;
}

/** GET /inspections/{id}/compliance — latest evaluation or explicit absence. */
export interface InspectionComplianceStatus {
  inspectionId: string;
  status: EvaluationStatus;
  evaluation?: ComplianceEvaluation | null;
  boundaryNote: string;
}

/** A deterministic rule configuration bound to a real requirement. */
export interface ComplianceRuleConfig {
  id: string;
  requirementId: string;
  ruleCode: string;
  ruleType: DeterministicRuleType;
  ruleVersion: number;
  configuration: Record<string, Json>;
  description?: string | null;
  active: boolean;
  isDemo: boolean;
  createdAt: string;
}

// --- Findings, evidence, review --------------------------------------------

export interface Evidence {
  id: string;
  findingId: string;
  evidenceType: EvidenceType;
  imageId?: string | null;
  imageRegionId?: string | null;
  extractedFieldId?: string | null;
  ruleId?: string | null;
  data?: Json;
  createdAt: string;
}

export interface ReviewAction {
  id: string;
  findingId: string;
  reviewerId: string;
  action: ReviewActionType;
  correctedStatus?: ComplianceStatus | null;
  reason?: string | null;
  note?: string | null;
  createdAt: string;
}

export interface ComplianceFinding {
  id: string;
  inspectionId: string;
  packageId: string;
  ruleId?: string | null;
  ruleVersionId?: string | null;
  fieldType?: FieldType | null;
  status: ComplianceStatus;
  confidence: number;
  rationale: string;
  modelVersionId?: string | null;
  /** Latest human decision, if any. */
  reviewStatus?: ComplianceStatus | null;
  isReviewed: boolean;
  isDemo: boolean;
  createdAt: string;
  evidence?: Evidence[];
  reviewActions?: ReviewAction[];
}

export interface AuditEvent {
  id: string;
  inspectionId?: string | null;
  entityType: string;
  entityId?: string | null;
  actorId?: string | null;
  eventType: AuditEventType | string;
  payload?: Json;
  createdAt: string;
}

export interface ModelVersion {
  id: string;
  serviceType: ModelServiceType;
  name: string;
  version: string;
  provider: string;
  isActive: boolean;
  metadata?: Json;
  createdAt: string;
}

export interface BatchInspection {
  id: string;
  name: string;
  description?: string | null;
  status: BatchStatus;
  totalCount: number;
  stats?: BatchStats | null;
  createdBy?: string | null;
  createdAt: string;
  updatedAt: string;
}

// --- Analytics -------------------------------------------------------------

export interface BatchStats {
  total: number;
  byStatus: Record<ComplianceStatus, number>;
  reviewRequired: number;
  potentialViolations: number;
}

export interface RecurringViolation {
  fieldType: FieldType | null;
  ruleId: string | null;
  ruleCode: string | null;
  count: number;
  affectedInspections: number;
}

export interface DashboardSummary {
  inspections: {
    total: number;
    byStatus: Record<InspectionStatus, number>;
  };
  findings: FindingCounts;
  recentInspections: Inspection[];
  recurringViolations: RecurringViolation[];
  generatedAt: string;
}

// --- Evidence graph (for the Evidence Viewer) ------------------------------

export interface EvidenceGraphNode {
  id: string;
  type:
    | 'INSPECTION'
    | 'PACKAGE'
    | 'IMAGE'
    | 'IMAGE_REGION'
    | 'EXTRACTED_FIELD'
    | 'EVIDENCE'
    | 'RULE'
    | 'RULE_VERSION'
    | 'FINDING'
    | 'REVIEW_ACTION';
  label: string;
  data?: Json;
}

export interface EvidenceGraphEdge {
  from: string;
  to: string;
  relation: string;
}

export interface EvidenceGraph {
  findingId: string;
  nodes: EvidenceGraphNode[];
  edges: EvidenceGraphEdge[];
}

// --- Evidence traceability graph (Prompt 7) ------------------------------------
// Read-only traceability over REAL persisted records. Every node is one
// persisted entity (`id` is `"<TYPE>:<uuid>"`), every edge is an actual
// foreign-key / provenance relationship. This graph is a representation of
// system inputs, transformations, regulatory references and findings — it does
// not independently determine legal compliance.

/** Mandated boundary statement attached to every evidence-graph payload. */
export const EVIDENCE_GRAPH_BOUNDARY_NOTE =
  'The Evidence Graph is a traceability representation of system inputs, ' +
  'transformations, regulatory references, and findings. It does not ' +
  'independently determine legal compliance.';

/** One traceability node == one persisted record. */
export interface TraceNode {
  id: string;
  type: EvidenceGraphNodeKind;
  label: string;
  /** Whitelisted, non-sensitive metadata (no storage keys, paths or secrets). */
  metadata?: Record<string, Json> | null;
}

/** One typed relationship between two real entity nodes. */
export interface TraceEdge {
  id: string;
  source: string;
  target: string;
  type: EvidenceGraphEdgeKind;
  metadata?: Record<string, Json> | null;
}

/** A bounded, cycle-free traceability graph (node/edge caps server-enforced). */
export interface EvidenceTraceGraph {
  rootType: string;
  rootId: string;
  inspectionId: string;
  evaluationId?: string | null;
  nodes: TraceNode[];
  edges: TraceEdge[];
  nodeCount: number;
  edgeCount: number;
  /** True when the server hit a traversal cap — the graph is a bounded view. */
  truncated: boolean;
  boundaryNote: string;
}

/** GET /evidence-graph — vocabulary + evidence-strength semantics. */
export interface EvidenceGraphVocabulary {
  strengths: Array<{
    strength: EvidenceStrength;
    label: string;
    description: string;
  }>;
  boundaryNote: string;
}

// --- Human-in-the-loop review & decision (Prompt 8) ----------------------------
// AI ASSISTS. THE INSPECTOR DECIDES. Every payload below carries the mandated
// boundary note, and every write is an authorised human action — the engine
// can never produce any of these records.

/** Mandated boundary statement attached to every HITL payload. */
export const HITL_BOUNDARY_NOTE =
  'METRASIGHT provides AI-assisted inspection analysis and traceability. ' +
  'The authorized inspector remains responsible for the final inspection ' +
  'decision.';

/** POST /fields/{fieldId}/correct — inspector corrects an AI-extracted value. */
export interface FieldCorrectRequest {
  correctedValue: string;
  reason: string;
  triggeredByEvaluationId?: string | null;
}

/**
 * One append-only correction row. The original AI extraction is NEVER
 * overwritten — previousValue/newValue are both preserved here.
 */
export interface FieldCorrection {
  id: string;
  extractedFieldId: string;
  inspectionId: string;
  correctedBy: string;
  correctedByName?: string | null;
  correctedAt: string;
  previousValue?: string | null;
  previousRawText?: string | null;
  correctedValue: string;
  reason: string;
  triggeredByEvaluationId?: string | null;
  createdAt: string;
}

/** GET /fields/{fieldId}/review — original AI value vs latest human correction. */
export interface FieldReview {
  fieldId: string;
  inspectionId: string;
  originalValue?: string | null;
  originalRawText?: string | null;
  aiConfidence?: number | null;
  aiExtractionStatus?: string | null;
  correctedValue?: string | null;
  correctedAt?: string | null;
  correctedBy?: string | null;
  correctedByName?: string | null;
  correctionReason?: string | null;
  correctionCount: number;
  boundaryNote: string;
}

/** One immutable transition in a finding's review history. */
export interface FindingReviewEvent {
  id: string;
  reviewId: string;
  actorId?: string | null;
  actorRole?: string | null;
  action: string;
  previousState?: FindingReviewState | null;
  newState?: FindingReviewState | null;
  reason?: string | null;
  payload: Record<string, Json>;
  createdAt: string;
}

/**
 * The human review overlay of one engine finding. The finding itself is a
 * frozen system output; this records what the AUTHORISED HUMAN decided.
 */
export interface FindingReview {
  id: string;
  findingId: string;
  inspectionId: string;
  evaluationId?: string | null;
  state: FindingReviewState;
  reviewedBy?: string | null;
  reviewedByName?: string | null;
  reviewedAt?: string | null;
  reason?: string | null;
  correctionId?: string | null;
  escalatedToRole?: string | null;
  events: FindingReviewEvent[];
  boundaryNote: string;
}

/** POST /compliance/findings/{findingId}/review — one review action. */
export interface FindingReviewActionRequest {
  action?: FindingReviewAction;
  reason?: string | null;
  note?: string | null;
  correctedValue?: string | null;
}

/** POST /inspections/{inspectionId}/decision — the final human decision. */
export interface DecisionRequest {
  decision: InspectionDecisionType;
  reason?: string | null;
  note?: string | null;
  evaluationId?: string | null;
}

/**
 * The FINAL human decision on an inspection — the only legal conclusion the
 * system ever records. Superseded, never deleted.
 */
export interface InspectionDecision {
  id: string;
  inspectionId: string;
  decision: InspectionDecisionType;
  decidedBy: string;
  decidedByName?: string | null;
  decidedAt: string;
  reason?: string | null;
  evaluationId?: string | null;
  supersedesDecisionId?: string | null;
  payload: Record<string, Json>;
  createdAt: string;
  boundaryNote: string;
}

/** GET /inspections/{inspectionId}/decision-history — the full chain. */
export interface DecisionHistory {
  inspectionId: string;
  current?: InspectionDecision | null;
  history: InspectionDecision[];
  boundaryNote: string;
}

/**
 * GET /inspections/{inspectionId}/review-status — review progress + the
 * decision gate (critical unresolved findings block a final decision).
 */
export interface ReviewStatus {
  inspectionId: string;
  totalFindings: number;
  pendingReview: number;
  confirmed: number;
  corrected: number;
  rejected: number;
  overridden: number;
  escalated: number;
  /** Findings with no review row yet — implicitly PENDING_REVIEW. */
  unreviewed: number;
  criticalUnresolved: number;
  decision?: InspectionDecision | null;
  decisionAllowed: boolean;
  decisionBlockers: string[];
  /** UI-06: open REQUIRED verification tasks also block; RECOMMENDED never do. */
  verificationTotal: number;
  verificationOpenRequired: number;
  verificationInProgress: number;
  verificationCompleted: number;
  boundaryNote: string;
}

// --- Evidence Planner + verification (UI-06) ----------------------------------
// What evidence exists, what is missing, and which inspector action closes
// the gap. A measurement is EVIDENCE recorded by a human from an appropriate
// instrument — the system never converts a declared-vs-measured difference
// into an automatic violation.

/** One recorded verification outcome — append-only, never edited. */
export interface VerificationResult {
  id: string;
  taskId: string;
  recordedBy: string;
  recordedByName?: string | null;
  recordedAt: string;
  measuredValue?: number | null;
  unit?: string | null;
  observation?: string | null;
  instrumentId?: string | null;
  /** Only set when the inspector supplied it — absent means "not recorded". */
  instrumentVerificationStatus?: string | null;
  notes?: string | null;
  createdAt: string;
}

/** One concrete inspector action that closes an evidence gap. */
export interface VerificationTask {
  id: string;
  inspectionId: string;
  findingId?: string | null;
  extractedFieldId?: string | null;
  /** UI-07 — set when this task measures a LOT PACKAGE (gates the lot
   * decision, not the inspection decision). */
  lotPackageId?: string | null;
  taskType: VerificationTaskType;
  requirementLevel: VerificationLevel;
  reason: string;
  status: VerificationTaskStatus;
  createdBy: string;
  createdByName?: string | null;
  startedAt?: string | null;
  completedAt?: string | null;
  cancelledReason?: string | null;
  results: VerificationResult[];
  createdAt: string;
  boundaryNote: string;
}

/** POST /inspections/:id/verifications — explicit human action, reason mandatory. */
export interface VerificationCreateRequest {
  findingId?: string | null;
  fieldId?: string | null;
  lotPackageId?: string | null;
  type?: VerificationTaskType;
  reason: string;
  requirementLevel?: VerificationLevel | null;
}

/** POST /verifications/:id/result — one recorded outcome. */
export interface VerificationResultRequest {
  measuredValue?: number | null;
  unit?: string | null;
  observation?: string | null;
  instrumentId?: string | null;
  instrumentVerificationStatus?: string | null;
  notes?: string | null;
}

export interface VerificationList {
  inspectionId: string;
  tasks: VerificationTask[];
  boundaryNote: string;
}

/** One concrete piece of evidence behind a plan row (real or absent). */
export interface EvidencePlanItemEvidence {
  kind: EvidenceRequirementKind;
  status: EvidenceItemStatus;
  label: string;
  detail?: string | null;
}

/** One OPEN evidence gap and the verification that closes it. */
export interface EvidencePlanGap {
  kind: EvidenceRequirementKind;
  reason: string;
  required: boolean;
  defaultLevel: VerificationLevel;
  taskId?: string | null;
  taskStatus?: VerificationTaskStatus | null;
}

/** The OBSERVED difference between a declaration and a measurement — pure
 * arithmetic on normalized values, labelled "observed" and never a legal
 * deficiency. `comparable: false` (with `reason`) when the pair cannot be
 * compared deterministically (dimension mismatch, unparseable declaration). */
export interface ObservedDifference {
  comparable: boolean;
  reason?: string;
  declared?: { value: string; unit: string; normalized: string };
  measured?: { value: string; unit: string; normalized: string };
  difference?: string;
  percentDifference?: string;
  note?: string;
}

/** The frozen regulatory evaluation of ONE recorded measurement (UI-07).
 * Computed once at record time against the permissible-error procedure
 * configured for the applicable version; later rule changes never rewrite
 * it. UNAVAILABLE means "not configured — inspector review required",
 * never a guessed tolerance. */
export interface MeasurementEvaluation {
  id: string;
  status: MeasurementEvaluationStatus;
  outcome?: MeasurementOutcome | null;
  ruleCode?: string | null;
  ruleVersionId?: string | null;
  provenance: Record<string, unknown>;
  detail: Record<string, unknown>;
  evaluatedAt: string;
}

/** The verification task attached to a plan row (its live state). */
export interface EvidencePlanVerificationRef {
  id: string;
  taskType: VerificationTaskType;
  status: VerificationTaskStatus;
  requirementLevel: VerificationLevel;
  reason: string;
  createdAt: string;
  startedAt?: string | null;
  completedAt?: string | null;
  observed?: ObservedDifference | null;
  evaluation?: MeasurementEvaluation | null;
  latestResult?: VerificationResult | null;
}

/** One row of the Evidence Planner — a finding or a bare declaration. */
export interface EvidencePlanItem {
  findingId?: string | null;
  fieldId?: string | null;
  title: string;
  declaredValue?: string | null;
  unit?: string | null;
  confidence?: number | null;
  requirementCode?: string | null;
  requirementTitle?: string | null;
  ruleCode?: string | null;
  versionLabel?: string | null;
  findingStatus?: EngineFindingStatus | null;
  severity?: FindingSeverity | null;
  applicability?: ApplicabilityOutcome | null;
  reviewState?: FindingReviewState | null;
  evidence: EvidencePlanItemEvidence[];
  gaps: EvidencePlanGap[];
  status: EvidenceItemStatus;
  summary: string;
  verification?: EvidencePlanVerificationRef | null;
}

export interface EvidencePlanCounts {
  total: number;
  available: number;
  requiringVerification: number;
  verified: number;
  rejected: number;
  notApplicable: number;
  openRequiredTasks: number;
}

/** GET /inspections/:id/evidence-plan — the Evidence Planner view. */
export interface EvidencePlan {
  inspectionId: string;
  items: EvidencePlanItem[];
  counts: EvidencePlanCounts;
  boundaryNote: string;
  payload?: Record<string, Json>;
}

// --- Physical verification + lot intelligence (UI-07) -------------------------
// LOT → PACKAGES → SAMPLE → MEASUREMENTS → REGULATORY EVALUATION → LOT RESULT.
// Every read model carries the two honesty contracts of this layer:
// statistics are OBSERVED values computed from recorded measurements, never
// legal compliance results; and a sampling run either references a
// CONFIGURED legal procedure or is explicitly AI-recommended with inspector
// confirmation — the system never claims a legally required sample it
// cannot cite.

/** One recorded measurement in the append-only history (§14). */
export interface MeasurementHistoryRow {
  measurementId: string;
  taskId: string;
  taskStatus: VerificationTaskStatus;
  anchor:
    | { kind: 'LOT_PACKAGE'; lotPackageId: string }
    | { kind: 'FINDING'; findingId: string }
    | { kind: 'DECLARATION'; extractedFieldId: string };
  declaredValue?: string | null;
  measuredValue?: number | null;
  unit?: string | null;
  observed?: ObservedDifference | null;
  instrumentId?: string | null;
  /** Only set when supplied — absent means "not recorded", never "verified". */
  instrumentVerificationStatus?: string | null;
  recordedBy: string;
  recordedByName?: string | null;
  recordedAt: string;
  observation?: string | null;
  notes?: string | null;
  evaluation?: MeasurementEvaluation | null;
}

export interface MeasurementHistory {
  inspectionId: string;
  measurements: MeasurementHistoryRow[];
  boundaryNote: string;
}

/** Lot progress from real package states — e.g. "7 / 10 measurements completed". */
export interface LotProgress {
  packagesTotal: number;
  sampled: number;
  measured: number;
  remaining: number;
  summary: string;
  action?: string | null;
}

export interface LotSummary {
  id: string;
  label: string;
  productId?: string | null;
  declaredValue: string;
  lotSize: number;
  location?: string | null;
  status: LotStatus;
  decision?: string | null;
  decisionReason?: string | null;
  decidedAt?: string | null;
  createdAt: string;
  progress: LotProgress;
}

export interface LotList {
  inspectionId: string;
  lots: LotSummary[];
  boundaryNote: string;
}

/** The measurement state of one lot package (real records only). */
export interface LotPackageMeasurement {
  taskId: string;
  taskStatus: VerificationTaskStatus;
  latestResult?: {
    id: string;
    measuredValue?: number | null;
    unit?: string | null;
    instrumentId?: string | null;
    instrumentVerificationStatus?: string | null;
    recordedBy: string;
    recordedAt: string;
    observation?: string | null;
  } | null;
  observed?: ObservedDifference | null;
  evaluation?: MeasurementEvaluation | null;
}

export interface LotPackage {
  id: string;
  label: string;
  packageId?: string | null;
  position: number;
  status: LotPackageStatus;
  samplingRunId?: string | null;
  measurement?: LotPackageMeasurement | null;
}

/** One audited, reproducible sample draw. */
export interface SamplingRun {
  id: string;
  sampleSize: number;
  selectionMethod: SamplingMethod;
  procedureCode?: string | null;
  procedureVersionLabel?: string | null;
  isAiRecommended: boolean;
  seed?: string | null;
  randomization: Record<string, unknown>;
  createdBy: string;
  createdAt: string;
}

/** The configured legal sampling procedure for the applicable version.
 * Null fields mean "not configured" — the UI must surface that fact. */
export interface SamplingProcedure {
  code: string;
  title: string;
  sampleSize?: number | null;
  method?: string | null;
  sourceReference?: string | null;
  versionLabel?: string | null;
}

/** OBSERVED statistics — computed from measurement rows that exist. */
export interface LotStatistics {
  sampled: number;
  measured: number;
  averageMeasured?: string | null;
  averageNote?: string | null;
  observedDeficiencies: number;
  exceedingThreshold: number;
  evaluated: number;
  note: string;
}

export interface LotDetail {
  id: string;
  inspectionId: string;
  label: string;
  productId?: string | null;
  declaredValue: string;
  lotSize: number;
  location?: string | null;
  notes?: string | null;
  status: LotStatus;
  decision?: string | null;
  decisionReason?: string | null;
  decidedBy?: string | null;
  decidedAt?: string | null;
  createdBy: string;
  createdAt: string;
  packages: LotPackage[];
  samplingRuns: SamplingRun[];
  samplingProcedure?: SamplingProcedure | null;
  statistics: LotStatistics;
  progress: LotProgress;
  boundaryNote: string;
}

/** POST /inspections/:id/lots — the declared quantity is stored verbatim and
 * is immutable after creation. */
export interface LotCreateRequest {
  label: string;
  declaredValue: string;
  lotSize: number;
  productId?: string | null;
  location?: string | null;
  notes?: string | null;
}

/** POST /lots/:id/sample. Without a configured legal procedure the run is
 * AI-recommended and REQUIRES confirmAiSample. */
export interface SampleGenerateRequest {
  sampleSize?: number | null;
  selectionMethod?: SamplingMethod;
  seed?: string | null;
  confirmAiSample?: boolean;
}

/** POST /lots/:id/decision — the explicit, evidence-gated lot result. */
export interface LotDecisionRequest {
  decision: LotStatus;
  reason: string;
}

/** UI-07 — the physical verification workload block on the department
 * dashboard. Every count is a real SQL COUNT; no number here is a
 * compliance signal. */
export interface PhysicalVerificationDashboard {
  inspectionsRequiringVerification: number;
  measurementsCompleted: number;
  lotsUnderVerification: number;
  lotsAwaitingMeasurement: number;
  lotsCompleted: number;
}

// --- Citizen Mode (UI-02) ----------------------------------------------------
// Anonymous consumer contracts: SCAN → DETECT → REVIEW → REPORT.
// A citizen scan is an automated screening of label declarations — the shapes
// themselves carry no compliance verdict vocabulary.

/** One declaration read from the label by the real OCR + extractor pipeline. */
export interface CitizenDetectedField {
  fieldType: string;
  label: string;
  rawText: string;
  normalizedValue?: string | null;
  confidence: number;
  status: ExtractionStatus;
}

/** Usability summary of the captured photo (readability, never compliance). */
export interface CitizenQualitySummary {
  grade?: ImageQualityGrade | null;
  score?: number | null;
  status?: string | null;
  readable: boolean;
}

/** POST/GET /citizen/scans — the anonymous screening result. */
export interface CitizenScanResult {
  id: string;
  reference: string;
  filename: string;
  quality: CitizenQualitySummary;
  outcome: CitizenScreenOutcome;
  outcomeRationale?: string | null;
  detectedFields: CitizenDetectedField[];
  ocrProvider?: string | null;
  ocrModel?: string | null;
  imageUrl?: string | null;
  createdAt: string;
}

/** POST /citizen/reports request body. */
export interface CitizenReportRequest {
  scanId: string;
  product: string;
  shop?: string;
  location?: string;
  issue: string;
  description?: string;
  reporterName?: string;
  reporterContact?: string;
}

/** POST/GET /citizen/reports — a submitted suspected-issue report. */
export interface CitizenReportResult {
  id: string;
  reference: string;
  scanId: string;
  status: CitizenReportStatus;
  product: string;
  shop?: string | null;
  location?: string | null;
  issue: string;
  description?: string | null;
  reporterName?: string | null;
  reporterContact?: string | null;
  createdAt: string;
  updatedAt?: string | null;
  isLive: boolean;
}

// --- Complaint lifecycle (UI-03) ----------------------------------------------
// A complaint IS a submitted citizen report, extended with the department
// intake lifecycle. All shapes mirror the backend's camelCase serialization;
// status values come from CITIZEN_REPORT_STATUSES and every transition is
// validated server-side — these types describe responses, never authorise them.

/** One REAL recorded event in a complaint's history (never fabricated). */
export interface ComplaintEvent {
  id: string;
  event: string;
  actorType: 'CITIZEN' | 'DEPARTMENT';
  actorName?: string | null;
  note?: string | null;
  createdAt: string;
}

/** The inspection created from a complaint (null until one exists). */
export interface ComplaintLinkedInspection {
  id: string;
  referenceNo: string;
  status: InspectionStatus;
}

/** A citizen's follow-up appended to a complaint's evidence (append-only). */
export interface ComplaintFollowUp {
  message: string;
  location?: string | null;
  at: string;
  imageUrl?: string | null;
}

/** Evidence snapshot attached at submission — never overwritten afterwards. */
export interface ComplaintEvidence {
  scanReference?: string | null;
  imageUrl?: string | null;
  quality?: Record<string, unknown> | null;
  detectedFields?: CitizenDetectedField[];
  citizenFollowUps?: ComplaintFollowUp[];
}

/** GET /citizen/reports/:id — complaint detail as the citizen sees it. */
export interface CitizenReportDetail extends CitizenReportResult {
  /** What the department asked the citizen for (while status is
   * REQUEST_INFORMATION). */
  pendingInfoRequest?: string | null;
  /** Real recorded events, oldest first. */
  events: ComplaintEvent[];
  inspection?: ComplaintLinkedInspection | null;
}

/** GET /citizen/complaints — one row of the department intake queue. */
export interface ComplaintSummary {
  id: string;
  reference: string;
  status: CitizenReportStatus;
  product: string;
  location?: string | null;
  issue: string;
  /** SYSTEM screening (deterministic, computed at submission). */
  screeningRisk?: string | null;
  /** OFFICIAL priority decision (department-only, set via transition). */
  officialPriority?: string | null;
  assignedInspectorId?: string | null;
  assignedInspectorName?: string | null;
  inspectionId?: string | null;
  inspectionReference?: string | null;
  /** UI-05: the linked inspection's own lifecycle status (null when the
   * complaint has not been converted) — drives the queue's inspection column. */
  inspectionStatus?: InspectionStatus | null;
  hasImageEvidence: boolean;
  /** Deterministic evidence-completeness score (0–100) — evidence, not violation likelihood. */
  evidenceCompleteness?: number | null;
  pendingInfoRequest?: string | null;
  createdAt: string;
  updatedAt?: string | null;
}

/** GET /citizen/complaints/:id — full review detail for the department. */
export interface ComplaintDetail extends ComplaintSummary {
  shop?: string | null;
  description?: string | null;
  reporterName?: string | null;
  reporterContact?: string | null;
  evidence: ComplaintEvidence;
  events: ComplaintEvent[];
  inspection?: ComplaintLinkedInspection | null;
}

/** GET /citizen/complaints/stats — real COUNT(*) values from the database. */
export interface ComplaintStats {
  total: number;
  submitted: number;
  underReview: number;
  requestInformation: number;
  accepted: number;
  assigned: number;
  inspectionPending: number;
  inspectionCompleted: number;
  actionTaken: number;
  closed: number;
  rejected: number;
  /** Open complaints with no assigned inspector. */
  unassignedOpen: number;
}

/** POST /citizen/complaints/:id/transition request body. */
export interface ComplaintTransitionRequest {
  action: ComplaintAction;
  /** Required for REJECT and REQUEST_INFORMATION. */
  reason?: string;
  /** Required for ASSIGN. */
  inspectorId?: string;
  /** Optional official priority decision (LOW | MEDIUM | HIGH). */
  officialPriority?: string;
}

/** GET /citizen/complaints/inspectors — users a complaint can be assigned to. */
export interface AssignableInspector {
  id: string;
  fullName: string;
  role: string;
}

/** GET /inspections/:id/source-complaint (UI-05) — the inspection brief:
 * WHY this targeted inspection exists, plus the immutable citizen evidence
 * that originated it. Everything here is *source evidence submitted by a
 * citizen* — a suspected issue to verify, never an official finding. */
export interface SourceComplaint {
  id: string;
  reference: string;
  status: CitizenReportStatus;
  product: string;
  shop?: string | null;
  location?: string | null;
  issue: string;
  description?: string | null;
  reporterName?: string | null;
  screeningRisk?: string | null;
  officialPriority?: string | null;
  assignedInspectorId?: string | null;
  assignedInspectorName?: string | null;
  evidence?: ComplaintEvidence | null;
  eventCount: number;
  createdAt: string;
}

/** POST /inspections/:id/assign request body (UI-05). */
export interface AssignInspectionRequest {
  inspectorId: string;
  note?: string;
  /** Must be true to move an inspection away from a formally assigned
   * inspector (explicit reassignment confirmation). */
  reassign?: boolean;
}

/** Queue filter params — filtering happens in SQL, never in the client. */
export interface ComplaintListParams {
  /** One status or several comma-separated (same enum, no second status system). */
  status?: string;
  risk?: string;
  assigned?: 'ASSIGNED' | 'UNASSIGNED';
  /** Filter on the complaint → inspection link. */
  inspection?: 'LINKED' | 'UNLINKED';
  /** Deterministic evidence-completeness band. */
  evidence?: 'COMPLETE' | 'PARTIAL' | 'MINIMAL';
  /** Only open complaints older than the attention threshold. */
  stale?: boolean;
  location?: string;
  search?: string;
}

/* ------------------------------------------------------------------------- */
/* UI-04 — Department Command Center (GET /department/dashboard)             */
/* ------------------------------------------------------------------------- */

/** Headline KPIs — every value is a real database COUNT. */
export interface DepartmentKpis {
  totalComplaints: number;
  pendingReview: number;
  highPriority: number;
  convertedToInspection: number;
  underInvestigation: number;
  resolved: number;
  rejected: number;
  unassignedOpen: number;
}

/** Complaints created on one UTC day (real created_at grouping, zero-filled). */
export interface ComplaintTrendPoint {
  date: string;
  count: number;
}

/** Deterministic evidence completeness over OPEN complaints. */
export interface EvidenceCompleteness {
  /** 0–100 average across scored complaints (0 when none exist). */
  average: number;
  scored: number;
  complete: number;
  partial: number;
  minimal: number;
}

/** One actionable "needs attention" signal with its queue filter. */
export interface AttentionItem {
  kind: string;
  label: string;
  description: string;
  count: number;
  /** Query params for the complaint queue — the filtered view to open. */
  filters: Record<string, string>;
}

/** CITIZEN → REPORT → REVIEW → PRIORITIZE → INSPECT → VERIFY → DECIDE counts. */
export interface DepartmentPipeline {
  citizenReports: number;
  departmentReview: number;
  accepted: number;
  inspectionAssigned: number;
  inspectionCompleted: number;
  decision: number;
}

/** Location rollup from real complaint locations. */
export interface LocationRollup {
  area: string;
  complaints: number;
  highPriority: number;
  inspections: number;
}

/** One real audit event from the department's complaint operations. */
export interface DepartmentActivity {
  id: string;
  event: string;
  actorName?: string | null;
  createdAt: string;
  /** Complaint reference (CMP-…) from the audit payload. */
  reference?: string | null;
  /** The complaint to open when clicked. */
  reportId?: string | null;
}

/** A priority-queue row with its triage signals. */
export interface PriorityComplaint {
  id: string;
  reference: string;
  status: CitizenReportStatus;
  product: string;
  issue: string;
  location?: string | null;
  /** Effective priority: official decision when set, else system screening. */
  priority?: string | null;
  prioritySource?: 'OFFICIAL_DECISION' | 'SYSTEM_SCREENING' | null;
  evidenceCompleteness: number;
  createdAt: string;
}

/** GET /department/dashboard — the aggregated, read-only command center payload. */
export interface DepartmentDashboard {
  generatedAt: string;
  windowDays: number;
  windowComplaints: number;
  kpis: DepartmentKpis;
  statusDistribution: Record<string, number>;
  trend: ComplaintTrendPoint[];
  /** Effective priority over OPEN complaints: HIGH / MEDIUM / LOW / UNSET. */
  riskDistribution: Record<string, number>;
  evidence: EvidenceCompleteness;
  physicalVerification: PhysicalVerificationDashboard;
  needsAttention: AttentionItem[];
  pipeline: DepartmentPipeline;
  locations: LocationRollup[];
  recentActivity: DepartmentActivity[];
  priorityQueue: PriorityComplaint[];
}

// --- Reporting & evidence pack (UI-08) -----------------------------------------
// Reports are decision-support artifacts generated from inspection evidence.
// They do not replace the authority of the authorized Legal Metrology
// inspector. Every payload carries the boundary note; every write is an
// authorised human action on the backend's gated lifecycle.

/** Mandated boundary statement attached to every report payload. */
export const REPORT_BOUNDARY_NOTE =
  'Reports are decision-support artifacts generated from inspection evidence. ' +
  'They do not replace the authority of the authorized Legal Metrology ' +
  'inspector.';

/** POST /reports — create the (single, per-inspection) report record. */
export interface ReportCreateRequest {
  inspectionId: string;
  note?: string;
}

/** POST /reports/:id/amend — the mandatory, explained amendment reason. */
export interface ReportAmendRequest {
  reason: string;
  note?: string;
}

/** One row of the Report Center list (real DB records only). */
export interface ReportSummary {
  id: string;
  inspectionId: string;
  inspectionReference: string;
  productName?: string | null;
  inspectionDate?: string | null;
  inspectorName?: string | null;
  result: string;
  status: ReportStatus;
  version: number;
  evidenceCount: number;
  generatedAt?: string | null;
  finalizedAt?: string | null;
  amendmentReason?: string | null;
  createdBy: string;
  updatedAt: string;
}

export interface ReportList {
  items: ReportSummary[];
  total: number;
  page: number;
  pageSize: number;
}

/** GET /reports/kpis — real group-by counts from the reports table. */
export interface ReportKpis {
  total: number;
  draft: number;
  finalized: number;
  exported: number;
  underReview: number;
  amended: number;
  requiresReview: number;
}

/** One finding frozen into a snapshot — engine status + human review state. */
export interface ReportSnapshotFinding {
  id: string;
  status: string;
  severity: string;
  requirement: string;
  ruleCode?: string | null;
  ruleVersion?: string | null;
  regulatoryVersionLabel?: string | null;
  detectedValue?: string | null;
  expectedValue?: string | null;
  explanation: string;
  reviewState: string;
  evidenceStatus: string;
  /** SOURCE (citizen scan) / OFFICIAL (inspection) — never merged. */
  source: string;
}

/** One physical measurement frozen into a snapshot. */
export interface ReportSnapshotMeasurement {
  measurementId: string;
  anchor: string;
  declaredValue?: string | null;
  measuredValue?: number | null;
  unit?: string | null;
  observedDifference?: string | null;
  instrumentId?: string | null;
  instrumentVerificationStatus?: string | null;
  recordedBy: string;
  recordedAt: string;
  evaluationStatus: string;
  evaluationOutcome?: string | null;
  evaluationRuleCode?: string | null;
}

/** One lot's observed statistics frozen into a snapshot. */
export interface ReportSnapshotLot {
  lotId: string;
  label: string;
  declaredValue: string;
  lotSize: number;
  sampled: number;
  measured: number;
  decision?: string | null;
  decisionReason?: string | null;
  samplingLabel: string;
}

/** The inspector's final decision frozen into a snapshot. */
export interface ReportSnapshotDecision {
  decision: string;
  reason?: string | null;
  decidedBy: string;
  decidedByName?: string | null;
  decidedAt: string;
  evaluationId?: string | null;
}

/** Regulatory basis of one frozen snapshot (engine output, quoted verbatim). */
export interface ReportSnapshotRegulatoryBasis {
  engineVersion?: string | null;
  regulatoryVersionLabel?: string | null;
  contextDate?: string | null;
  status: string;
  note?: string | null;
}

/** Planner status distilled for the report — REQUIRED vs RECOMMENDED. */
export interface ReportEvidenceCompleteness {
  requiredTotal: number;
  requiredOpen: number;
  recommendedOpen: number;
  evidenceItems: number;
  findingRows: number;
  counts: Record<string, number>;
  blockers: string[];
  canFinalize: boolean;
}

/** One immutable version row of the report's snapshot history. */
export interface ReportVersion {
  version: number;
  id: string;
  reason: string;
  createdAt: string;
  createdBy: string;
  createdByName?: string | null;
  statusAtCreation?: string | null;
}

/** One evidence-manifest entry: E-00N + a reference to an existing record. */
export interface ReportEvidenceItem {
  id: string;
  /** Stable identifier, e.g. "E-001". */
  ref: string;
  sequence: number;
  evidenceType: ReportEvidenceType | string;
  evidenceId: string;
  label: string;
  detail?: Record<string, unknown> | null;
}

/** Source context for complaint-originated inspections. */
export interface ReportSourceComplaint {
  reference: string;
  status: string;
  product?: string | null;
  location?: string | null;
  issue: string;
  description?: string | null;
  priority?: string | null;
  submittedAt?: string | null;
}

/**
 * The frozen snapshot — the ONLY input to exports, so later data changes can
 * never rewrite what an exported report claimed. Keys are camelCase; the
 * exact shape is versioned server-side.
 */
export interface ReportSnapshot {
  reportId: string;
  inspectionId: string;
  inspectionReference?: string | null;
  version: number;
  generatedAt?: string | null;
  result: string;
  inspection?: Record<string, unknown> | null;
  sourceComplaint?: Record<string, unknown> | null;
  findings?: ReportSnapshotFinding[];
  regulatoryBasis?: ReportSnapshotRegulatoryBasis[];
  measurements?: ReportSnapshotMeasurement[];
  lots?: ReportSnapshotLot[];
  decision?: Record<string, unknown> | null;
  completeness?: Record<string, unknown> | null;
  boundaryNote?: string;
  [key: string]: unknown;
}

/** GET /reports/:id — the full current read model. */
export interface ReportDetail {
  id: string;
  inspectionId: string;
  inspectionReference: string;
  status: ReportStatus;
  result: string;
  version: number;
  productName?: string | null;
  productCategory?: string | null;
  inspectionDate?: string | null;
  inspectionStatus?: string | null;
  inspectorName?: string | null;
  inspectorId?: string | null;
  createdBy: string;
  createdByName?: string | null;
  generatedAt?: string | null;
  finalizedAt?: string | null;
  finalizedBy?: string | null;
  finalizedByName?: string | null;
  amendmentReason?: string | null;
  sourceComplaint?: ReportSourceComplaint | null;
  evidence: ReportEvidenceCompleteness;
  versions: ReportVersion[];
  snapshot?: ReportSnapshot | null;
  boundaryNote: string;
}

/** One report-lifecycle audit event (from the shared append-only trail). */
export interface ReportAuditEvent {
  id: string;
  actorId?: string | null;
  actorRole?: string | null;
  actorName?: string | null;
  eventType: string;
  reportId?: string | null;
  inspectionId?: string | null;
  payload?: Record<string, unknown> | null;
  createdAt: string;
}

/** GET /reports/:id/evidence-pack — the exportable evidence bundle. */
export interface ReportEvidencePack {
  packId: string;
  reportId: string;
  inspectionId: string;
  reportVersion: number;
  createdAt: string;
  evidenceCount: number;
  completeness: ReportEvidenceCompleteness;
  items: ReportEvidenceItem[];
  sourceComplaint?: ReportSourceComplaint | null;
  decision?: ReportSnapshotDecision | null;
  auditEvents: ReportAuditEvent[];
  boundaryNote: string;
}

/** GET /reports/:id/audit — the report's slice of the audit trail. */
export interface ReportAudit {
  reportId: string;
  inspectionId: string;
  events: ReportAuditEvent[];
}

/* ========================================================================== */
/* UI-09 — Search, history & operational intelligence (read-only read models)  */
/*                                                                            */
/* Every shape here mirrors services/api/app/schemas/discovery.py and the     */
/* operational analytics schemas in app/schemas/analytics.py exactly. They     */
/* are READ models over existing entities: no new tables, no duplicated        */
/* detail pages. Privacy by construction: search results never carry citizen   */
/* reporter names/contacts, internal notes, credentials or storage keys.       */
/* ========================================================================== */

// ------------------------------------------------------------------- search

export interface SearchInspectionHit {
  id: string;
  reference: string;
  productName?: string | null;
  status: string;
  result: string;
  inspectorName?: string | null;
  source: string;
  createdAt: string;
}

export interface SearchComplaintHit {
  id: string;
  reference: string;
  status: string;
  product: string;
  issue: string;
  location?: string | null;
  inspectionId?: string | null;
  createdAt: string;
}

export interface SearchProductHit {
  id: string;
  name: string;
  category: string;
  gtin?: string | null;
  inspectionCount: number;
  lastInspectionAt?: string | null;
}

export interface SearchReportHit {
  id: string;
  inspectionId: string;
  inspectionReference: string;
  status: string;
  version: number;
  result: string;
}

export interface SearchFindingHit {
  id: string;
  inspectionId: string;
  inspectionReference: string;
  ruleCode?: string | null;
  status: string;
  severity: string;
  detectedValue?: string | null;
  createdAt: string;
}

export interface SearchEvidenceHit {
  id: string;
  inspectionId: string;
  inspectionReference: string;
  fieldType: string;
  value: string;
  imageId?: string | null;
  createdAt: string;
}

/** Grouped global-search results (UI-09 §2). */
export interface SearchResults {
  query: string;
  inspections: SearchInspectionHit[];
  complaints: SearchComplaintHit[];
  products: SearchProductHit[];
  reports: SearchReportHit[];
  findings: SearchFindingHit[];
  evidence: SearchEvidenceHit[];
}

// ------------------------------------------------------------------ history

/** The report state for one inspection (link chip + status). */
export interface HistoryReportRef {
  id: string;
  status: string;
  version: number;
}

export interface InspectionHistoryItem {
  id: string;
  reference: string;
  createdAt: string;
  productName?: string | null;
  productCategory?: string | null;
  inspectorName?: string | null;
  /** Reported shop/establishment when the inspection came from a complaint. */
  establishment?: string | null;
  source: string;
  sourceComplaintReference?: string | null;
  status: string;
  /** decision → evaluation status → NOT_EVALUATED (human outranks engine). */
  result: string;
  /** Real captured-evidence count (package images). */
  imageCount: number;
  report?: HistoryReportRef | null;
}

/** Real COUNT()s over the filtered history set — never hardcoded. */
export interface InspectionHistoryKpis {
  total: number;
  compliant: number;
  nonCompliant: number;
  reviewRequired: number;
  open: number;
}

/** /history/inspections — one server-side page + the filtered-set KPIs.
 * (Spelled out rather than extending api.ts's Paginated to avoid a circular
 * import; the wire shape is identical.) */
export interface HistoryPage {
  items: InspectionHistoryItem[];
  total: number;
  page: number;
  pageSize: number;
  kpis: InspectionHistoryKpis;
}

/** One REAL recorded event on an inspection's chain — never fabricated. */
export interface TimelineEvent {
  stage: string;
  label: string;
  eventType?: string | null;
  at: string;
  actorName?: string | null;
  detail?: string | null;
  reportId?: string | null;
  decision?: string | null;
}

export interface InspectionTimeline {
  inspectionId: string;
  reference: string;
  events: TimelineEvent[];
}

// ----------------------------------------------------------------- products

export interface ProductSummary {
  id: string;
  name: string;
  category: string;
  gtin?: string | null;
  inspectionCount: number;
  findingCount: number;
  lastInspectionAt?: string | null;
  /** NOT_EVALUATED when nothing was ever evaluated. */
  latestResult: string;
}

/** Latest detected declaration for one field type across inspections. */
export interface ProductDeclaredField {
  fieldType: string;
  rawText: string;
  normalizedValue?: string | null;
  unit?: string | null;
  inspectionId: string;
  inspectionReference: string;
  detectedAt: string;
}

export interface ProductInspectionRef {
  id: string;
  reference: string;
  createdAt: string;
  inspectorName?: string | null;
  result: string;
  report?: HistoryReportRef | null;
  source: string;
}

/** Recurring finding pattern — a HISTORICAL RECORD, never a verdict. */
export interface ProductFindingHistory {
  ruleCode?: string | null;
  label: string;
  occurrenceCount: number;
  inspectionCount: number;
  reviewRequiredCount: number;
  nonCompliantCount: number;
}

export interface ProductEvidenceImage {
  id: string;
  inspectionId: string;
  inspectionReference: string;
  imageType: string;
  originalFilename: string;
  createdAt: string;
  fieldTypes: string[];
}

export interface ProductDetail {
  id: string;
  name: string;
  category: string;
  gtin?: string | null;
  inspectionCount: number;
  findingCount: number;
  lastInspectionAt?: string | null;
  latestResult: string;
  declaredFields: ProductDeclaredField[];
  inspections: ProductInspectionRef[];
  findingsHistory: ProductFindingHistory[];
  evidenceGallery: ProductEvidenceImage[];
  /** Honesty contract: history proves nothing about the current package. */
  boundaryNote: string;
}

// --------------------------------------------------- operational analytics

export interface OperationalKpis {
  totalInspections: number;
  complaintLedInspections: number;
  decidedInspections: number;
  /** null when there is no decided denominator — the UI shows N/A, never 0%. */
  complianceRate?: number | null;
  nonComplianceRate?: number | null;
  reviewRequired: number;
  openInspections: number;
  averageEvidenceCompleteness?: number | null;
}

export interface TrendPoint {
  /** ISO period label (day/week/month bucket). */
  period: string;
  count: number;
}

export interface OutcomeSlice {
  result: string;
  count: number;
  percentage?: number | null;
}

export interface ComplaintPipelineStage {
  stage: string;
  label: string;
  count: number;
}

export interface ComplaintPipeline {
  stages: ComplaintPipelineStage[];
  conversionRate?: number | null;
}

export interface EvidenceQualityMetrics {
  inspectionsWithPlanner: number;
  averageEvidenceCompleteness?: number | null;
  incompleteInspections: number;
  missingRequiredEvidence: number;
  measurementsPending: number;
  reportsBlockedByEvidence: number;
}

export interface FindingCategorySlice {
  ruleCode: string;
  label: string;
  count: number;
  inspectionCount: number;
  percentage?: number | null;
}

export interface RepeatFindingPattern {
  productName: string;
  ruleCode: string;
  label: string;
  inspectionCount: number;
  occurrenceCount: number;
}

export interface LocationSlice {
  location: string;
  complaintCount: number;
  inspectionCount: number;
  findingCount: number;
}

export interface LocationIntelligence {
  locations: LocationSlice[];
  sufficient: boolean;
  note?: string | null;
}

export interface ReportAnalytics {
  generated: number;
  finalized: number;
  amended: number;
  pdfExports: number;
  docxExports: number;
}

/** GET /analytics/operational — server-side aggregation, real DB data only. */
export interface OperationalAnalytics {
  kpis: OperationalKpis;
  trend: TrendPoint[];
  granularity: string;
  outcomes: OutcomeSlice[];
  complaintPipeline: ComplaintPipeline;
  evidenceQuality: EvidenceQualityMetrics;
  findingCategories: FindingCategorySlice[];
  repeatFindings: RepeatFindingPattern[];
  locations: LocationIntelligence;
  reports: ReportAnalytics;
  /** Present when the dataset is small — honest labelling, never fake stats. */
  dataNote?: string | null;
  generatedAt: string;
}
