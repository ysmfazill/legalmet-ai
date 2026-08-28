/**
 * Domain entity DTOs — the JSON shapes returned by the LEGALMET AI API.
 *
 * Convention: the API serialises using camelCase (configured in the backend via
 * a Pydantic alias generator), so these interfaces use camelCase throughout.
 *
 * `isDemo` appears on any entity that may currently be backed by placeholder /
 * mock data during the foundation phase. The UI uses it to render a clear
 * "DEMO DATA — NOT LEGAL ADVICE" marker. It must never be silently dropped.
 */
import type {
  AuditEventType,
  CaptureSource,
  ComplianceStatus,
  DocumentType,
  EvidenceType,
  ExtractionStatus,
  FieldType,
  ImageProcessingStatus,
  ImageQualityGrade,
  ImageQualityStatus,
  ImageType,
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
  batchId?: string | null;
  note?: string | null;
  isDemo: boolean;
  createdAt: string;
  updatedAt: string;
  completedAt?: string | null;
  packages?: Package[];
  findingCounts?: FindingCounts;
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
