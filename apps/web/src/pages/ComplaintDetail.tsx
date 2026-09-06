import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';

import type {
  AssignableInspector,
  ComplaintDetail,
  ComplaintTransitionRequest,
} from '@legalmet/types';

import { api, ApiClientError } from '../api/client';
import { useApp } from '../app/AppContext';
import { Badge } from '../components/Badge';
import { Card, CardBody, CardHead } from '../components/Card';
import { Icon } from '../components/Icon';
import { Modal } from '../components/Modal';
import { PageHeader } from '../components/PageHeader';
import { AsyncView, ErrorState } from '../components/states';
import { useAsync } from '../data/useAsync';
import { useObjectUrl } from '../intake/useObjectUrl';
import { formatDateTime } from '../lib/format';
import {
  COMPLAINT_RISK_META,
  COMPLAINT_STATUS_META,
  complaintEventLabel,
} from '../lib/complaintStatus';

/**
 * COMPLAINT REVIEW (UI-03) — /complaints/:id.
 *
 * The department decides: start review → accept / reject / request
 * information → assign → create inspection → complete → close. Every action
 * is one backend state-machine transition (confirmed, reason-validated,
 * audited with the acting user) — this page only requests transitions, it
 * never sets a status directly. Legal language: "suspected issue", "possible
 * non-compliance", "requires official verification" — the system never
 * declares a violation.
 */

const INFO_PRESETS = [
  'A clearer photo of the full label',
  'A photo of the MRP / price marking',
  'The batch number and expiry date',
  'The exact shop name and address',
];

/** Complaint transitions are a department act (backend-enforced for
 * INSPECTOR/SUPERVISOR/ADMIN); AUDITOR is read-only here too. */
const WRITE_ROLES = ['INSPECTOR', 'SUPERVISOR', 'ADMIN'];

type ActionKind =
  | 'START_REVIEW'
  | 'ACCEPT'
  | 'REJECT'
  | 'REQUEST_INFORMATION'
  | 'ASSIGN'
  | 'CREATE_INSPECTION'
  | 'COMPLETE_INSPECTION'
  | 'RECORD_ACTION'
  | 'CLOSE';

/** Actions available from each status (mirrors the backend's legal edges). */
const ACTIONS_BY_STATUS: Record<string, { kind: ActionKind; label: string; primary?: boolean; danger?: boolean }[]> = {
  SUBMITTED: [{ kind: 'START_REVIEW', label: 'Start review', primary: true }],
  UNDER_REVIEW: [
    { kind: 'ACCEPT', label: 'Accept', primary: true },
    { kind: 'REQUEST_INFORMATION', label: 'Request information' },
    { kind: 'REJECT', label: 'Reject', danger: true },
  ],
  ACCEPTED: [
    { kind: 'CREATE_INSPECTION', label: 'Create Targeted Inspection', primary: true },
    { kind: 'ASSIGN', label: 'Assign inspector' },
  ],
  ASSIGNED: [{ kind: 'CREATE_INSPECTION', label: 'Create Targeted Inspection', primary: true }],
  INSPECTION_SCHEDULED: [{ kind: 'COMPLETE_INSPECTION', label: 'Mark inspection completed', primary: true }],
  INSPECTION_COMPLETED: [
    { kind: 'RECORD_ACTION', label: 'Record action taken', primary: true },
    { kind: 'CLOSE', label: 'Close complaint' },
  ],
  ACTION_TAKEN: [{ kind: 'CLOSE', label: 'Close complaint', primary: true }],
};

/** UI-04 deep links from the command center (?action=assign / inspect / …)
 * mapped to the action dialog — only if legal for the complaint's status. */
const ACTION_PARAMS: Record<string, ActionKind> = {
  review: 'START_REVIEW',
  accept: 'ACCEPT',
  reject: 'REJECT',
  'request-information': 'REQUEST_INFORMATION',
  assign: 'ASSIGN',
  inspect: 'CREATE_INSPECTION',
};

