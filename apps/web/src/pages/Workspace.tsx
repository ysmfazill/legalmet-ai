import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';

import { FIELD_TYPE_LABELS, INSPECTION_STATUS_META } from '@legalmet/config';
import type { Tone } from '@legalmet/config';
import type { Inspection, PackageImage, SourceComplaint } from '@legalmet/types';

import { api, ApiClientError } from '../api/client';
import { useApp } from '../app/AppContext';
import {
  Badge,
  DemoBadge,
  ImageProcessingBadge,
  ImageQualityGradeBadge,
  InspectionStatusBadge,
} from '../components/Badge';
import { BarList } from '../components/charts';
import { Card, CardBody, CardHead, SectionCard } from '../components/Card';
import { DeclarationField } from '../components/DeclarationField';
import { EvidenceDrawer } from '../components/EvidenceDrawer';
import { EvidenceViewer } from '../components/EvidenceViewer';
import { FindingCard } from '../components/FindingCard';
import { Icon } from '../components/Icon';
import { PageHeader } from '../components/PageHeader';
import { AsyncView, EmptyState, ErrorState } from '../components/states';
import { useAsync } from '../data/useAsync';
import {
  COMPLAINT_RISK_META,
  COMPLAINT_STATUS_META as COMPLAINT_STATUS_LABELS,
} from '../lib/complaintStatus';
import {
  ComplianceControlCard,
  ComplianceFindingsCard,
} from '../compliance/CompliancePanel';
import { FindingExplanationDrawer } from '../compliance/FindingExplanationDrawer';
import { useCompliance } from '../compliance/useCompliance';
import { FinalDecisionCard } from '../hitl/FinalDecisionCard';
import { useHitl } from '../hitl/useHitl';
import { EvidenceTraceCard } from '../evidence/EvidenceTraceCard';
import { QualityReadout } from '../intake/QualityReadout';
import { useObjectUrl } from '../intake/useObjectUrl';
import { FieldEvidenceDrawer } from '../perception/FieldEvidenceDrawer';
import {
  PerceptionControlCard,
  PerceptionDeclarationsCard,
  PerceptionRunHistoryCard,
} from '../perception/PerceptionPanel';
import { PerceptionViewer } from '../perception/PerceptionViewer';
import { usePerception } from '../perception/usePerception';
import { EvidencePlanner } from '../evidence/EvidencePlanner';
import type { EvidencePlanRow } from '../evidence/EvidencePlanner';
import { EvidencePlannerLive } from '../evidence/EvidencePlannerLive';
import { EvidenceTimelineCard } from '../evidence/EvidenceTimelineCard';
import { PhysicalVerificationCard } from '../evidence/PhysicalVerificationCard';
import { LotIntelligenceCard } from '../lot/LotIntelligenceCard';
import { formatBytes, formatDateTime, humanizeEnum } from '../lib/format';
import { toneColor, toneSoft } from '../lib/tone';
import { mockApi } from '../mock/adapter';
import { countsFrom, inspectorName } from '../mock/fixtures';
import type { FindingView, InspectionDetail } from '../mock/types';

const WORKED_DEMOS = [
  { id: 'ins-10482', label: 'INS-10482 · Namkeen' },
  { id: 'ins-10483', label: 'INS-10483 · Drinking Water' },
  { id: 'ins-10485', label: 'INS-10485 · Sunflower Oil' },
];

function qualityTone(score: number): Tone {
  return score >= 0.9 ? 'positive' : score >= 0.75 ? 'warning' : 'critical';
}

/**
 * One inspection id resolves to one of three things:
 *   - a fully-worked DEMO inspection (authored evidence + findings), or
 *   - a REAL intake inspection (uploaded image + provenance, NO analysis), or
 *   - nothing we can render.
 * Demo data is served by the mock adapter and always wins; real inspections are
 * fetched from the backend only when authenticated.
 */
type WorkspaceResult =
  | { kind: 'demo'; detail: InspectionDetail }
  | { kind: 'real'; inspection: Inspection }
  | { kind: 'none' };

