/**
 * Typed API client for the METRASIGHT backend.
 *
 * Two transports live here:
 *   - `request()` — JSON over `fetch`, used for every non-upload call. It injects
 *     the bearer token, serialises JSON bodies and unwraps the structured error
 *     envelope into an {@link ApiClientError}.
 *   - `xhrUpload()` — multipart over `XMLHttpRequest`, the only reliable way to
 *     get real upload-progress events in the browser. Used for single + batch
 *     image intake (Prompt 3).
 *
 * All shapes come from the shared `@legalmet/types` contract, so the client
 * never invents field names.
 *
 * IMPORTANT: nothing here interprets an upload as a compliance result. Uploading
 * an image yields storage + a usability grade only; the strongest lifecycle
 * outcome the intake API can reach is READY_FOR_ANALYSIS.
 */
import type {
  ApiError,
  AssignInspectionRequest,
  AuditEvent,
  AuthTokenResponse,
  BatchUploadResponse,
  CaptureSource,
  CitizenReportDetail,
  CitizenReportRequest,
  CitizenReportResult,
  CitizenScanResult,
  ComplaintDetail,
  ComplaintListParams,
  ComplaintStats,
  ComplaintSummary,
  ComplaintTransitionRequest,
  AssignableInspector,
  CreateInspectionRequest,
  CreatePackageRequest,
  DecisionHistory,
  DecisionRequest,
  DepartmentDashboard,
  EngineFinding,
  EngineInfo,
  EvidenceGraphVocabulary,
  EvidenceTraceGraph,
  ExtractedField,
  FieldCandidates,
  FieldCorrectRequest,
  FieldCorrection,
  FieldReview,
  FindingReview,
  FindingReviewActionRequest,
  HealthResponse,
  ImageRegion,
  ImageType,
  Inspection,
  InspectionComplianceStatus,
  InspectionDecision,
  ComplianceEvaluation,
  OcrTextResult,
  Package,
  PackageImage,
  Paginated,
  PerceptionAnalysis,
  PerceptionKickoff,
  ProcessingRun,
  ProcessingRunDetail,
  Regulation,
  RegulationVersion,
  RegulatoryRequirement,
  RegulatoryRequirementDetail,
  RegulatorySource,
  ReviewStatus,
  SourceComplaint,
  User,
  VerificationCreateRequest,
  VerificationList,
  VerificationResultRequest,
  VerificationTask,
  EvidencePlan,
  LotCreateRequest,
  LotDecisionRequest,
  LotDetail,
  LotList,
  MeasurementHistory,
  SampleGenerateRequest,
  SamplingRun,
  VersionSelection,
  ReportAudit,
  ReportCreateRequest,
  ReportDetail,
  ReportEvidencePack,
  ReportKpis,
  ReportList,
  ReportAmendRequest,
  SearchResults,
  HistoryPage,
  InspectionTimeline,
  ProductSummary,
  ProductDetail,
  OperationalAnalytics,
} from '@legalmet/types';

/** Base URL for all API calls. Dev default is proxied by Vite to the backend. */
export const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? '/api/v1';

/** Thrown for any non-2xx response, carrying the backend's error envelope. */
export class ApiClientError extends Error {
  readonly status: number;
  readonly payload: ApiError | null;

  constructor(status: number, payload: ApiError | null, message: string) {
    super(message);
    this.name = 'ApiClientError';
    this.status = status;
    this.payload = payload;
  }

  /** The backend error code (e.g. `INVALID_IMAGE`), when present. */
  get code(): string | undefined {
    return this.payload?.error?.code;
  }
}

/* -------------------------------------------------------------------------- */
/* Auth token                                                                 */
/* -------------------------------------------------------------------------- */
// Persisted so a page reload keeps the dev session; falls back to in-memory
// only when storage is unavailable (private mode, SSR, tests).
const TOKEN_KEY = 'legalmet.token';

function readStoredToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

let authToken: string | null = readStoredToken();

export function getToken(): string | null {
  return authToken;
}

export function setToken(token: string | null): void {
  authToken = token;
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    // Storage unavailable — the in-memory token still works for this session.
  }
}

function authHeaders(extra?: Record<string, string>): Record<string, string> {
  return {
    ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
    ...(extra ?? {}),
  };
}

async function toClientError(response: Response): Promise<ApiClientError> {
  let payload: ApiError | null = null;
  try {
    payload = (await response.json()) as ApiError;
  } catch {
    // Non-JSON error body — fall back to a generic message.
  }
  const message = payload?.error?.message ?? `Request failed with status ${response.status}`;
  return new ApiClientError(response.status, payload, message);
}

/* -------------------------------------------------------------------------- */
/* JSON transport                                                             */
/* -------------------------------------------------------------------------- */
interface RequestOptions extends Omit<RequestInit, 'body' | 'headers'> {
  /** JSON-serialisable request body. Omit for GET/DELETE/empty POST. */
  body?: unknown;
  headers?: Record<string, string>;
}