export function ComplaintDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const query = useAsync(() => api.complaintGet(id ?? ''), [id]);

  // Consume the deep-link param once so a page refresh does not reopen the
  // dialog; the requested action is validated against the legal edges below.
  const requestedAction = searchParams.get('action');
  useEffect(() => {
    if (requestedAction) setSearchParams({}, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [requestedAction]);

  if (!id) return <ErrorState title="No complaint selected" />;

  return (
    <div className="page">
      <AsyncView query={query} loadingLabel="Loading complaint…">
        {(detail) => {
          const wanted = requestedAction ? ACTION_PARAMS[requestedAction] : undefined;
          const legal = (ACTIONS_BY_STATUS[detail.status] ?? []).some((a) => a.kind === wanted);
          return (
            <ComplaintReview
              key={detail.id}
              detail={detail}
              initialAction={legal ? wanted : undefined}
              onOpenInspection={(iid) => navigate(`/inspections/${iid}`)}
            />
          );
        }}
      </AsyncView>
    </div>
  );
}

function ComplaintReview({
  detail: initial,
  initialAction,
  onOpenInspection,
}: {
  detail: ComplaintDetail;
  initialAction?: ActionKind;
  onOpenInspection: (inspectionId: string) => void;
}) {
  const [detail, setDetail] = useState<ComplaintDetail>(initial);
  const { user } = useApp();
  const canAct = WRITE_ROLES.includes(user.role);
  const [action, setAction] = useState<ActionKind | null>(canAct ? (initialAction ?? null) : null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const meta = COMPLAINT_STATUS_META[detail.status];
  const actions = ACTIONS_BY_STATUS[detail.status] ?? [];

  async function runTransition(body: ComplaintTransitionRequest, successNote: string) {
    setBusy(true);
    setError(null);
    try {
      const updated = await api.complaintTransition(detail.id, body);
      setDetail(updated);
      setAction(null);
      setNotice(successNote);
    } catch (err) {
      setError(
        err instanceof ApiClientError
          ? err.message
          : 'The action could not be applied. Check your connection and try again.',
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader
        eyebrow={`Complaint ${detail.reference}`}
        title={detail.product}
        lead={`Submitted ${formatDateTime(detail.createdAt)} · Suspected issue: ${detail.issue}`}
        actions={
          <>
            <Link to="/complaints" className="btn btn--ghost">
              <Icon name="chevronLeft" size={15} />
              Intake queue
            </Link>
          </>
        }
      />

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

      <div className="grid grid--2">
        {/* --- Status + actions ------------------------------------------------ */}
        <Card>
          <CardHead
            eyebrow="Status"
            title={meta.label}
            subtitle={meta.hint}
            actions={<Badge tone={meta.tone} dot>{detail.status}</Badge>}
          />
          <CardBody>
            <dl className="kv">
              <dt>Complaint ID</dt>
              <dd className="cell-mono">{detail.reference}</dd>
              <dt>Status</dt>
              <dd>{meta.label}</dd>
              <dt>System screening</dt>
              <dd>
                {detail.screeningRisk ? (
                  <Badge
                    tone={COMPLAINT_RISK_META[detail.screeningRisk]?.tone}
                    outline
                    title="Deterministic rule over the scan's detected declarations — decision support, not an official determination"
                  >
                    {detail.screeningRisk} (system screening)
                  </Badge>
                ) : (
                  'Not assessed'
                )}
              </dd>
              <dt>Official priority</dt>
              <dd>
                {detail.officialPriority ? (
                  <Badge tone={COMPLAINT_RISK_META[detail.officialPriority]?.tone} dot>
                    {detail.officialPriority} (official decision)
                  </Badge>
                ) : (
                  'Not set — decided during review'
                )}
              </dd>
              <dt>Assigned inspector</dt>
              <dd>{detail.assignedInspectorName ?? 'Unassigned'}</dd>
              <dt>Location</dt>
              <dd>{detail.location ?? '—'}</dd>
              {detail.shop && (
                <>
                  <dt>Shop</dt>
                  <dd>{detail.shop}</dd>
                </>
              )}
              {detail.reporterName && (
                <>
                  <dt>Reporter</dt>
                  <dd>
                    {detail.reporterName}
                    {detail.reporterContact ? ` · ${detail.reporterContact}` : ''}
                  </dd>
                </>
              )}
              {detail.description && (
                <>
                  <dt>Description</dt>
                  <dd>{detail.description}</dd>
                </>
              )}
            </dl>

            {detail.status === 'REQUEST_INFORMATION' && detail.pendingInfoRequest && (
              <div className="complaint-inforeq" role="note">
                <Icon name="info" size={15} />
                <span>
                  <strong>Waiting for the citizen.</strong> Requested:{' '}
                  {detail.pendingInfoRequest}
                </span>
              </div>
            )}

            {detail.inspection && (
              <div className="complaint-linked" role="region" aria-label="Linked inspection">
                <div>
                  <span className="cell-muted" style={{ fontSize: 'var(--fs-xs)' }}>
                    Linked inspection
                  </span>
                  <div className="cell-strong cell-mono">{detail.inspection.referenceNo}</div>
                  <span className="cell-muted" style={{ fontSize: 'var(--fs-sm)' }}>
                    Status: {detail.inspection.status.replace(/_/g, ' ').toLowerCase()}
                    {detail.assignedInspectorName ? ` · ${detail.assignedInspectorName}` : ''}
                  </span>
                </div>
                <button
                  type="button"
                  className="btn btn--sm"
                  onClick={() => onOpenInspection(detail.inspection!.id)}
                >
                  <Icon name="inspections" size={14} />
                  {detail.inspection.status === 'COMPLETED' || detail.inspection.status === 'ARCHIVED'
                    ? 'View inspection'
                    : 'Open inspection'}
                </button>
              </div>
            )}

            {canAct && actions.length > 0 && (
              <div className="row row--wrap" style={{ gap: 'var(--space-2)', marginTop: 'var(--space-4)' }}>
                {actions.map((a) => (
                  <button
                    key={a.kind}
                    type="button"
                    className={`btn ${a.primary ? 'btn--primary' : a.danger ? 'btn--danger' : 'btn--subtle'}`}
                    onClick={() => {
                      setError(null);
                      setNotice(null);
                      setAction(a.kind);
                    }}
                  >
                    {a.label}
                  </button>
                ))}
              </div>
            )}
            {!canAct && actions.length > 0 && (
              <p className="cell-muted" style={{ marginTop: 'var(--space-4)' }}>
                Your role ({user.role.toLowerCase()}) is read-only — complaint actions are limited
                to inspectors, supervisors and admins.
              </p>
            )}
            {(detail.status === 'REJECTED' || detail.status === 'CLOSED') && (
              <p className="cell-muted" style={{ marginTop: 'var(--space-3)' }}>
                This complaint is {meta.label.toLowerCase()} — no further actions are available.
              </p>
            )}
          </CardBody>
        </Card>

        {/* --- Evidence review -------------------------------------------------- */}
        <Card id="evidence">
          <CardHead
            eyebrow="Evidence"
            title="Citizen-submitted evidence"
            subtitle="The submission-time snapshot — citizen responses are appended, never overwritten"
          />
          <CardBody>
            <EvidenceImage url={detail.evidence?.imageUrl ?? null} />
            {detail.evidence?.scanReference && (
              <p className="cell-muted" style={{ fontSize: 'var(--fs-sm)' }}>
                From scan <span className="cell-mono">{detail.evidence.scanReference}</span>
              </p>
            )}
            {detail.evidence?.quality && (
              <p className="cell-muted" style={{ fontSize: 'var(--fs-sm)' }}>
                Image quality grade:{' '}
                {String(
                  (detail.evidence.quality as Record<string, unknown>).grade ?? 'unknown',
                )}
              </p>
            )}

            <h3 className="cell-strong" style={{ margin: 'var(--space-4) 0 var(--space-2)' }}>
              Detected declarations
            </h3>
            <p className="cell-muted" style={{ fontSize: 'var(--fs-sm)', margin: 0 }}>
              What the OCR + extraction pipeline read from the citizen's photo. These are
              readings, not compliance conclusions — verification is the inspector's job.
            </p>
            <ul className="complaint-fields">
              {(detail.evidence?.detectedFields ?? []).map((f, i) => (
                <li key={i} className="complaint-fields__row">
                  <span className="complaint-fields__label">{f.label}</span>
                  <span className={f.status === 'NOT_EXTRACTED' ? 'cell-muted' : 'cell-strong'}>
                    {f.status === 'NOT_EXTRACTED'
                      ? 'not read'
                      : (f.normalizedValue ?? f.rawText ?? '—')}
                  </span>
                  <Badge
                    tone={f.status === 'DETECTED' ? 'positive' : f.status === 'REVIEW_REQUIRED' ? 'warning' : 'neutral'}
                    outline
                  >
                    {f.status.replace(/_/g, ' ').toLowerCase()}
                  </Badge>
                </li>
              ))}
              {(detail.evidence?.detectedFields?.length ?? 0) === 0 && (
                <li className="cell-muted">No declarations were read from the photo.</li>
              )}
            </ul>

            {(detail.evidence?.citizenFollowUps?.length ?? 0) > 0 && (
              <>
                <h3 className="cell-strong" style={{ margin: 'var(--space-4) 0 var(--space-2)' }}>
                  Citizen responses
                </h3>
                <ul className="stack stack--sm">
                  {detail.evidence!.citizenFollowUps!.map((f, i) => (
                    <li key={i} className="complaint-followup">
                      <div className="cell-muted" style={{ fontSize: 'var(--fs-xs)' }}>
                        {formatDateTime(f.at)}
                        {f.location ? ` · ${f.location}` : ''}
                      </div>
                      <p style={{ margin: 0, whiteSpace: 'pre-wrap' }}>{f.message}</p>
                      {f.imageUrl && <FollowUpImage url={f.imageUrl} />}
                    </li>
                  ))}
                </ul>
              </>
            )}
          </CardBody>
        </Card>
      </div>

      {/* --- Timeline (real recorded events only) ------------------------------ */}
      <Card>
        <CardHead
          eyebrow="History"
          title="Complaint timeline"
          subtitle="Every entry is a real recorded, audited event — nothing here is inferred"
        />
        <CardBody>
          <ol className="timeline">
            {detail.events.map((event) => (
              <li key={event.id} className="timeline__item">
                <span
                  className={`timeline__dot timeline__dot--${
                    event.actorType === 'CITIZEN' ? 'citizen' : 'department'
                  }`}
                  aria-hidden
                />
                <div>
                  <div className="row row--between row--wrap" style={{ gap: 'var(--space-2)' }}>
                    <span className="cell-strong">{complaintEventLabel(event.event)}</span>
                    <span className="cell-muted" style={{ fontSize: 'var(--fs-xs)' }}>
                      {formatDateTime(event.createdAt)}
                    </span>
                  </div>
                  <div className="cell-muted" style={{ fontSize: 'var(--fs-sm)' }}>
                    {event.actorType === 'CITIZEN'
                      ? 'Citizen (anonymous)'
                      : (event.actorName ?? 'Department officer')}
                  </div>
                  {event.note && (
                    <p className="timeline__note">{event.note}</p>
                  )}
                </div>
              </li>
            ))}
          </ol>
        </CardBody>
      </Card>

      {/* --- Action dialogs ----------------------------------------------------- */}
      {action === 'CREATE_INSPECTION' && (
        <CreateInspectionDialog
          detail={detail}
          busy={busy}
          onCancel={() => setAction(null)}
          onSubmit={runTransition}
        />
      )}
      {action && action !== 'CREATE_INSPECTION' && (
        <ActionDialog
          kind={action}
          busy={busy}
          onCancel={() => setAction(null)}
          onSubmit={runTransition}
        />
      )}
    </>
  );
}

/** evidence.imageUrl is an app-relative `/api/v1/storage/{key}` URL; the
 * bearer-authed fetcher wants the bare storage key. */
function storageKeyFromUrl(url: string): string {
  return url.replace(/^\/api\/v1\/storage\//, '');
}

function EvidenceImage({ url }: { url: string | null }) {
  const state = useObjectUrl(url ? storageKeyFromUrl(url) : null);
  if (state.status === 'loading') return <p className="cell-muted">Loading photo…</p>;
  if (state.status === 'error') return <p className="cell-muted">{state.message}</p>;
  return (
    <a href={state.url} target="_blank" rel="noreferrer" className="complaint-photo">
      <img src={state.url} alt="Package photo submitted by the citizen" />
    </a>
  );
}

function FollowUpImage({ url }: { url: string }) {
  const state = useObjectUrl(storageKeyFromUrl(url));
  if (state.status !== 'ready') return null;
  return (
    <a href={state.url} target="_blank" rel="noreferrer" className="complaint-photo complaint-photo--sm">
      <img src={state.url} alt="Photo attached by the citizen in response" />
    </a>
  );
}

const ACTION_COPY: Record<ActionKind, { title: string; body: string; confirm: string; success: string }> = {  START_REVIEW: {
    title: 'Start reviewing this complaint',
    body: 'The complaint moves to UNDER_REVIEW. This does not express any judgement on the suspected issue.',
    confirm: 'Start review',
    success: 'Review started — the complaint is now UNDER_REVIEW.',
  },
  ACCEPT: {
    title: 'Accept this complaint',
    body: 'Accepted for further review. The complaint is NOT marked as a confirmed violation — acceptance means the reported suspected issue merits departmental follow-up.',
    confirm: 'Accept complaint',
    success: 'Complaint accepted for further review.',
  },
  REJECT: {
    title: 'Reject this complaint',
    body: 'A reason is required and is recorded in the audit trail. Rejection is terminal — the complaint cannot be reopened.',
    confirm: 'Reject complaint',
    success: 'Complaint rejected.',
  },
  REQUEST_INFORMATION: {
    title: 'Request information from the citizen',
    body: 'The citizen sees this request on their complaint and can respond with a message and an optional photo. The complaint returns to UNDER_REVIEW once they respond.',
    confirm: 'Send request',
    success: 'Information requested — waiting for the citizen to respond.',
  },
  ASSIGN: {
    title: 'Assign an inspector',
    body: 'The assigned inspector is recorded on the complaint and in the audit trail.',
    confirm: 'Assign inspector',
    success: 'Inspector assigned.',
  },
  CREATE_INSPECTION: {
    title: 'Create an inspection from this complaint',
    body: 'A REAL inspection is created through the existing inspection service, linked to this complaint (and carrying its reference in the note). This does NOT mark anything as inspected — the inspection then proceeds through its own workflow.',
    confirm: 'Create inspection',
    success: 'Inspection created and linked to this complaint.',
  },
  COMPLETE_INSPECTION: {
    title: 'Mark the inspection completed',
    body: 'Records that the linked field inspection has been completed. Enforcement outcomes are recorded on the inspection itself.',
    confirm: 'Mark completed',
    success: 'Inspection marked completed.',
  },
  RECORD_ACTION: {
    title: 'Record action taken',
    body: 'Records that enforcement/administrative action has been taken on this complaint.',
    confirm: 'Record action',
    success: 'Action recorded.',
  },
  CLOSE: {
    title: 'Close this complaint',
    body: 'Closing is terminal. The full history and audit trail remain available.',
    confirm: 'Close complaint',
    success: 'Complaint closed.',
  },
};

function ActionDialog({
  kind,
  busy,
  onCancel,
  onSubmit,
}: {
  kind: ActionKind;
  busy: boolean;
  onCancel: () => void;
  onSubmit: (body: ComplaintTransitionRequest, successNote: string) => Promise<void>;
}) {
  const copy = ACTION_COPY[kind];
  const [reason, setReason] = useState('');
  const [inspectorId, setInspectorId] = useState('');
  const [priority, setPriority] = useState('');
  const [error, setError] = useState<string | null>(null);

  const inspectors = useAsync<AssignableInspector[]>(() => {
    // Only the ASSIGN dialog needs the list.
    return kind === 'ASSIGN' ? api.complaintInspectors() : Promise.resolve([]);
  }, [kind]);

  const needsReason = kind === 'REJECT' || kind === 'REQUEST_INFORMATION';

  const reasonValue =
    kind === 'REQUEST_INFORMATION' && INFO_PRESETS.includes(reason)
      ? reason
      : reason.trim();

  async function submit() {
    if (needsReason && !reasonValue) {
      setError(
        kind === 'REJECT'
          ? 'A reason is required to reject a complaint.'
          : 'Describe the information you need from the citizen.',
      );
      return;
    }
    if (kind === 'ASSIGN' && !inspectorId) {
      setError('Choose an inspector to assign.');
      return;
    }
    setError(null);
    await onSubmit(
      {
        action: kind,
        reason: needsReason ? reasonValue : undefined,
        inspectorId: kind === 'ASSIGN' ? inspectorId : undefined,
        officialPriority: priority || undefined,
      },
      copy.success,
    );
  }

  return (
    <Modal
      title={copy.title}
      onClose={onCancel}
      footer={
        <>
          <button type="button" className="btn btn--subtle" onClick={onCancel} disabled={busy}>
            Cancel
          </button>
          <button
            type="button"
            className={`btn ${kind === 'REJECT' ? 'btn--danger' : 'btn--primary'}`}
            onClick={() => void submit()}
            disabled={busy}
          >
            {busy ? <span className="spinner" aria-hidden /> : <Icon name="check" size={15} />}
            {copy.confirm}
          </button>
        </>
      }
    >
      <div className="stack">
        <p className="cell-muted" style={{ margin: 0 }}>
          {copy.body}
        </p>

        {kind === 'REJECT' && (
          <div className="field">
            <label className="field__label" htmlFor="reject-reason">
              Reason (required, audited)
            </label>
            <textarea
              id="reject-reason"
              className="input"
              rows={3}
              maxLength={4000}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="e.g. The photo does not show the reported marking; insufficient evidence to proceed"
            />
          </div>
        )}

        {kind === 'REQUEST_INFORMATION' && (
          <>
            <div className="field">
              <span className="field__label">Quick requests</span>
              <div className="row row--wrap" style={{ gap: 6 }}>
                {INFO_PRESETS.map((preset) => (
                  <button
                    key={preset}
                    type="button"
                    className="btn btn--ghost btn--sm"
                    onClick={() => setReason(preset)}
                  >
                    {preset}
                  </button>
                ))}
              </div>
            </div>
            <div className="field">
              <label className="field__label" htmlFor="info-request">
                Requested information (required, shown to the citizen)
              </label>
              <textarea
                id="info-request"
                className="input"
                rows={3}
                maxLength={4000}
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="Describe exactly what the citizen should provide…"
              />
            </div>
          </>
        )}

        {kind === 'ASSIGN' && (
          <div className="field">
            <label className="field__label" htmlFor="assign-inspector">
              Inspector
            </label>
            <select
              id="assign-inspector"
              className="input"
              value={inspectorId}
              onChange={(e) => setInspectorId(e.target.value)}
            >
              <option value="">Choose an inspector…</option>
              {inspectors.data?.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.fullName} ({u.role.toLowerCase()})
                </option>
              ))}
            </select>
          </div>
        )}

        {(kind === 'ACCEPT' || kind === 'ASSIGN') && (
          <div className="field">
            <label className="field__label" htmlFor="official-priority">
              Official priority decision (optional)
            </label>
            <select
              id="official-priority"
              className="input"
              value={priority}
              onChange={(e) => setPriority(e.target.value)}
            >
              <option value="">No change</option>
              <option value="HIGH">High</option>
              <option value="MEDIUM">Medium</option>
              <option value="LOW">Low</option>
            </select>
            <span className="cell-muted" style={{ fontSize: 'var(--fs-xs)' }}>
              Distinct from the system screening shown on the queue.
            </span>
          </div>
        )}

        {error && (
          <p className="cell-strong" style={{ color: 'var(--tone-critical)', margin: 0 }} role="alert">
            {error}
          </p>
        )}
      </div>
    </Modal>
  );
}

/**
 * UI-05 — the CREATE_INSPECTION confirmation panel. Distinct from the generic
 * action dialog on purpose: converting a complaint into a targeted inspection
 * is the pivotal department decision, so the officer confirms against a full
 * pre-flight summary (complaint, reported issue, product, location, evidence,
 * priority) before a real inspection record is created. The backend re-checks
 * everything server-side; nothing here is trusted input.
 */
function CreateInspectionDialog({
  detail,
  busy,
  onCancel,
  onSubmit,
}: {
  detail: ComplaintDetail;
  busy: boolean;
  onCancel: () => void;
  onSubmit: (body: ComplaintTransitionRequest, successNote: string) => Promise<void>;
}) {
  const [priorityChoice, setPriorityChoice] = useState('');
  const [error, setError] = useState<string | null>(null);

  const evidence = detail.evidence;
  const photoCount = evidence?.imageUrl ? 1 : 0;
  const followUpCount = evidence?.citizenFollowUps?.length ?? 0;
  const fieldCount = evidence?.detectedFields?.length ?? 0;
  const evidenceSummary = [
    photoCount > 0 ? `${photoCount} photo` : null,
    followUpCount > 0 ? `${followUpCount} citizen response${followUpCount === 1 ? '' : 's'}` : null,
    fieldCount > 0 ? `${fieldCount} detected declaration${fieldCount === 1 ? '' : 's'}` : null,
  ]
    .filter(Boolean)
    .join(' · ');
  const priority = detail.officialPriority ?? detail.screeningRisk;

  // Pre-flight (client side; the backend enforces the same invariant): a
  // complaint with nothing verifiable must not be converted.
  const missingEvidence = photoCount === 0 && followUpCount === 0 && !detail.description?.trim();

  async function submit() {
    if (missingEvidence) {
      setError(
        'Additional information required: this complaint has no verifiable evidence to inspect — ' +
          'no photo, no citizen description and no follow-up responses. Request information from the citizen first.',
      );
      return;
    }
    setError(null);
    await onSubmit(
      { action: 'CREATE_INSPECTION', officialPriority: priorityChoice || undefined },
      'Targeted inspection created and linked to this complaint.',
    );
  }

  return (
    <Modal
      title="Create a targeted inspection"
      onClose={onCancel}
      footer={
        <>
          <button type="button" className="btn btn--subtle" onClick={onCancel} disabled={busy}>
            Cancel
          </button>
          <button
            type="button"
            className="btn btn--primary"
            onClick={() => void submit()}
            disabled={busy}
          >
            {busy ? <span className="spinner" aria-hidden /> : <Icon name="inspections" size={15} />}
            Create inspection
          </button>
        </>
      }
    >
      <div className="stack">
        <p className="cell-muted" style={{ margin: 0 }}>
          A REAL inspection will be created through the existing inspection workflow, linked to this
          complaint and carrying the citizen&rsquo;s evidence as immutable source material. The
          complaint moves to INSPECTION_SCHEDULED — nothing is marked as a violation. The inspector
          independently verifies and makes the official decision.
        </p>

        <dl className="kv">
          <dt>Complaint</dt>
          <dd className="cell-mono">{detail.reference}</dd>
          <dt>Reported issue</dt>
          <dd>{detail.issue}</dd>
          <dt>Product</dt>
          <dd>{detail.product}</dd>
          <dt>Location</dt>
          <dd>{detail.location ?? '—'}</dd>
          <dt>Evidence</dt>
          <dd>{evidenceSummary || 'None recorded'}</dd>
          <dt>Priority</dt>
          <dd>
            {priority ? (
              <Badge tone={COMPLAINT_RISK_META[priority]?.tone} outline>
                {priority} ({detail.officialPriority ? 'official decision' : 'system screening'})
              </Badge>
            ) : (
              'Not assessed'
            )}
          </dd>
        </dl>

        <div className="field">
          <label className="field__label" htmlFor="target-priority">
            Official priority decision (optional)
          </label>
          <select
            id="target-priority"
            className="input"
            value={priorityChoice}
            onChange={(e) => setPriorityChoice(e.target.value)}
            disabled={busy}
          >
            <option value="">No change</option>
            <option value="HIGH">High</option>
            <option value="MEDIUM">Medium</option>
            <option value="LOW">Low</option>
          </select>
          <span className="cell-muted" style={{ fontSize: 'var(--fs-xs)' }}>
            Distinct from the system screening shown on the queue.
          </span>
        </div>

        {missingEvidence && (
          <div className="complaint-inforeq" role="alert">
            <Icon name="alert" size={15} />
            <span>
              <strong>Additional information required.</strong> This complaint has no verifiable
              evidence to inspect. Request information from the citizen before creating a targeted
              inspection.
            </span>
          </div>
        )}

        {error && (
          <p className="cell-strong" style={{ color: 'var(--tone-critical)', margin: 0 }} role="alert">
            {error}
          </p>
        )}
      </div>
    </Modal>
  );
}
