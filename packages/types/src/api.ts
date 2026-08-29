/**
 * API request/response contracts for LEGALMET AI.
 *
 * Mirrors the live FastAPI contract (OpenAPI schema at `/openapi.json`, Swagger
 * UI at `/docs`); see also docs/architecture.md → "API layer". Response
 * envelopes are intentionally explicit so the frontend never has to guess the
 * shape.
 */
import type {
  AuditEvent,
  ComplianceEvaluation,
  ComplianceFinding,
  ComplianceRuleConfig,
  DashboardSummary,
  EngineFinding,
  EngineInfo,
  Evidence,
  EvidenceGraph,
  EvidenceGraphVocabulary,
  EvidenceTraceGraph,
  FieldCandidates,
  Inspection,
  InspectionComplianceStatus,
  Package,
  PackageImage,
  Product,
  Regulation,
  RegulationVersion,
  RegulatoryRequirement,
  RegulatoryRequirementDetail,
  RegulatorySource,
  ReviewAction,
  Rule,
  User,
  VersionSelection,
} from './models';
import type { ComplianceStatus, ImageType, ReviewActionType } from './enums';

/** Standard structured error envelope returned for every non-2xx response. */
export interface ApiError {
  error: {
    code: string;
    message: string;
    details?: unknown;
    requestId?: string;
  };
}

/** Generic list envelope. */
export interface Paginated<T> {
  items: T[];
  total: number;
  page: number;
  pageSize: number;
}

// --- Health ----------------------------------------------------------------

/** Liveness/health probe payload (mirrors backend `schemas/common.HealthResponse`). */
export interface HealthResponse {
  status: string;
  service: string;
  version: string;
  environment: string;
}

// --- Auth ------------------------------------------------------------------

export interface LoginRequest {
  email: string;
  password: string;
}

export interface AuthTokenResponse {
  accessToken: string;
  tokenType: 'bearer';
  expiresIn: number;
  user: User;
}

// --- Inspections -----------------------------------------------------------

export interface CreateInspectionRequest {
  productName: string;
  productCategory: string;
  gtin?: string;
  note?: string;
  batchId?: string;
}

export interface AnalyzeInspectionRequest {
  /** Optional inspection context date (ISO). Drives version-aware rule selection. */
  contextDate?: string;
}

export interface RegisterImageRequest {
  originalFilename: string;
  mimeType: string;
  imageType?: ImageType;
  /** Base64 image payload OR a pre-uploaded storage key. Foundation phase accepts either. */
  contentBase64?: string;
  storageKey?: string;
  width?: number;
  height?: number;
  fileSize?: number;
}

// --- Real package intake (Prompt 3) ----------------------------------------
// Single/batch uploads are multipart/form-data (a raw file part plus optional
// captureSource/imageType/packageId form fields), so they have no JSON request
// body type here. These are the JSON shapes the intake endpoints return.

export interface CreatePackageRequest {
  label?: string;
}

export interface BatchUploadItemResult {
  filename: string;
  /** "UPLOADED" | "REJECTED" */
  status: string;
  image?: PackageImage | null;
  error?: { code: string; message: string } | null;
}

export interface BatchUploadResponse {
  items: BatchUploadItemResult[];
  uploaded: number;
  rejected: number;
}

// --- Review ----------------------------------------------------------------

export interface ReviewFindingRequest {
  action: ReviewActionType;
  correctedStatus?: ComplianceStatus;
  reason?: string;
  note?: string;
}

// --- Convenience response aliases ------------------------------------------

export type InspectionResponse = Inspection;
export type InspectionListResponse = Paginated<Inspection>;
export type PackageResponse = Package;
export type ImageResponse = PackageImage;
export type FindingListResponse = { items: ComplianceFinding[] };
export type EvidenceListResponse = { items: Evidence[] };
export type EvidenceGraphResponse = EvidenceGraph;
export type ReviewActionResponse = ReviewAction;
export type RuleListResponse = Paginated<Rule>;
export type RegulationListResponse = {
  items: (Regulation & { versions?: RegulationVersion[] })[];
};

// --- Regulatory intelligence (Prompt 5) ---------------------------------------

export type RegulatorySourceListResponse = RegulatorySource[];
export type RegulatoryDocumentListResponse = Regulation[];
export type RegulatoryVersionListResponse = RegulationVersion[];
export type RegulatoryRequirementListResponse = Paginated<RegulatoryRequirement>;
export type RegulatoryRequirementResponse = RegulatoryRequirementDetail;
export type VersionSelectionResponse = VersionSelection;
export type FieldCandidatesResponse = FieldCandidates;

// --- Deterministic compliance engine (Prompt 6) --------------------------------

export type EvaluateInspectionResponse = {
  evaluation: ComplianceEvaluation;
  boundaryNote: string;
};
export type ComplianceStatusResponse = InspectionComplianceStatus;
export type EngineFindingsListResponse = EngineFinding[];
export type ComplianceEvaluationResponse = ComplianceEvaluation;
export type EngineFindingResponse = EngineFinding;
export type EngineInfoResponse = EngineInfo;
export type ComplianceReviewQueueResponse = Paginated<EngineFinding>;
export type ComplianceRuleListResponse = ComplianceRuleConfig[];

export type AuditListResponse = { items: AuditEvent[] };
export type DashboardResponse = DashboardSummary;
export type ProductResponse = Product;
export type UserResponse = User;

// --- Evidence traceability graph (Prompt 7) -----------------------------------

/** GET /inspections/{id}/evidence-graph (full) — same shape for all three roots. */
export type EvidenceTraceGraphResponse = EvidenceTraceGraph;
/** GET /evidence-graph — strength vocabulary + boundary note. */
export type EvidenceGraphVocabularyResponse = EvidenceGraphVocabulary;