async function request<T>(path: string, init: RequestOptions = {}): Promise<T> {
  const { body, headers, ...rest } = init;
  const hasBody = body !== undefined;
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...rest,
    headers: authHeaders({
      ...(hasBody ? { 'Content-Type': 'application/json' } : {}),
      ...(headers ?? {}),
    }),
    body: hasBody ? JSON.stringify(body) : undefined,
  });

  if (!response.ok) throw await toClientError(response);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

/* -------------------------------------------------------------------------- */
/* Multipart transport (with upload progress)                                 */
/* -------------------------------------------------------------------------- */
export interface UploadProgress {
  loaded: number;
  total: number;
  /** 0..100, rounded. */
  percent: number;
}

interface XhrOptions {
  onProgress?: (progress: UploadProgress) => void;
  signal?: AbortSignal;
}

function xhrUpload<T>(path: string, form: FormData, opts: XhrOptions = {}): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', `${API_BASE_URL}${path}`);
    if (authToken) xhr.setRequestHeader('Authorization', `Bearer ${authToken}`);
    // Deliberately no Content-Type: the browser sets the multipart boundary.

    if (opts.onProgress && xhr.upload) {
      xhr.upload.onprogress = (event) => {
        if (event.lengthComputable) {
          opts.onProgress!({
            loaded: event.loaded,
            total: event.total,
            percent: Math.round((event.loaded / event.total) * 100),
          });
        }
      };
    }

    xhr.onload = () => {
      let parsed: unknown = null;
      try {
        parsed = xhr.responseText ? JSON.parse(xhr.responseText) : null;
      } catch {
        // leave parsed = null
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(parsed as T);
        return;
      }
      const payload =
        parsed && typeof parsed === 'object' && 'error' in parsed ? (parsed as ApiError) : null;
      const message = payload?.error?.message ?? `Upload failed with status ${xhr.status}`;
      reject(new ApiClientError(xhr.status, payload, message));
    };
    xhr.onerror = () => reject(new ApiClientError(0, null, 'Network error during upload'));
    xhr.onabort = () => reject(new ApiClientError(0, null, 'Upload cancelled'));

    if (opts.signal) {
      if (opts.signal.aborted) {
        xhr.abort();
        return;
      }
      opts.signal.addEventListener('abort', () => xhr.abort());
    }

    xhr.send(form);
  });
}

/**
 * Fetch a stored object (original or processed derivative) as an object URL.
 *
 * The `/storage` endpoint is bearer-authenticated, so a plain `<img src>` can't
 * load it — we fetch the bytes with the token and hand back a blob URL. Callers
 * MUST `URL.revokeObjectURL(url)` when the image unmounts to avoid leaks.
 */
export async function fetchObjectUrl(storageKey: string, signal?: AbortSignal): Promise<string> {
  const response = await fetch(`${API_BASE_URL}/storage/${storageKey}`, {
    headers: authHeaders(),
    signal,
  });
  if (!response.ok) throw await toClientError(response);
  const blob = await response.blob();
  return URL.createObjectURL(blob);
}

/* -------------------------------------------------------------------------- */
/* Upload option shapes                                                       */
/* -------------------------------------------------------------------------- */
export interface UploadImageOptions extends XhrOptions {
  captureSource?: CaptureSource;
  imageType?: ImageType;
  packageId?: string;
}

export interface BatchUploadOptions extends XhrOptions {
  packageId?: string;
}