export function WorkspacePage() {
  const { id = '' } = useParams();
  const { isLive } = useApp();

  const query = useAsync<WorkspaceResult>(async () => {
    const demo = await mockApi.getInspectionDetail(id);
    if (demo) return { kind: 'demo', detail: demo };
    if (isLive) {
      try {
        const inspection = await api.getInspection(id);
        return { kind: 'real', inspection };
      } catch {
        return { kind: 'none' };
      }
    }
    return { kind: 'none' };
  }, [id, isLive]);

  return (
    <div className="page">
      <AsyncView query={query} loadingLabel="Loading inspection workspace…">
        {(result) =>
          result.kind === 'demo' ? (
            <Workspace detail={result.detail} />
          ) : result.kind === 'real' ? (
            <RealInspectionWorkspace inspection={result.inspection} />
          ) : (
            <NoWorkspace />
          )
        }
      </AsyncView>
    </div>
  );
}

function NoWorkspace() {
  const navigate = useNavigate();
  return (
    <>
      <PageHeader eyebrow="Workspace" title="Inspection Workspace" />
      <Card>
        <CardBody>
          <EmptyState
            icon="image"
            title="No worked evidence for this inspection"
            message="Fully-linked evidence (regions, declarations, findings and rules) is authored for the demonstration inspections below."
            action={
              <div className="row row--wrap" style={{ gap: 'var(--space-2)', justifyContent: 'center' }}>
                {WORKED_DEMOS.map((d) => (
                  <button key={d.id} type="button" className="btn btn--subtle btn--sm" onClick={() => navigate(`/inspections/${d.id}`)}>
                    {d.label}
                  </button>
                ))}
              </div>
            }
          />
        </CardBody>
      </Card>
    </>
  );
}

