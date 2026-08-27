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
  EvidenceType,
  FieldType,
  ImageProcessingStatus,
  ImageQualityGrade,
  ImageQualityStatus,
  ImageType,
  InspectionStatus,
  ModelServiceType,
  PackageStatus,
  RegionType,
  RegulationVersionStatus,
  ReviewActionType,
  RuleStatus,
  BatchStatus,
  UserRole,
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
}

// --- Regulatory knowledge system -------------------------------------------

export interface Regulation {
  id: string;
  code: string;
  title: string;
  jurisdiction: string;
  authority: string;
  description?: string | null;
  officialSourceUrl?: string | null;
  isDemo: boolean;
  createdAt: string;
}

export interface RegulationVersion {
  id: string;
  regulationId: string;
  versionLabel: string;
  status: RegulationVersionStatus;
  effectiveFrom?: string | null;
  effectiveUntil?: string | null;
  amendmentOfId?: string | null;
  sourceDocumentRef?: string | null;
  isDemo: boolean;
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