/* -------------------------------------------------------------------------- */
/* API surface                                                                */
/* -------------------------------------------------------------------------- */
export const api = {
  baseUrl: API_BASE_URL,

  /** GET /health — unauthenticated liveness probe. */
  health: (): Promise<HealthResponse> => request<HealthResponse>('/health'),

  // --- auth ----------------------------------------------------------------
  /** POST /auth/login — exchanges credentials for a JWT and stores it. */
  async login(email: string, password: string): Promise<AuthTokenResponse> {
    const result = await request<AuthTokenResponse>('/auth/login', {
      method: 'POST',
      body: { email, password },
    });
    setToken(result.accessToken);
    return result;
  },
  /** GET /auth/me — the currently authenticated user. */
  me: (): Promise<User> => request<User>('/auth/me'),
  /** Drop the stored token (there is no server-side session to revoke). */
  logout: (): void => setToken(null),

  // --- inspections ---------------------------------------------------------
  createInspection: (body: CreateInspectionRequest): Promise<Inspection> =>
    request<Inspection>('/inspections', { method: 'POST', body }),
  getInspection: (id: string): Promise<Inspection> => request<Inspection>(`/inspections/${id}`),
  /**
   * Live inspections from the backend. Paginated; `pageSize: 100` covers the
   * demo database comfortably. Use for LIVE views — never mix with the
   * labelled demo adapter.
   */
  listInspections: (params: { page?: number; pageSize?: number } = {}): Promise<
    Paginated<Inspection>
  > => request<Paginated<Inspection>>('/inspections' + querySuffix(params)),

  // --- Complaint → targeted inspection (UI-05) -------------------------------
  /** GET /inspections/:id/source-complaint — the brief + immutable citizen
   * evidence behind a TARGETED inspection. 404 when the inspection did not
   * originate from a complaint. */
  getInspectionSourceComplaint: (inspectionId: string): Promise<SourceComplaint> =>
    request<SourceComplaint>(`/inspections/${inspectionId}/source-complaint`),

  /**
   * POST /inspections/:id/assign — SUPERVISOR/ADMIN only (a department act,
   * enforced by the backend). Assigns the inspector, audits it, and keeps the
   * source complaint in sync. Moving away from a formally assigned inspector
   * requires `reassign: true`.
   */
  assignInspection: (
    inspectionId: string,
    body: AssignInspectionRequest,
  ): Promise<Inspection> =>
    request<Inspection>(`/inspections/${inspectionId}/assign`, {
      method: 'POST',
      body,
    }),

  // --- real package intake (Prompt 3) --------------------------------------
  createPackage: (inspectionId: string, body: CreatePackageRequest = {}): Promise<Package> =>
    request<Package>(`/inspections/${inspectionId}/packages`, { method: 'POST', body }),

  listImages: (inspectionId: string): Promise<PackageImage[]> =>
    request<PackageImage[]>(`/inspections/${inspectionId}/images`),

  uploadImage: (
    inspectionId: string,
    file: File | Blob,
    opts: UploadImageOptions = {},
  ): Promise<PackageImage> => {
    const form = new FormData();
    const name = file instanceof File ? file.name : 'capture.jpg';
    form.append('file', file, name);
    if (opts.captureSource) form.append('captureSource', opts.captureSource);
    if (opts.imageType) form.append('imageType', opts.imageType);
    if (opts.packageId) form.append('packageId', opts.packageId);
    return xhrUpload<PackageImage>(`/inspections/${inspectionId}/images/upload`, form, opts);
  },

  batchUpload: (
    inspectionId: string,
    files: File[],
    opts: BatchUploadOptions = {},
  ): Promise<BatchUploadResponse> => {
    const form = new FormData();
    for (const file of files) form.append('files', file, file.name);
    if (opts.packageId) form.append('packageId', opts.packageId);
    return xhrUpload<BatchUploadResponse>(`/inspections/${inspectionId}/images/batch`, form, opts);
  },

  qualityCheck: (imageId: string): Promise<PackageImage> =>
    request<PackageImage>(`/images/${imageId}/quality-check`, { method: 'POST' }),

  prepareImage: (imageId: string): Promise<PackageImage> =>
    request<PackageImage>(`/images/${imageId}/prepare`, { method: 'POST' }),

  deleteImage: (imageId: string): Promise<void> =>
    request<void>(`/images/${imageId}`, { method: 'DELETE' }),

  /** POST /inspections/{id}/ready — the strongest intake outcome. No analysis. */
  markReady: (inspectionId: string): Promise<Inspection> =>
    request<Inspection>(`/inspections/${inspectionId}/ready`, { method: 'POST' }),

  // --- Perception (Prompt 4) --------------------------------------------------
  // These endpoints surface what the system PERCEIVED on real package images:
  // OCR text, visual regions and extracted declaration candidates with
  // evidence links. They never return a compliance verdict — the strongest
  // statement available is "awaiting regulatory evaluation".

  /** Queue a perception run for every usable image (202 + poll). */
  startPerception: (inspectionId: string): Promise<PerceptionKickoff> =>
    request<PerceptionKickoff>(`/inspections/${inspectionId}/perceive`, { method: 'POST' }),

  /** Queue a NEW run for one image; prior runs are preserved as history. */
  reanalyzeImage: (imageId: string): Promise<PerceptionKickoff> =>
    request<PerceptionKickoff>(`/images/${imageId}/reanalyze`, { method: 'POST' }),

  getPerceptionAnalysis: (inspectionId: string): Promise<PerceptionAnalysis> =>
    request<PerceptionAnalysis>(`/inspections/${inspectionId}/analysis`),

  listOcrResults: (inspectionId: string): Promise<OcrTextResult[]> =>
    request<OcrTextResult[]>(`/inspections/${inspectionId}/ocr`),

  listRegions: (inspectionId: string): Promise<ImageRegion[]> =>
    request<ImageRegion[]>(`/inspections/${inspectionId}/regions`),

  listFields: (inspectionId: string): Promise<ExtractedField[]> =>
    request<ExtractedField[]>(`/inspections/${inspectionId}/fields`),

  listProcessingRuns: (inspectionId: string): Promise<ProcessingRun[]> =>
    request<ProcessingRun[]>(`/inspections/${inspectionId}/processing`),

  getProcessingRun: (runId: string): Promise<ProcessingRunDetail> =>
    request<ProcessingRunDetail>(`/processing-runs/${runId}`),

  fetchObjectUrl,

  // --- Regulatory intelligence (Prompt 5) -------------------------------------
  // Read models over the SOURCE → DOCUMENT → VERSION → REQUIREMENT hierarchy.
  // These endpoints never return a compliance verdict: the strongest statement
  // they make about a detected field is "candidate requirement — applicability
  // not evaluated, awaiting the compliance engine".

  listRegulatorySources: (params: {
    verificationStatus?: string;
    sourceType?: string;
  } = {}): Promise<RegulatorySource[]> =>
    request<RegulatorySource[]>('/regulations/sources' + querySuffix(params)),

  getRegulatorySource: (sourceId: string): Promise<RegulatorySource> =>
    request<RegulatorySource>(`/regulations/sources/${sourceId}`),

  /** ADMIN-only, audited verification-state change (before/after recorded). */
  updateSourceVerification: (
    sourceId: string,
    body: { verificationStatus: string; verificationNote?: string | null },
  ): Promise<RegulatorySource> =>
    request<RegulatorySource>(`/regulations/sources/${sourceId}`, {
      method: 'PATCH',
      body,
    }),

  listRegulatoryDocuments: (params: {
    sourceId?: string;
    documentType?: string;
    isDemo?: boolean;
  } = {}): Promise<Regulation[]> =>
    request<Regulation[]>('/regulations/documents' + querySuffix(params)),

  getRegulatoryDocument: (documentId: string): Promise<Regulation> =>
    request<Regulation>(`/regulations/documents/${documentId}`),

  listRegulatoryVersions: (params: {
    documentId?: string;
    status?: string;
    effectiveOn?: string;
  } = {}): Promise<RegulationVersion[]> =>
    request<RegulationVersion[]>('/regulations/versions' + querySuffix(params)),

  /** Deterministic effective-date selection (never falls back to newest). */
  resolveRegulatoryVersion: (documentId: string, on: string): Promise<VersionSelection> =>
    request<VersionSelection>(
      '/regulations/versions/resolve' + querySuffix({ documentId, on }),
    ),

  listRegulatoryRequirements: (params: {
    versionId?: string;
    documentId?: string;
    sourceId?: string;
    fieldKey?: string;
    requirementType?: string;
    category?: string;
    status?: string;
    effectiveOn?: string;
    current?: boolean;
    isDemo?: boolean;
    page?: number;
    pageSize?: number;
  } = {}): Promise<Paginated<RegulatoryRequirement>> =>
    request<Paginated<RegulatoryRequirement>>(
      '/regulations/requirements' + querySuffix(params),
    ),

  getRegulatoryRequirement: (requirementId: string): Promise<RegulatoryRequirementDetail> =>
    request<RegulatoryRequirementDetail>(`/regulations/requirements/${requirementId}`),

  /**
   * Map an inspection's perceived fields to candidate requirement definitions.
   * Every mapping is marked applicability-not-evaluated / awaiting the
   * compliance engine — never a compliance verdict.
   */
  getFieldCandidates: (inspectionId: string, on?: string): Promise<FieldCandidates> =>
    request<FieldCandidates>(
      `/inspections/${inspectionId}/regulatory-candidates` + querySuffix({ on }),
    ),

  // --- Deterministic compliance engine (Prompt 6) -----------------------------
  // Runs the deterministic evaluation over an inspection's perceived evidence
  // and the regulatory version in force. Findings are SYSTEM decision-support
  // outputs — every payload carries the boundary note. There is no
  // approve/reject call here: the inspector's final decision is a later phase.

  /** Run one evaluation — a NEW run each time; history is never overwritten. */
  evaluateCompliance: (inspectionId: string): Promise<ComplianceEvaluation> =>
    request<{ evaluation: ComplianceEvaluation }>(
      `/inspections/${inspectionId}/evaluate`,
      { method: 'POST', body: {} },
    ).then((r) => r.evaluation),

  /** Latest evaluation for an inspection, or an explicit NOT_EVALUATED. */
  getComplianceStatus: (inspectionId: string): Promise<InspectionComplianceStatus> =>
    request<InspectionComplianceStatus>(`/inspections/${inspectionId}/compliance`),

  /** Findings of the LATEST evaluation (engine vocabulary, not the demo flow). */
  listEngineFindings: (inspectionId: string): Promise<EngineFinding[]> =>
    request<EngineFinding[]>(`/inspections/${inspectionId}/compliance/findings`),

  /** One historical evaluation — reproducible, byte-identical to its run. */
  getComplianceEvaluation: (evaluationId: string): Promise<ComplianceEvaluation> =>
    request<ComplianceEvaluation>(`/compliance/evaluations/${evaluationId}`),

  /** One finding with its deterministic explanation and provenance snapshot. */
  getEngineFinding: (findingId: string): Promise<EngineFinding> =>
    request<EngineFinding>(`/compliance/findings/${findingId}`),

  /** Engine metadata: version, rule-type vocabulary, no-LLM contract. */
  getEngineInfo: (): Promise<EngineInfo> => request<EngineInfo>('/compliance/engine'),

  /**
   * Read-only review queue: system findings whose inspector decision is
   * pending. COMPLIANT / NOT_APPLICABLE findings are never queued.
   */
  listComplianceReviewQueue: (params: {
    page?: number;
    pageSize?: number;
  } = {}): Promise<Paginated<EngineFinding>> =>
    request<Paginated<EngineFinding>>('/compliance/review/queue' + querySuffix(params)),

  // --- Evidence traceability graph (Prompt 7) -----------------------------------
  // Read-only traceability over REAL persisted records: images, OCR, regions,
  // extracted fields, regulatory sources/documents/versions/requirements,
  // rules, evaluations, findings and audit events. These endpoints never
  // write, never decide compliance, and expose no credentials or storage
  // paths in node metadata.

  /**
   * Full evidence graph for one inspection (latest evaluation, or a historical
   * one via `evaluationId` — the frozen provenance of that run is traced).
   */
  getInspectionEvidenceGraph: (
    inspectionId: string,
    evaluationId?: string,
  ): Promise<EvidenceTraceGraph> =>
    request<EvidenceTraceGraph>(
      `/inspections/${inspectionId}/evidence-graph` + querySuffix({ evaluationId }),
    ),

  /**
   * Focused trace for ONE engine finding, both directions:
   * Finding → Rule → Requirement → Version → Document → Source AND
   * Finding → Field → OCR → Region → Image.
   */
  getFindingEvidenceGraph: (findingId: string): Promise<EvidenceTraceGraph> =>
    request<EvidenceTraceGraph>(`/compliance/findings/${findingId}/evidence-graph`),

  /**
   * Reverse trace for ONE extracted field: its evidence chain plus every
   * finding that used this field as evidence.
   */
  getFieldEvidenceGraph: (fieldId: string): Promise<EvidenceTraceGraph> =>
    request<EvidenceTraceGraph>(`/fields/${fieldId}/evidence-graph`),

  /** Node/edge/evidence-strength vocabulary + the traceability boundary note. */
  getEvidenceGraphVocabulary: (): Promise<EvidenceGraphVocabulary> =>
    request<EvidenceGraphVocabulary>('/evidence-graph'),

  // --- Human-in-the-loop review & decision (Prompt 8) ---------------------------
  // AI ASSISTS. THE INSPECTOR DECIDES. These calls record AUTHORISED HUMAN
  // actions only — the engine has no corresponding write path. The backend
  // enforces roles (INSPECTOR/SUPERVISOR/ADMIN write, AUDITOR read-only),
  // the review state machine, and the decision gate; this client merely
  // surfaces the results and errors honestly.

  /** Inspector corrects one extracted value. The AI original is never overwritten. */
  correctField: (
    fieldId: string,
    body: FieldCorrectRequest,
  ): Promise<FieldCorrection> =>
    request<FieldCorrection>(`/fields/${fieldId}/correct`, {
      method: 'POST',
      body,
    }),

  /** Append-only correction history of one field (oldest first). */
  listFieldCorrections: (fieldId: string): Promise<FieldCorrection[]> =>
    request<FieldCorrection[]>(`/fields/${fieldId}/corrections`),

  /** Original AI value vs the latest human correction of one field. */
  getFieldReview: (fieldId: string): Promise<FieldReview> =>
    request<FieldReview>(`/fields/${fieldId}/review`),

  /** Apply one review action (CONFIRM/CORRECT/REJECT/OVERRIDE/ESCALATE). */
  reviewFinding: (
    findingId: string,
    body: FindingReviewActionRequest,
  ): Promise<FindingReview> =>
    request<FindingReview>(`/compliance/findings/${findingId}/review`, {
      method: 'POST',
      body,
    }),

  /** The review state + full transition history of one finding. */
  getFindingReview: (findingId: string): Promise<FindingReview> =>
    request<FindingReview>(`/compliance/findings/${findingId}/review`),

  /** Record the FINAL human decision. Critical unresolved findings gate it. */
  submitDecision: (
    inspectionId: string,
    body: DecisionRequest,
  ): Promise<InspectionDecision> =>
    request<InspectionDecision>(`/inspections/${inspectionId}/decision`, {
      method: 'POST',
      body,
    }),

  /** The CURRENT decision — 404 when none has been recorded yet. */
  getCurrentDecision: (inspectionId: string): Promise<InspectionDecision> =>
    request<InspectionDecision>(`/inspections/${inspectionId}/decision`),

  /** The full decision chain — previous decisions are never deleted. */
  getDecisionHistory: (inspectionId: string): Promise<DecisionHistory> =>
    request<DecisionHistory>(`/inspections/${inspectionId}/decision-history`),

  /** Review progress + the decision gate for one inspection. */
  getReviewStatus: (inspectionId: string): Promise<ReviewStatus> =>
    request<ReviewStatus>(`/inspections/${inspectionId}/review-status`),

  /**
   * The append-only audit trail for one inspection — the evidence timeline.
   * Real server timestamps only; the trail cannot be edited by anyone.
   */
  getInspectionAudit: (inspectionId: string): Promise<AuditEvent[]> =>
    request<AuditEvent[]>(`/inspections/${inspectionId}/audit`),

  // --- Evidence Planner + verification (UI-06) ----------------------------------
  // What evidence exists, what is missing, and which inspector action closes
  // the gap. Verification tasks are AUTHORISED HUMAN actions only — the
  // backend enforces roles, the task state machine and the anchor/duplicate
  // rules. A recorded measurement is EVIDENCE: this client never compares it
  // to the declared value, and never derives a compliance verdict from it.

  /** GET /inspections/:id/evidence-plan — per finding/declaration: existing
   *  evidence, open gaps, the verification that closes them. */
  getEvidencePlan: (inspectionId: string): Promise<EvidencePlan> =>
    request<EvidencePlan>(`/inspections/${inspectionId}/evidence-plan`),

  /** POST /inspections/:id/verifications — create ONE task (reason mandatory). */
  createVerification: (
    inspectionId: string,
    body: VerificationCreateRequest,
  ): Promise<VerificationTask> =>
    request<VerificationTask>(`/inspections/${inspectionId}/verifications`, {
      method: 'POST',
      body,
    }),

  /** GET /inspections/:id/verifications — tasks + append-only results. */
  listVerifications: (inspectionId: string): Promise<VerificationList> =>
    request<VerificationList>(`/inspections/${inspectionId}/verifications`),

  /** GET /verifications/:taskId — one task with its result history. */
  getVerification: (taskId: string): Promise<VerificationTask> =>
    request<VerificationTask>(`/verifications/${taskId}`),

  /** POST /verifications/:taskId/start — PENDING → IN_PROGRESS (409 otherwise). */
  startVerification: (taskId: string): Promise<VerificationTask> =>
    request<VerificationTask>(`/verifications/${taskId}/start`, { method: 'POST' }),

  /**
   * POST /verifications/:taskId/result — record ONE outcome (append-only).
   * MEASUREMENT tasks require measuredValue (> 0) and unit. The measured
   * value is stored SEPARATELY from the declared value; nothing evaluates
   * the difference — the inspector does.
   */
  recordVerificationResult: (
    taskId: string,
    body: VerificationResultRequest,
  ): Promise<VerificationTask> =>
    request<VerificationTask>(`/verifications/${taskId}/result`, {
      method: 'POST',
      body,
    }),

  /** POST /verifications/:taskId/cancel — reason mandatory. */
  cancelVerification: (
    taskId: string,
    body: { reason: string },
  ): Promise<VerificationTask> =>
    request<VerificationTask>(`/verifications/${taskId}/cancel`, {
      method: 'POST',
      body,
    }),

  // --- Physical verification + lot intelligence (UI-07) -----------------------
  // LOT → PACKAGES → SAMPLE → MEASUREMENTS → EVALUATION → LOT RESULT.
  // Every write is an AUTHORISED HUMAN action (backend-enforced RBAC); every
  // read carries observed statistics and honesty labels — this client never
  // derives a compliance verdict from any of them.

  /** GET /inspections/:id/measurements — the append-only measurement
   *  history: declared (never overwritten) beside measured, instrument
   *  metadata, the observed difference and the frozen evaluation. */
  getMeasurementHistory: (inspectionId: string): Promise<MeasurementHistory> =>
    request<MeasurementHistory>(`/inspections/${inspectionId}/measurements`),

  /** POST /inspections/:id/lots — create a lot + its package records. The
   *  declared quantity is stored verbatim and is immutable after creation. */
  createLot: (inspectionId: string, body: LotCreateRequest): Promise<LotDetail> =>
    request<LotDetail>(`/inspections/${inspectionId}/lots`, {
      method: 'POST',
      body,
    }),

  /** GET /inspections/:id/lots — lot summaries with progress. */
  listLots: (inspectionId: string): Promise<LotList> =>
    request<LotList>(`/inspections/${inspectionId}/lots`),

  /** GET /lots/:lotId — the full lot read model (packages, sampling runs,
   *  observed statistics, progress). Read-only for any authenticated role. */
  getLot: (lotId: string): Promise<LotDetail> =>
    request<LotDetail>(`/lots/${lotId}`),

  /**
   * POST /lots/:lotId/sample — draw ONE audited, reproducible sample.
   * Without a configured legal procedure the run is AI-recommended and the
   * backend requires confirmAiSample (422 otherwise). Never regenerated on
   * read; never silently replaced after a measurement.
   */
  generateLotSample: (lotId: string, body: SampleGenerateRequest): Promise<SamplingRun> =>
    request<SamplingRun>(`/lots/${lotId}/sample`, {
      method: 'POST',
      body,
    }),

  /**
   * POST /lots/:lotId/decision — the explicit, evidence-gated lot result.
   * The backend blocks the submission with "Insufficient evidence" while
   * sampled packages still lack measurements.
   */
  submitLotDecision: (lotId: string, body: LotDecisionRequest): Promise<LotDetail> =>
    request<LotDetail>(`/lots/${lotId}/decision`, {
      method: 'POST',
      body,
    }),

  // --- Reporting & evidence pack (UI-08) --------------------------------------
  // Report lifecycle: create → generate (frozen snapshot version) → finalize
  // (gated) → export (PDF/DOCX) → amend (new version, reason mandatory). All
  // writes are backend-authorized; the snapshot is the only export input so
  // later data changes can never rewrite an exported claim.

  /** POST /reports — create the one live report for an inspection. */
  createReport: (body: ReportCreateRequest): Promise<ReportDetail> =>
    request<ReportDetail>('/reports', { method: 'POST', body }),

  /** GET /reports — the Report Center list (real DB records only). */
  listReports: (params: { status?: string; inspectionId?: string; q?: string; page?: number; pageSize?: number } = {}): Promise<ReportList> =>
    request<ReportList>('/reports' + querySuffix(params)),

  /** GET /reports/kpis — real group-by counts (never fabricated). */
  reportKpis: (): Promise<ReportKpis> => request<ReportKpis>('/reports/kpis'),

  /** GET /reports/:id — full detail (snapshot + version history). */
  getReport: (reportId: string): Promise<ReportDetail> =>
    request<ReportDetail>(`/reports/${reportId}`),

  /** POST /reports/:id/generate — freeze a new snapshot version. */
  generateReport: (reportId: string, body: { note?: string } = {}): Promise<ReportDetail> =>
    request<ReportDetail>(`/reports/${reportId}/generate`, { method: 'POST', body }),

  /** POST /reports/:id/review — record the human review step. */
  reviewReport: (reportId: string, body: { note?: string } = {}): Promise<ReportDetail> =>
    request<ReportDetail>(`/reports/${reportId}/review`, { method: 'POST', body }),

  /** POST /reports/:id/finalize — the gated finalization. */
  finalizeReport: (reportId: string, body: { note?: string } = {}): Promise<ReportDetail> =>
    request<ReportDetail>(`/reports/${reportId}/finalize`, { method: 'POST', body }),

  /** POST /reports/:id/amend — new version; an explained reason is mandatory. */
  amendReport: (reportId: string, body: ReportAmendRequest): Promise<ReportDetail> =>
    request<ReportDetail>(`/reports/${reportId}/amend`, { method: 'POST', body }),

  /** GET /reports/:id/evidence-pack — the E-00N evidence bundle. */
  getEvidencePack: (reportId: string): Promise<ReportEvidencePack> =>
    request<ReportEvidencePack>(`/reports/${reportId}/evidence-pack`),

  /** GET /reports/:id/audit — the report's lifecycle events. */
  getReportAudit: (reportId: string): Promise<ReportAudit> =>
    request<ReportAudit>(`/reports/${reportId}/audit`),

  /**
   * GET /reports/:id/export/pdf|docx — REAL file download. Fetches the bytes
   * with the bearer token (a plain <a href> cannot authenticate), hands back
   * a blob URL the caller must revoke, and surfaces the backend's honest
   * error strings on failure. On export failure nothing changes — retrying
   * is always safe.
   */
  exportReport: async (
    reportId: string,
    format: 'pdf' | 'docx',
    signal?: AbortSignal,
  ): Promise<{ url: string; filename: string }> => {
    const response = await fetch(
      `${API_BASE_URL}/reports/${reportId}/export/${format}`,
      { headers: authHeaders(), signal },
    );
    if (!response.ok) throw await toClientError(response);
    const disposition = response.headers.get('content-disposition') ?? '';
    const match = /filename="?([^";]+)"?/.exec(disposition);
    const blob = await response.blob();
    return {
      url: URL.createObjectURL(blob),
      filename: match?.[1] ?? `metrasight-report.${format}`,
    };
  },

  // --- Citizen Mode (UI-02) — anonymous by design --------------------------
  // No bearer token is required; the auth headers are simply absent when no
  // inspector session exists, which is exactly the anonymous citizen case.
  /** POST /citizen/scans — real quality gate + OCR + extraction, no login. */
  citizenScan: (file: File | Blob, opts: XhrOptions = {}): Promise<CitizenScanResult> => {
    const form = new FormData();
    const name = file instanceof File ? file.name : 'capture.jpg';
    form.append('file', file, name);
    form.append('captureSource', 'CAMERA');
    return xhrUpload<CitizenScanResult>('/citizen/scans', form, opts);
  },
  /** GET /citizen/scans/:id — re-read a scan by its unguessable UUID. */
  citizenGetScan: (scanId: string): Promise<CitizenScanResult> =>
    request<CitizenScanResult>(`/citizen/scans/${scanId}`),
  /** POST /citizen/reports — submit a suspected issue for official review. */
  citizenSubmitReport: (body: CitizenReportRequest): Promise<CitizenReportResult> =>
    request<CitizenReportResult>('/citizen/reports', { method: 'POST', body }),
  /** GET /citizen/reports/:id — read back a submitted complaint + timeline. */
  citizenGetReport: (reportId: string): Promise<CitizenReportDetail> =>
    request<CitizenReportDetail>(`/citizen/reports/${reportId}`),
  /** POST /citizen/reports/:id/respond — answer a pending information request. */
  citizenRespond: (
    reportId: string,
    input: { message: string; location?: string; file?: File | Blob },
    opts: XhrOptions = {},
  ): Promise<CitizenReportDetail> => {
    const form = new FormData();
    form.append('message', input.message);
    if (input.location) form.append('location', input.location);
    if (input.file) {
      const name = input.file instanceof File ? input.file.name : 'response.jpg';
      form.append('file', input.file, name);
    }
    return xhrUpload<CitizenReportDetail>(`/citizen/reports/${reportId}/respond`, form, opts);
  },

  // --- Department Command Center (UI-04) — aggregated, read-only -----------
  /** GET /department/dashboard?days=7|30|90 — server-side aggregation only. */
  departmentDashboard: (days: 7 | 30 | 90 = 30): Promise<DepartmentDashboard> =>
    request<DepartmentDashboard>(`/department/dashboard${querySuffix({ days })}`),

  // --- Complaint management (UI-03) — authenticated department surface -----
  /** GET /citizen/complaints — intake queue. Filtering happens in SQL. */
  complaintList: (params: ComplaintListParams = {}): Promise<ComplaintSummary[]> =>
    request<ComplaintSummary[]>(`/citizen/complaints${querySuffix({ ...params })}`),
  /** GET /citizen/complaints/stats — real COUNT(*) KPIs from the database. */
  complaintStats: (): Promise<ComplaintStats> =>
    request<ComplaintStats>('/citizen/complaints/stats'),
  /** GET /citizen/complaints/inspectors — users a complaint may be assigned to. */
  complaintInspectors: (): Promise<AssignableInspector[]> =>
    request<AssignableInspector[]>('/citizen/complaints/inspectors'),
  /** GET /citizen/complaints/:id — full complaint review detail. */
  complaintGet: (complaintId: string): Promise<ComplaintDetail> =>
    request<ComplaintDetail>(`/citizen/complaints/${complaintId}`),
  /** POST /citizen/complaints/:id/transition — one state-machine action. */
  complaintTransition: (
    complaintId: string,
    body: ComplaintTransitionRequest,
  ): Promise<ComplaintDetail> =>
    request<ComplaintDetail>(`/citizen/complaints/${complaintId}/transition`, {
      method: 'POST',
      body,
    }),

  // --- UI-09: global search / history / product repository / analytics --------
  // Read-only intelligence surfaces over EXISTING entities. All filtering and
  // aggregation happens server-side; results never carry citizen reporter PII,
  // internal notes or storage keys. Rates arrive null when there is no valid
  // denominator — the UI shows N/A, never a fabricated 0%.

  /** GET /search — grouped, RBAC-aware, server-side global search. */
  search: (params: { q: string; limit?: number }): Promise<SearchResults> =>
    request<SearchResults>('/search' + querySuffix(params)),

  /** GET /history/inspections — one server-side page + real filtered-set KPIs. */
  inspectionHistory: (params: {
    q?: string;
    status?: string;
    result?: string;
    source?: string;
    inspectorId?: string;
    productId?: string;
    dateFrom?: string;
    dateTo?: string;
    page?: number;
    pageSize?: number;
  }): Promise<HistoryPage> =>
    request<HistoryPage>('/history/inspections' + querySuffix(params)),

  /** GET /history/inspections/:id/timeline — only events actually recorded. */
  inspectionTimeline: (inspectionId: string): Promise<InspectionTimeline> =>
    request<InspectionTimeline>(`/history/inspections/${inspectionId}/timeline`),

  /** GET /products — searchable product directory (real aggregate counts). */
  listProducts: (params: { q?: string; page?: number; pageSize?: number } = {}): Promise<
    Paginated<ProductSummary>
  > => request<Paginated<ProductSummary>>('/products' + querySuffix(params)),

  /** GET /products/:id — the historical record: overview, inspections,
   *  recurring findings, evidence gallery. Never a current-compliance claim. */
  getProduct: (productId: string): Promise<ProductDetail> =>
    request<ProductDetail>(`/products/${productId}`),

  /** GET /analytics/operational — server-side aggregation over real DB rows. */
  operationalAnalytics: (params: {
    granularity?: 'day' | 'week' | 'month';
    dateFrom?: string;
    dateTo?: string;
  }): Promise<OperationalAnalytics> =>
    request<OperationalAnalytics>('/analytics/operational' + querySuffix(params)),
};

/** Query string for GET params (empty values dropped), '' when none. */
function querySuffix(params: Record<string, string | number | boolean | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== '') search.set(key, String(value));
  }
  const query = search.toString();
  return query ? `?${query}` : '';
}