/* -------------------------------------------------------------------------- */
/* REAL inspection workspace — actual uploaded image + REAL perception        */
/* (Prompt 4).                                                                */
/*                                                                            */
/* Shows what the system PERCEIVED: real OCR text, symbol regions and         */
/* extracted declaration candidates with full evidence links. It never shows  */
/* a compliance verdict — the strongest statement available is                */
/* "awaiting regulatory evaluation".                                          */
/* -------------------------------------------------------------------------- */
function RealInspectionWorkspace({ inspection: initial }: { inspection: Inspection }) {
  // UI-05: assignment updates the inspector in place — keep a local copy so
  // the header, the assign card and the source brief stay consistent.
  const [inspection, setInspection] = useState<Inspection>(initial);
  const images = inspection.packages?.flatMap((p) => p.images ?? []) ?? [];
  const statusMeta = INSPECTION_STATUS_META[inspection.status];
  const isReady = inspection.status === 'READY_FOR_ANALYSIS';
  // Deep link from Evidence Explorer: ?field=<extractedFieldId> opens the
  // evidence drawer for that field and highlights its region on the image.
  const [searchParams] = useSearchParams();
  const deepLinkFieldId = searchParams.get('field');

  const perception = usePerception(inspection.id);
  const [selectedFieldId, setSelectedFieldId] = useState<string | null>(null);
  const [openFindingId, setOpenFindingId] = useState<string | null>(null);

  // Once perception data loads, resolve the deep-linked field exactly once.
  const appliedDeepLink = useRef<string | null>(null);
  useEffect(() => {
    if (!deepLinkFieldId || appliedDeepLink.current === deepLinkFieldId) return;
    if (perception.loading) return;
    if (perception.fields.some((f) => f.id === deepLinkFieldId)) {
      appliedDeepLink.current = deepLinkFieldId;
      setSelectedFieldId(deepLinkFieldId);
    }
  }, [deepLinkFieldId, perception.loading, perception.fields]);

  const hasRuns = perception.analysis?.hasRuns ?? false;

  const compliance = useCompliance(inspection.id, hasRuns);
  const hitl = useHitl(inspection.id, hasRuns);
  // UI-07 — bumped after every verification write so the physical-verification
  // history and the lot read models reload alongside the planner.
  const [verificationVersion, setVerificationVersion] = useState(0);
  const openFinding =
    compliance.findings.find((f) => f.id === openFindingId) ?? null;

  const selectedField =
    perception.fields.find((f) => f.id === selectedFieldId) ?? null;
  const selectedRegionId = selectedField?.imageRegionId ?? null;
  const selectedOcrLine = selectedField?.sourceOcrResultId
    ? perception.ocr.find((o) => o.id === selectedField.sourceOcrResultId) ?? null
    : null;
  const selectedRegion = selectedField?.imageRegionId
    ? perception.regions.find((r) => r.id === selectedField.imageRegionId) ?? null
    : null;
  const selectedRun = selectedField?.processingRunId
    ? perception.runs.find((r) => r.id === selectedField.processingRunId) ?? null
    : null;

  return (
    <>
      <PageHeader
        eyebrow={inspection.referenceNo}
        title={inspection.product?.name ?? 'Packaged commodity'}
        lead={`${inspection.product?.category ?? '—'} · Real package perception`}
        actions={
          <>
            <span className="tag tag--live" title="This inspection was created through real intake and lives in the backend database">
              LIVE INSPECTION
            </span>
            <InspectionStatusBadge status={inspection.status} />
            <Link to="/inspections/new" className="btn btn--subtle btn--sm">
              <Icon name="camera" size={15} />
              New intake
            </Link>
            <Link to="/inspections" className="btn btn--ghost btn--sm">
              <Icon name="chevronLeft" size={15} />
              All inspections
            </Link>
          </>
        }
      />

      <div className="demo-note demo-note--block">
        <Icon name="info" size={15} />
        <span>
          <strong>{statusMeta?.label ?? humanizeEnum(inspection.status)}.</strong>{' '}
          {isReady
            ? 'Images are validated and stored. '
            : 'Images are validated and stored with a deterministic usability grade. '}
          Perception results below come from <strong>real OCR and symbol detection</strong> over the
          uploaded pixels — they describe what the system <em>saw</em>, not whether the package is
          legally compliant.
        </span>
      </div>

      {perception.error && (
        <div className="demo-note demo-note--block" style={{ borderColor: 'var(--tone-critical)' }}>
          <Icon name="alert" size={15} />
          <span>Could not load perception data: {perception.error}</span>
        </div>
      )}

      {/* UI-05 — the inspection brief: why this targeted inspection exists,
          with the immutable citizen evidence it originated from. */}
      {inspection.sourceComplaint && <SourceComplaintCard inspection={inspection} />}

      {/* UI-05 — department assignment (SUPERVISOR/ADMIN; backend-enforced). */}
      <AssignInspectorCard inspection={inspection} onAssigned={setInspection} />

      {images.length === 0 ? (
        <Card>
          <CardBody>
            <EmptyState
              icon="image"
              title="No images on this inspection yet"
              message="Upload or capture label images from the New inspection page to populate this workspace."
            />
          </CardBody>
        </Card>
      ) : (
        <div className="split">
          {/* LEFT — the real package images with perception overlays */}
          <div className="stack">
            {images.map((image) => (
              <div className="stack" key={image.id}>
                <PerceptionViewer
                  image={image}
                  ocrLines={perception.ocr.filter((o) => o.imageId === image.id)}
                  symbolRegions={perception.regions.filter(
                    (r) =>
                      r.imageId === image.id &&
                      (r.regionType === 'QR_CODE' || r.regionType === 'BARCODE'),
                  )}
                  selectedRegionId={selectedRegionId}
                />
                <RealImageMeta image={image} />
              </div>
            ))}
          </div>

          {/* RIGHT — the perception + compliance panels */}
          <div className="stack">
            <PerceptionControlCard
              analysis={perception.analysis}
              starting={perception.starting}
              hasImages={images.length > 0}
              runs={perception.runs}
              hasEvaluation={Boolean(compliance.evaluation)}
              onStart={() => void perception.start()}
            />

            {hasRuns && (
              <div className="demo-note demo-note--block">
                <Icon name="scale" size={15} />
                <span>
                  <strong>Perception ≠ compliance.</strong> The declarations card lists what the
                  system detected. The deterministic engine below checks each requirement in force
                  against that evidence — every conclusion is traceable, and the inspector makes the
                  final decision.
                </span>
              </div>
            )}

            <PerceptionDeclarationsCard
              fields={perception.fields}
              selectedFieldId={selectedFieldId}
              onSelect={(field) =>
                setSelectedFieldId((cur) => (cur === field.id ? null : field.id))
              }
            />

            {hasRuns && (
              <>
                <ComplianceControlCard
                  evaluation={compliance.evaluation}
                  evaluating={compliance.evaluating}
                  error={compliance.error}
                  hasEvidence={perception.fields.length > 0}
                  onEvaluate={() => void compliance.evaluate()}
                />
                {compliance.findings.length > 0 && (
                  <ComplianceFindingsCard
                    findings={compliance.findings}
                    selectedFindingId={openFindingId}
                    onOpen={(finding) =>
                      setOpenFindingId((cur) => (cur === finding.id ? null : finding.id))
                    }
                  />
                )}
                <EvidenceTraceCard
                  inspectionId={inspection.id}
                  evaluationId={compliance.evaluation?.id ?? null}
                  hasEvaluation={Boolean(compliance.evaluation)}
                />
                {/* UI-06 — the LIVE evidence planner: what exists, what is
                    missing, and which inspector action closes the gap. The
                    plan is computed by the backend from real rows only. */}
                <EvidencePlannerLive
                  inspectionId={inspection.id}
                  enabled={hasRuns}
                  onChanged={() => {
                    void hitl.reload();
                    setVerificationVersion((v) => v + 1);
                  }}
                />
                {/* UI-07 §31 — the verification layering:
                    FINDINGS → EVIDENCE PLANNER → PHYSICAL VERIFICATION →
                    LOT INTELLIGENCE → FINAL REVIEW. */}
                <PhysicalVerificationCard
                  inspectionId={inspection.id}
                  enabled={hasRuns}
                  refreshKey={verificationVersion}
                />
                <LotIntelligenceCard
                  inspectionId={inspection.id}
                  enabled={hasRuns}
                  refreshKey={verificationVersion}
                />
                <FinalDecisionCard
                  hitl={hitl}
                  hasFindings={compliance.findings.length > 0}
                />
              </>
            )}

            {/* UI-06 — the append-only evidence timeline. Real server
                timestamps only; visible from inspection creation. */}
            <EvidenceTimelineCard inspectionId={inspection.id} />

            <PerceptionRunHistoryCard
              runs={perception.runs}
              onReanalyze={(imageId) => void perception.reanalyze(imageId)}
              reanalyzing={perception.starting}
            />
          </div>
        </div>
      )}

      {selectedField && (
        <FieldEvidenceDrawer
          field={selectedField}
          inspectionId={inspection.id}
          ocrLine={selectedOcrLine}
          region={selectedRegion}
          run={selectedRun}
          onClose={() => setSelectedFieldId(null)}
        />
      )}

      {openFinding && (
        <FindingExplanationDrawer
          finding={openFinding}
          onClose={() => setOpenFindingId(null)}
          hitl={hitl}
          onReviewed={() => void compliance.reload()}
        />
      )}
    </>
  );
}

