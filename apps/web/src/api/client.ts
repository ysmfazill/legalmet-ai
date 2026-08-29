/**
 * Typed API client for the LEGALMET AI backend.
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
  AuthTokenResponse,
  BatchUploadResponse,
  CaptureSource,
  CreateInspectionRequest,
  CreatePackageRequest,
  EngineFinding,
  EngineInfo,
  ExtractedField,
  FieldCandidates,
  HealthResponse,
  ImageRegion,
  ImageType,
  Inspection,
  InspectionComplianceStatus,
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
  User,
  VersionSelection,
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