/* -------------------------------------------------------------------------- */
/* UI-05 — SOURCE COMPLAINT BRIEF                                              */
/* The immutable citizen evidence behind a targeted inspection. Everything in  */
/* this card is SOURCE MATERIAL submitted by the citizen: a suspected issue to */
/* verify, never an official finding. The inspector's own images stay in the  */
/* normal workflow below, clearly separate from this evidence.                */
/* -------------------------------------------------------------------------- */

/** evidence.imageUrl is an app-relative `/api/v1/storage/{key}` URL; the
 * bearer-authed fetcher wants the bare storage key. */
function sourceStorageKeyFromUrl(url: string): string {
  return url.replace(/^\/api\/v1\/storage\//, '');
}

function SourceEvidenceImage({ url, small }: { url: string; small?: boolean }) {
  const state = useObjectUrl(sourceStorageKeyFromUrl(url));
  if (state.status === 'loading') return <p className="cell-muted">Loading photo…</p>;
  if (state.status === 'error') return <p className="cell-muted">{state.message}</p>;
  return (
    <a
      href={state.url}
      target="_blank"
      rel="noreferrer"
      className={`complaint-photo${small ? ' complaint-photo--sm' : ''}`}
    >
      <img src={state.url} alt="Source evidence photo submitted by the citizen" />
    </a>
  );
}

function SourceComplaintCard({ inspection }: { inspection: Inspection }) {
  const query = useAsync(() => api.getInspectionSourceComplaint(inspection.id), [inspection.id]);
  const ref = inspection.sourceComplaint!;

  return (
    <Card>
      <CardHead
        eyebrow="Inspection brief"
        title={`Source complaint ${ref.reference}`}
        subtitle="This inspection originated from a citizen complaint. The evidence below is what the citizen submitted — source material to verify, not an official finding."
        actions={
          <Link to={`/complaints/${ref.id}`} className="btn btn--subtle btn--sm">
            <Icon name="complaints" size={14} />
            Open complaint
          </Link>
        }
      />
      <CardBody>
        {query.status === 'error' ? (
          <ErrorState
            title="Source complaint unavailable"
            error={query.error}
            onRetry={query.reload}
          />
        ) : query.status === 'loading' ? (
          <p className="cell-muted">Loading the source complaint…</p>
        ) : (
          <SourceComplaintBrief brief={query.data} />
        )}
      </CardBody>
    </Card>
  );
}

function SourceComplaintBrief({ brief }: { brief: SourceComplaint }) {
  const followUps = brief.evidence?.citizenFollowUps ?? [];
  const detectedFields = brief.evidence?.detectedFields ?? [];
  const priority = brief.officialPriority ?? brief.screeningRisk;
  const statusMeta = COMPLAINT_STATUS_LABELS[brief.status];

  return (
    <div className="grid grid--2">
      {/* Left — the brief itself */}
      <div>
        <dl className="kv">
          <dt>Complaint</dt>
          <dd className="cell-mono">{brief.reference}</dd>
          <dt>Reported concern</dt>
          <dd>{brief.issue}</dd>
          <dt>Product</dt>
          <dd>{brief.product}</dd>
          {brief.shop && (
            <>
              <dt>Shop</dt>
              <dd>{brief.shop}</dd>
            </>
          )}
          <dt>Location</dt>
          <dd>{brief.location ?? '—'}</dd>
          <dt>Submitted</dt>
          <dd>{formatDateTime(brief.createdAt)}</dd>
          <dt>Priority</dt>
          <dd>
            {priority ? (
              <Badge tone={COMPLAINT_RISK_META[priority]?.tone} outline>
                {priority} ({brief.officialPriority ? 'official decision' : 'system screening'})
              </Badge>
            ) : (
              'Not assessed'
            )}
          </dd>
          <dt>Department action</dt>
          <dd>
            {statusMeta ? (
              <Badge tone={statusMeta.tone} dot>{statusMeta.label}</Badge>
            ) : (
              brief.status
            )}
          </dd>
          {brief.assignedInspectorName && (
            <>
              <dt>Assigned inspector</dt>
              <dd>{brief.assignedInspectorName}</dd>
            </>
          )}
        </dl>
        {brief.description && (
          <div className="complaint-followup" style={{ marginTop: 'var(--space-3)' }}>
            <div className="cell-muted" style={{ fontSize: 'var(--fs-xs)' }}>
              Citizen&rsquo;s description
            </div>
            <p style={{ margin: 0, whiteSpace: 'pre-wrap' }}>{brief.description}</p>
          </div>
        )}
      </div>

      {/* Right — the immutable source evidence */}
      <div>
        <h3 className="cell-strong" style={{ margin: '0 0 var(--space-2)' }}>
          Source complaint evidence
        </h3>
        <p className="cell-muted" style={{ fontSize: 'var(--fs-sm)', margin: 0 }}>
          Citizen-submitted at report time and never modified. These are readings and photos from
          the citizen — <strong>not official findings</strong>. Anything the inspector verifies is
          added as new inspection evidence in the workflow below.
        </p>
        {brief.evidence?.imageUrl && (
          <div style={{ marginTop: 'var(--space-3)' }}>
            <SourceEvidenceImage url={brief.evidence.imageUrl} />
          </div>
        )}
        {detectedFields.length > 0 && (
          <>
            <h4 className="cell-strong" style={{ margin: 'var(--space-4) 0 var(--space-2)', fontSize: 'var(--fs-sm)' }}>
              Declarations read from the citizen&rsquo;s photo
            </h4>
            <ul className="complaint-fields">
              {detectedFields.map((f, i) => (
                <li key={i} className="complaint-fields__row">
                  <span className="complaint-fields__label">{f.label}</span>
                  <span className={f.status === 'NOT_EXTRACTED' ? 'cell-muted' : 'cell-strong'}>
                    {f.status === 'NOT_EXTRACTED' ? 'not read' : (f.normalizedValue ?? f.rawText ?? '—')}
                  </span>
                </li>
              ))}
            </ul>
          </>
        )}
        {followUps.length > 0 && (
          <>
            <h4 className="cell-strong" style={{ margin: 'var(--space-4) 0 var(--space-2)', fontSize: 'var(--fs-sm)' }}>
              Citizen responses
            </h4>
            <ul className="stack stack--sm">
              {followUps.map((f, i) => (
                <li key={i} className="complaint-followup">
                  <div className="cell-muted" style={{ fontSize: 'var(--fs-xs)' }}>
                    {formatDateTime(f.at)}
                    {f.location ? ` · ${f.location}` : ''}
                  </div>
                  <p style={{ margin: 0, whiteSpace: 'pre-wrap' }}>{f.message}</p>
                  {f.imageUrl && <SourceEvidenceImage url={f.imageUrl} small />}
                </li>
              ))}
            </ul>
          </>
        )}
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* UI-05 — ASSIGN INSPECTOR (department act)                                   */
/* SUPERVISOR/ADMIN only — the backend enforces the same rule. Moving away     */
/* from a formally assigned inspector requires an explicit reassignment        */
/* confirmation; finalized inspections cannot be assigned at all.              */
/* -------------------------------------------------------------------------- */

const ASSIGN_ROLES = ['SUPERVISOR', 'ADMIN'];

function AssignInspectorCard({
  inspection,
  onAssigned,
}: {
  inspection: Inspection;
  onAssigned: (inspection: Inspection) => void;
}) {
  const { user } = useApp();
  const canAssign = ASSIGN_ROLES.includes(user.role);
  const finalized = inspection.status === 'COMPLETED' || inspection.status === 'ARCHIVED';

  const inspectors = useAsync(() => (canAssign && !finalized ? api.complaintInspectors() : Promise.resolve([])), [
    canAssign,
    finalized,
  ]);
  const [inspectorId, setInspectorId] = useState('');
  const [note, setNote] = useState('');
  const [confirmReassign, setConfirmReassign] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  if (!canAssign) return null;

  async function submit() {
    if (!inspectorId) {
      setError('Choose an inspector to assign.');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const updated = await api.assignInspection(inspection.id, {
        inspectorId,
        note: note.trim() || undefined,
        reassign: confirmReassign || undefined,
      });
      onAssigned(updated);
      setNotice(
        `Inspector assigned — ${updated.inspectorName ?? 'inspector'}. The assignment is audited and the source complaint (if any) is kept in sync.`,
      );
      setInspectorId('');
      setNote('');
      setConfirmReassign(false);
    } catch (err) {
      setError(
        err instanceof ApiClientError
          ? err.message
          : 'The assignment could not be applied. Check your connection and try again.',
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHead
        eyebrow="Department action"
        title="Assign inspector"
        subtitle={
          finalized
            ? 'This inspection is finalized — no further assignment is possible.'
            : 'Assignment is a department act (supervisor/admin). It is audited and keeps the source complaint in sync.'
        }
      />
      <CardBody>
        <dl className="kv">
          <dt>Current inspector</dt>
          <dd>{inspection.inspectorName ?? 'Not formally assigned'}</dd>
        </dl>

        {finalized ? (
          <p className="cell-muted" style={{ margin: 0 }}>
            The inspection is {humanizeEnum(inspection.status).toLowerCase()} — the inspector record
            is frozen with the rest of the evidence chain.
          </p>
        ) : (
          <div className="stack" style={{ marginTop: 'var(--space-3)' }}>
            {notice && (
              <div className="demo-note demo-note--block" role="status">
                <Icon name="check" size={15} />
                <span>{notice}</span>
              </div>
            )}
            {error && (
              <div className="demo-note demo-note--block demo-note--error" role="alert">
                <Icon name="alert" size={15} />
                <span>{error}</span>
              </div>
            )}
            <div className="field">
              <label className="field__label" htmlFor="assign-insp-select">
                Inspector
              </label>
              <select
                id="assign-insp-select"
                className="input"
                value={inspectorId}
                onChange={(e) => setInspectorId(e.target.value)}
                disabled={busy}
              >
                <option value="">Choose an inspector…</option>
                {(inspectors.data ?? []).map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.fullName} ({u.role.toLowerCase()})
                  </option>
                ))}
              </select>
            </div>
            <div className="field">
              <label className="field__label" htmlFor="assign-insp-note">
                Department note (optional, audited)
              </label>
              <textarea
                id="assign-insp-note"
                className="input"
                rows={2}
                maxLength={2000}
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder="e.g. Verify the MRP marking in person at the reported shop"
                disabled={busy}
              />
            </div>
            {inspection.inspectorName && (
              <label
                className="row"
                style={{ gap: 6, fontSize: 'var(--fs-sm)', cursor: 'pointer' }}
                title="Moving the inspection away from the currently assigned inspector"
              >
                <input
                  type="checkbox"
                  checked={confirmReassign}
                  onChange={(e) => setConfirmReassign(e.target.checked)}
                  disabled={busy}
                />
                Confirm reassignment — replace {inspection.inspectorName}
              </label>
            )}
            <div>
              <button
                type="button"
                className="btn btn--primary"
                onClick={() => void submit()}
                disabled={busy}
              >
                {busy ? <span className="spinner" aria-hidden /> : <Icon name="user" size={15} />}
                Assign inspector
              </button>
            </div>
          </div>
        )}
      </CardBody>
    </Card>
  );
}

/** Provenance + usability metadata for one real stored image. */
function RealImageMeta({ image }: { image: PackageImage }) {
  const resolution =
    image.width && image.height ? `${image.width} × ${image.height}` : 'Pending';
  const score =
    image.qualityScore != null ? `${Math.round(image.qualityScore * 100)}/100` : '—';
  const shortChecksum = image.checksum ? `${image.checksum.slice(0, 12)}…` : '—';

  return (
    <>
      <SectionCard
        eyebrow="Provenance"
        title={image.originalFilename}
        subtitle="Real stored image — metadata and usability only."
      >
        <div className="row row--wrap" style={{ gap: 'var(--space-2)', marginBottom: 'var(--space-3)' }}>
          <span className="tag">{image.captureSource}</span>
          <span className="tag">{image.imageType}</span>
          <ImageProcessingBadge status={image.processingStatus} />
          {image.qualityGrade && <ImageQualityGradeBadge grade={image.qualityGrade} />}
        </div>
        <dl className="meta-grid">
          <div>
            <dt>Image ID</dt>
            <dd title={image.id}>{image.id.slice(0, 8)}…</dd>
          </div>
          <div>
            <dt>Source</dt>
            <dd>{image.captureSource}</dd>
          </div>
          <div>
            <dt>Resolution</dt>
            <dd>{resolution}</dd>
          </div>
          <div>
            <dt>File size</dt>
            <dd>{formatBytes(image.fileSize)}</dd>
          </div>
          <div>
            <dt>Usability score</dt>
            <dd>{score}</dd>
          </div>
          <div>
            <dt>Processing</dt>
            <dd>{humanizeEnum(image.processingStatus)}</dd>
          </div>
          <div>
            <dt>Uploaded</dt>
            <dd>{formatDateTime(image.createdAt)}</dd>
          </div>
          <div>
            <dt>Checksum (SHA-256)</dt>
            <dd title={image.checksum ?? undefined}>{shortChecksum}</dd>
          </div>
        </dl>
      </SectionCard>

      <Card>
        <CardHead
          eyebrow="Perception"
          title="Image usability"
          subtitle="Deterministic legibility signal — not compliance, not AI confidence"
        />
        <CardBody>
          <QualityReadout image={image} />
        </CardBody>
      </Card>
    </>
  );
}

function Workspace({ detail }: { detail: InspectionDetail }) {
  const { inspection, imageRegions, declarations, findings, quality, qualityScore, complianceScore } = detail;
  const [selectedRegionId, setSelectedRegionId] = useState<string | null>(null);
  const [openFinding, setOpenFinding] = useState<FindingView | null>(null);
  const [reviewedIds, setReviewedIds] = useState<Set<string>>(new Set());

  const counts = countsFrom(findings);

  // Demo mirror of the live evidence plan: declared values are read from the
  // label; measured values stay honestly NOT VERIFIED until an instrument
  // integration exists. Net quantity always needs a physical measurement.
  const evidencePlanRows: EvidencePlanRow[] = declarations.map((d) => ({
    declaration: FIELD_TYPE_LABELS[d.field] ?? d.field,
    declaredValue: d.value,
    measuredValue: null,
    confidence: d.confidence,
    gaps: d.field === 'NET_QUANTITY' ? (['PHYSICAL_MEASUREMENT'] as const) : [],
  }));

  const breakdown: { label: string; value: number; tone: Tone }[] = [
    { label: 'Compliant', value: counts.compliant, tone: 'positive' },
    { label: 'Review required', value: counts.reviewRequired, tone: 'warning' },
    { label: 'Potential violation', value: counts.potentialViolation, tone: 'critical' },
    { label: 'Not applicable', value: counts.notApplicable, tone: 'neutral' },
  ];

  const openFindingCard = (f: FindingView) => {
    setOpenFinding(f);
    if (f.regionId) setSelectedRegionId(f.regionId);
  };

  return (
    <>
      <PageHeader
        eyebrow={inspection.referenceNo}
        title={inspection.product?.name ?? 'Packaged commodity'}
        lead={`${inspection.product?.category ?? '—'} · Inspector ${inspectorName(inspection.inspectorId)}`}
        actions={
          <>
            <DemoBadge />
            <InspectionStatusBadge status={inspection.status} />
            <Link to="/reports" className="btn btn--subtle btn--sm">
              <Icon name="reports" size={15} />
              Report
            </Link>
            <Link to="/inspections" className="btn btn--ghost btn--sm">
              <Icon name="chevronLeft" size={15} />
              All inspections
            </Link>
          </>
        }
      />

      <div className="split">
        {/* LEFT — the physical package, scanned */}
        <div className="stack">
          <EvidenceViewer
            packageLabel={inspection.product?.name ?? 'Package'}
            regions={imageRegions}
            declarations={declarations}
            selectedRegionId={selectedRegionId}
            onSelectRegion={(rid) => setSelectedRegionId((cur) => (cur === rid ? null : rid))}
          />
          <Card>
            <CardHead
              eyebrow="Perception"
              title="Image quality"
              subtitle="Why the system trusts (or doubts) this scan"
              actions={<span className="badge badge--square">{qualityScore}/100</span>}
            />
            <CardBody>
              <BarList
                rows={quality.map((q) => ({
                  label: q.label,
                  value: Math.round(q.score * 100),
                  display: `${Math.round(q.score * 100)}% · ${q.status}`,
                  tone: qualityTone(q.score),
                }))}
              />
            </CardBody>
          </Card>
        </div>

        {/* RIGHT — the intelligence panel */}
        <div className="stack">
          <Card>
            <CardHead
              eyebrow="AI-assisted"
              title="Compliance summary"
              subtitle="Assistance metric — inspectors make the final decision"
            />
            <CardBody>
              <div className="summary-score">
                <span className="summary-score__num">{complianceScore}</span>
                <span className="cell-muted">/ 100 assistance score</span>
              </div>
              <div className="summary-breakdown" style={{ marginTop: 'var(--space-4)' }}>
                {breakdown.map((b) => (
                  <div key={b.label} className="summary-breakdown__item" style={{ background: toneSoft(b.tone) }}>
                    <span className="row" style={{ gap: 6 }}>
                      <span className="badge__dot" style={{ color: toneColor(b.tone) }} aria-hidden />
                      {b.label}
                    </span>
                    <span className="summary-breakdown__count">{b.value}</span>
                  </div>
                ))}
              </div>
              {reviewedIds.size > 0 && (
                <p style={{ marginTop: 'var(--space-3)', fontSize: 'var(--fs-sm)', color: 'var(--tone-positive)' }}>
                  {reviewedIds.size} decision{reviewedIds.size > 1 ? 's' : ''} recorded this session (demo).
                </p>
              )}
            </CardBody>
          </Card>

          <SectionCard
            eyebrow="Extraction"
            title="Detected declarations"
            subtitle="Select a declaration to locate it on the label"
          >
            {declarations.length === 0 ? (
              <EmptyState icon="image" title="No declarations detected" />
            ) : (
              <div className="stack stack--sm">
                {declarations.map((d) => (
                  <DeclarationField
                    key={`${d.field}-${d.value}`}
                    declaration={d}
                    active={Boolean(d.regionId) && d.regionId === selectedRegionId}
                    onClick={() => d.regionId && setSelectedRegionId((cur) => (cur === d.regionId ? null : d.regionId!))}
                  />
                ))}
              </div>
            )}
          </SectionCard>

          <SectionCard
            eyebrow="Findings"
            title="Compliance findings"
            subtitle="Open any finding to see the evidence and why it was flagged"
          >
            <div className="stack stack--sm">
              {findings.map((f) => (
                <FindingCard
                  key={f.id}
                  finding={f}
                  active={openFinding?.id === f.id}
                  onOpen={openFindingCard}
                />
              ))}
            </div>
          </SectionCard>

          <EvidencePlanner rows={evidencePlanRows} />
        </div>
      </div>

      {openFinding && (
        <EvidenceDrawer
          finding={openFinding}
          onClose={() => setOpenFinding(null)}
          onReviewed={(findingId) => setReviewedIds((prev) => new Set(prev).add(findingId))}
        />
      )}
    </>
  );
}
