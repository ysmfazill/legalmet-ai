/**
 * LOT INTELLIGENCE (UI-07) — LOT → PACKAGES → SAMPLE → MEASUREMENTS →
 * REGULATORY EVALUATION → LOT RESULT.
 *
 * Everything on this card is a real persisted record. The honesty contracts:
 *
 * - A lot is created with an immutable declared quantity and REAL package
 *   records (no fabricated sample results).
 * - Sampling either references a CONFIGURED legal procedure (shown with its
 *   code/version) or is explicitly AI-recommended and requires inspector
 *   confirmation. Without a configured procedure the UI says
 *   "Sampling procedure requires inspector confirmation." — it never claims
 *   "AI selected the legally required sample".
 * - A drawn sample is stable: the run keeps its seed and is not silently
 *   regenerated. Redrawing is blocked once any package is measured.
 * - Package statistics are labelled OBSERVED — they are not legal compliance
 *   results. Aggregate formulas only appear when the configured rule defines
 *   them.
 * - The lot decision (COMPLIANT / NON_COMPLIANT / REQUIRES_REVIEW) is an
 *   explicit inspector action, blocked with "Insufficient evidence" while
 *   measurements are missing. The system never auto-classifies a lot.
 */
import { useState } from 'react';

import type {
  EvidencePlanItem,
  EvidencePlanVerificationRef,
  LotDetail,
  LotPackage,
  LotStatus,
  SamplingMethod,
  VerificationResult,
} from '@legalmet/types';

import { useApp } from '../app/AppContext';
import { api } from '../api/client';
import { Badge } from '../components/Badge';
import { Card, CardBody, CardHead } from '../components/Card';
import { DataTable, type Column } from '../components/DataTable';
import { Drawer } from '../components/Drawer';
import { Icon } from '../components/Icon';
import { useAsync } from '../data/useAsync';
import { formatDateTime } from '../lib/format';
import { EvaluationBadge } from '../evidence/ObservedEvaluation';
import { VerificationPanel } from '../evidence/VerificationPanel';
import type { EvidencePlanState } from '../evidence/useEvidencePlan';
import { useEvidencePlan } from '../evidence/useEvidencePlan';

const WRITE_ROLES = ['INSPECTOR', 'SUPERVISOR', 'ADMIN'];

const LOT_STATUS_META: Record<LotStatus, { label: string; tone: 'positive' | 'critical' | 'warning' | 'info' }> = {
  IN_PROGRESS: { label: 'Verification in progress', tone: 'info' },
  COMPLIANT: { label: 'Lot compliant', tone: 'positive' },
  NON_COMPLIANT: { label: 'Lot non-compliant', tone: 'critical' },
  REQUIRES_REVIEW: { label: 'Requires review', tone: 'warning' },
};

const PACKAGE_STATUS_META: Record<string, { label: string; tone: 'positive' | 'warning' | 'neutral' }> = {
  NOT_SAMPLED: { label: 'Not sampled', tone: 'neutral' },
  PENDING: { label: 'Pending measurement', tone: 'warning' },
  MEASURED: { label: 'Measured', tone: 'positive' },
};

function LotStatusBadge({ status }: { status: LotStatus }) {
  const meta = LOT_STATUS_META[status] ?? LOT_STATUS_META.IN_PROGRESS;
  return (
    <Badge tone={meta.tone} dot>
      {meta.label}
    </Badge>
  );
}

/** The plan-row shape VerificationPanel expects, built from a lot package. */
function packageRow(lot: LotDetail, pkg: LotPackage): EvidencePlanItem {
  const measurement = pkg.measurement;
  const latestResult: VerificationResult | null = measurement?.latestResult
    ? {
        ...measurement.latestResult,
        taskId: measurement.taskId,
        createdAt: measurement.latestResult.recordedAt,
      }
    : null;
  const verification: EvidencePlanVerificationRef | null = measurement
    ? {
        id: measurement.taskId,
        taskType: 'MEASUREMENT',
        status: measurement.taskStatus,
        requirementLevel: 'REQUIRED',
        reason: `Physical verification of lot package ${pkg.label}`,
        createdAt: lot.createdAt,
        observed: measurement.observed ?? null,
        evaluation: measurement.evaluation ?? null,
        latestResult,
      }
    : null;
  return {
    title: `${lot.label} · ${pkg.label}`,
    declaredValue: lot.declaredValue,
    unit: null,
    evidence: [],
    gaps: [],
    status: 'VERIFIED',
    summary: `Lot package measurement — the declared quantity ${lot.declaredValue} is fixed for the whole lot.`,
    verification,
  };
}

function SamplingSection({
  lot,
  canWrite,
  busy,
  onDone,
}: {
  lot: LotDetail;
  canWrite: boolean;
  busy: boolean;
  onDone: () => void;
}) {
  const hasMeasurements = lot.statistics.measured > 0;
  const procedure = lot.samplingProcedure ?? null;

  const [sampleSize, setSampleSize] = useState('');
  const [seed, setSeed] = useState('');
  const [method, setMethod] = useState<SamplingMethod>('RANDOM');
  const [confirmAiSample, setConfirmAiSample] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const drawSample = async () => {
    setError(null);
    try {
      await api.generateLotSample(lot.id, {
        sampleSize: sampleSize.trim() ? Number.parseInt(sampleSize, 10) : null,
        selectionMethod: method,
        seed: seed.trim() || null,
        confirmAiSample,
      });
      setSampleSize('');
      setSeed('');
      setConfirmAiSample(false);
      onDone();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Sampling failed');
    }
  };

  return (
    <section className="stack stack--sm">
      <h3 className="cell-strong" style={{ margin: 0, fontSize: 'var(--fs-sm)' }}>
        Legal sampling
      </h3>

      {procedure ? (
        <div className="demo-note" style={{ display: 'flex', gap: 8, borderColor: 'var(--tone-positive)' }} role="note">
          <Icon name="shield" size={15} />
          <span>
            <strong>Configured sampling procedure:</strong> {procedure.code} — {procedure.title}
            {procedure.versionLabel ? ` (version ${procedure.versionLabel})` : ''}
            {procedure.sampleSize != null ? ` · sample size ${procedure.sampleSize}` : ''}
            {procedure.method ? ` · method ${procedure.method}` : ''}
            {procedure.sourceReference ? ` · source ${procedure.sourceReference}` : ''}. A sample drawn
            here follows this deterministic, versioned rule.
          </span>
        </div>
      ) : (
        <div className="demo-note" style={{ display: 'flex', gap: 8 }} role="note">
          <Icon name="alert" size={15} />
          <span>
            <strong>No sampling procedure is configured</strong> for the applicable regulation
            version — <strong>sampling procedure requires inspector confirmation.</strong> A sample
            drawn here is AI-recommended (reproducible from its stored seed), not the legally
            required sample.
          </span>
        </div>
      )}

      {lot.samplingRuns.length > 0 && (
        <div className="detail-list">
          {lot.samplingRuns.map((run) => (
            <div className="detail-list__row" key={run.id}>
              <span className="detail-list__key">
                Sample run {run.id.slice(0, 8)}… · {formatDateTime(run.createdAt)}
              </span>
              <span className="detail-list__val">
                {run.sampleSize} package{run.sampleSize > 1 ? 's' : ''} · {run.selectionMethod.toLowerCase()}
                {run.seed ? ` · seed “${run.seed}” (reproducible)` : ''}
                {' · '}
                {run.procedureCode ? (
                  <span>per configured procedure {run.procedureCode}</span>
                ) : (
                  <span>AI-recommended — confirmed by the inspector</span>
                )}
                {` · drawn by ${run.createdBy.slice(0, 8)}…`}
              </span>
            </div>
          ))}
        </div>
      )}

      {error && (
        <div className="demo-note demo-note--error" style={{ display: 'flex', gap: 8 }} role="alert">
          <Icon name="alert" size={15} />
          <span>{error}</span>
        </div>
      )}

      {canWrite && lot.status === 'IN_PROGRESS' && (
        hasMeasurements ? (
          <p className="cell-muted" style={{ margin: 0, fontSize: 'var(--fs-xs)' }}>
            Measurements exist for this lot — the sample cannot be silently replaced. A new sample
            is a new, separately audited decision on a lot with no measurements.
          </p>
        ) : (
          <div className="stack stack--sm" style={{ borderTop: '1px solid var(--border)', paddingTop: 'var(--space-3)' }}>
            <div className="grid grid--2">
              <label className="field">
                <span className="field__label">
                  Sample size {procedure?.sampleSize != null ? `(configured procedure fixes it at ${procedure.sampleSize})` : '(mandatory — no configured procedure)'}
                </span>
                <input
                  className="input"
                  type="number"
                  min="1"
                  step="1"
                  inputMode="numeric"
                  value={sampleSize}
                  onChange={(e) => setSampleSize(e.target.value)}
                  placeholder={`e.g. ${Math.min(3, lot.lotSize)}`}
                  disabled={busy || procedure?.sampleSize != null}
                />
              </label>
              <label className="field">
                <span className="field__label">Randomization seed (recommended — makes the draw reproducible)</span>
                <input
                  className="input"
                  value={seed}
                  onChange={(e) => setSeed(e.target.value)}
                  placeholder="e.g. LOT-0007-SEED-01"
                  disabled={busy}
                />
              </label>
              <label className="field">
                <span className="field__label">Selection method</span>
                <select
                  className="input"
                  value={method}
                  onChange={(e) => setMethod(e.target.value as SamplingMethod)}
                  disabled={busy}
                >
                  <option value="RANDOM">RANDOM — reproducible draw from the stored seed</option>
                  <option value="MANUAL">MANUAL — packages chosen by the inspector</option>
                </select>
              </label>
            </div>
            {!procedure && (
              <div className="field" style={{ margin: 0 }}>
                <span className="field__label">
                  Inspector confirmation (mandatory without a configured procedure)
                </span>
                <label className="row" style={{ gap: 6, fontSize: 'var(--fs-sm)' }}>
                  <input
                    type="checkbox"
                    checked={confirmAiSample}
                    onChange={(e) => setConfirmAiSample(e.target.checked)}
                    disabled={busy}
                  />
                  I confirm this AI-recommended sample as the inspector responsible for this lot.
                </label>
              </div>
            )}
            <div>
              <button
                type="button"
                className="btn btn--primary btn--sm"
                disabled={busy || (procedure?.sampleSize == null && !sampleSize.trim()) || (!procedure && !confirmAiSample)}
                onClick={() => void drawSample()}
              >
                <Icon name="package" size={14} />
                Draw sample
              </button>
            </div>
          </div>
        )
      )}
    </section>
  );
}

function DecisionSection({
  lot,
  canWrite,
  busy,
  onDone,
}: {
  lot: LotDetail;
  canWrite: boolean;
  busy: boolean;
  onDone: () => void;
}) {
  const remaining = lot.progress.remaining;
  const [decision, setDecision] = useState<LotStatus>('COMPLIANT');
  const [reason, setReason] = useState('');
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    setError(null);
    try {
      await api.submitLotDecision(lot.id, { decision, reason: reason.trim() });
      setReason('');
      onDone();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'The decision could not be submitted');
    }
  };

  return (
    <section className="stack stack--sm">
      <h3 className="cell-strong" style={{ margin: 0, fontSize: 'var(--fs-sm)' }}>
        Lot result
      </h3>

      {lot.status !== 'IN_PROGRESS' ? (
        <div className="detail-list">
          <div className="detail-list__row">
            <span className="detail-list__key">Decision</span>
            <span className="detail-list__val"><LotStatusBadge status={lot.status} /></span>
          </div>
          <div className="detail-list__row">
            <span className="detail-list__key">Reason</span>
            <span className="detail-list__val">{lot.decisionReason}</span>
          </div>
          <div className="detail-list__row">
            <span className="detail-list__key">Decided</span>
            <span className="detail-list__val">
              {lot.decidedBy ? `${lot.decidedBy.slice(0, 8)}… · ` : ''}
              {lot.decidedAt ? formatDateTime(lot.decidedAt) : ''}
            </span>
          </div>
        </div>
      ) : (
        <>
          {remaining > 0 ? (
            <div className="demo-note demo-note--error" style={{ display: 'flex', gap: 8 }} role="alert">
              <Icon name="alert" size={15} />
              <span>
                <strong>Insufficient evidence</strong> — {remaining} measurement
                {remaining > 1 ? 's' : ''} remaining. The lot result stays blocked until every
                sampled package is measured.
              </span>
            </div>
          ) : (
            <div className="demo-note" style={{ display: 'flex', gap: 8 }} role="note">
              <Icon name="info" size={15} />
              <span>
                All sampled packages are measured. The result below is <strong>your</strong>{' '}
                decision as inspector — the system computes observed differences and rule
                evaluations, never the lot verdict.
              </span>
            </div>
          )}
          {error && (
            <div className="demo-note demo-note--error" style={{ display: 'flex', gap: 8 }} role="alert">
              <Icon name="alert" size={15} />
              <span>{error}</span>
            </div>
          )}
          {canWrite && (
            <div className="stack stack--sm">
              <label className="field" style={{ margin: 0 }}>
                <span className="field__label">Lot result</span>
                <select
                  className="input"
                  value={decision}
                  onChange={(e) => setDecision(e.target.value as LotStatus)}
                  disabled={busy || remaining > 0}
                >
                  <option value="COMPLIANT">COMPLIANT</option>
                  <option value="NON_COMPLIANT">NON_COMPLIANT</option>
                  <option value="REQUIRES_REVIEW">REQUIRES_REVIEW</option>
                </select>
              </label>
              <label className="field" style={{ margin: 0 }}>
                <span className="field__label">Reason (mandatory — audited with the decision)</span>
                <textarea
                  className="textarea"
                  rows={2}
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  placeholder="Why this result, referencing the measured evidence"
                  disabled={busy || remaining > 0}
                />
              </label>
              <div>
                <button
                  type="button"
                  className="btn btn--primary btn--sm"
                  disabled={busy || remaining > 0 || reason.trim().length < 3}
                  onClick={() => void submit()}
                >
                  <Icon name="check" size={14} />
                  Submit lot result
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </section>
  );
}

function LotDetailDrawer({
  lotId,
  canWrite,
  planner,
  refreshKey,
  onClose,
}: {
  lotId: string;
  canWrite: boolean;
  planner: EvidencePlanState;
  refreshKey: number;
  onClose: () => void;
}) {
  const [version, setVersion] = useState(0);
  const [openMeasureTaskId, setOpenMeasureTaskId] = useState<string | null>(null);
  const [taskError, setTaskError] = useState<string | null>(null);

  const lotAsync = useAsync(() => api.getLot(lotId), [lotId, version, refreshKey]);
  const reload = () => setVersion((v) => v + 1);
  const lot = lotAsync.data ?? null;

  const measureTask = openMeasureTaskId
    ? (planner.tasks.find((t) => t.id === openMeasureTaskId) ?? null)
    : null;
  const measurePkg =
    lot && measureTask ? (lot.packages.find((p) => p.measurement?.taskId === measureTask.id) ?? null) : null;

  const openMeasurement = (pkg: LotPackage) => {
    setTaskError(null);
    const taskId = pkg.measurement?.taskId;
    if (!taskId) return;
    if (!planner.tasks.some((t) => t.id === taskId)) {
      setTaskError('The measurement task for this package is not loaded yet — retry in a moment.');
      return;
    }
    setOpenMeasureTaskId(taskId);
  };

  const columns: Column<LotPackage>[] = [
    {
      key: 'package',
      header: 'Package',
      render: (p) => (
        <span>
          <span className="cell-strong">{p.label}</span>
          <span className="cell-muted" style={{ fontSize: 'var(--fs-xs)' }}> · position {p.position}</span>
        </span>
      ),
    },
    { key: 'declared', header: 'Declared', render: () => lot?.declaredValue ?? '—' },
    {
      key: 'measured',
      header: 'Measured',
      render: (p) =>
        p.measurement?.latestResult?.measuredValue != null ? (
          <span className="cell-strong">
            {`${p.measurement.latestResult.measuredValue} ${p.measurement.latestResult.unit ?? ''}`.trim()}
          </span>
        ) : (
          <span className="cell-muted">not measured</span>
        ),
    },
    {
      key: 'difference',
      header: 'Observed difference',
      render: (p) => {
        const observed = p.measurement?.observed;
        if (!observed) return <span className="cell-muted">—</span>;
        if (!observed.comparable)
          return <span className="cell-muted" title={observed.reason ?? ''}>not comparable</span>;
        const unit = observed.declared?.unit ?? '';
        return (
          <span>
            {observed.difference}
            {unit ? ` ${unit}` : ''}
            {observed.percentDifference != null ? (
              <span className="cell-muted"> ({observed.percentDifference}%)</span>
            ) : null}
          </span>
        );
      },
    },
    {
      key: 'evidence',
      header: 'Evidence',
      render: (p) => {
        const result = p.measurement?.latestResult;
        if (!result) return <span className="cell-muted">—</span>;
        return (
          <span className="stack" style={{ gap: 2, fontSize: 'var(--fs-xs)' }}>
            <span>
              {result.instrumentId ? `instrument ${result.instrumentId}` : 'instrument not recorded'}
              {result.instrumentId
                ? result.instrumentVerificationStatus
                  ? ` · ${result.instrumentVerificationStatus}`
                  : ' · verification status NOT recorded'
                : ''}
            </span>
            <span className="cell-muted">
              {result.recordedBy.slice(0, 8)}… ·{' '}
              {formatDateTime(result.recordedAt)}
            </span>
            <EvaluationBadge evaluation={p.measurement?.evaluation ?? null} />
          </span>
        );
      },
    },
    {
      key: 'status',
      header: 'Status',
      render: (p) => {
        const meta = PACKAGE_STATUS_META[p.status] ?? PACKAGE_STATUS_META.NOT_SAMPLED;
        return <Badge tone={meta.tone} outline>{meta.label}</Badge>;
      },
    },
    {
      key: 'action',
      header: '',
      render: (p) =>
        canWrite && p.status === 'PENDING' ? (
          <button
            type="button"
            className="btn btn--sm btn--primary"
            onClick={() => openMeasurement(p)}
          >
            <Icon name="scale" size={14} />
            Measure
          </button>
        ) : null,
    },
  ];

  return (
    <Drawer title={lot ? `Lot ${lot.label}` : 'Lot'} subtitle={lot ? `${lot.lotSize} packages · declared ${lot.declaredValue}` : undefined} onClose={onClose} wide>
      {lotAsync.status === 'error' && lotAsync.error && (
        <div className="demo-note demo-note--error" style={{ display: 'flex', gap: 8 }} role="alert">
          <Icon name="alert" size={15} />
          <span>Could not load the lot: {lotAsync.error.message}</span>
        </div>
      )}
      {lotAsync.status === 'loading' && !lot && <p className="cell-muted">Loading the lot…</p>}
      {lot && (
        <div className="stack">
          <div className="row row--wrap" style={{ gap: 6 }}>
            <LotStatusBadge status={lot.status} />
            <Badge tone="neutral" outline>{lot.progress.summary}</Badge>
            {lot.progress.remaining > 0 && (
              <Badge tone="warning" outline>
                {lot.progress.remaining} measurement{lot.progress.remaining > 1 ? 's' : ''} remaining
              </Badge>
            )}
          </div>

          <div className="detail-list">
            <div className="detail-list__row">
              <span className="detail-list__key">Declared quantity (immutable)</span>
              <span className="detail-list__val">{lot.declaredValue}</span>
            </div>
            {lot.location && (
              <div className="detail-list__row">
                <span className="detail-list__key">Location</span>
                <span className="detail-list__val">{lot.location}</span>
              </div>
            )}
            <div className="detail-list__row">
              <span className="detail-list__key">Created</span>
              <span className="detail-list__val">
                {lot.createdBy.slice(0, 8)}… · {formatDateTime(lot.createdAt)}
              </span>
            </div>
            {lot.notes && (
              <div className="detail-list__row">
                <span className="detail-list__key">Notes</span>
                <span className="detail-list__val">{lot.notes}</span>
              </div>
            )}
          </div>

          <SamplingSection lot={lot} canWrite={canWrite} busy={false} onDone={reload} />

          <section className="stack stack--sm">
            <h3 className="cell-strong" style={{ margin: 0, fontSize: 'var(--fs-sm)' }}>
              Packages — real records only
            </h3>
            {taskError && (
              <div className="demo-note demo-note--error" style={{ display: 'flex', gap: 8 }} role="alert">
                <Icon name="alert" size={15} />
                <span>{taskError}</span>
              </div>
            )}
            <DataTable
              columns={columns}
              rows={lot.packages}
              getRowId={(p) => p.id}
              ariaLabel={`Packages of lot ${lot.label}`}
            />
          </section>

          <section className="stack stack--sm">
            <h3 className="cell-strong" style={{ margin: 0, fontSize: 'var(--fs-sm)' }}>
              Observed statistics
            </h3>
            <div className="detail-list">
              <div className="detail-list__row">
                <span className="detail-list__key">Sampled / measured</span>
                <span className="detail-list__val">
                  {lot.statistics.sampled} sampled · {lot.statistics.measured} measured
                </span>
              </div>
              <div className="detail-list__row">
                <span className="detail-list__key">Average measured value</span>
                <span className="detail-list__val">
                  {lot.statistics.averageMeasured ?? 'Not computed'}
                  {lot.statistics.averageNote ? (
                    <span className="cell-muted"> — {lot.statistics.averageNote}</span>
                  ) : null}
                </span>
              </div>
              <div className="detail-list__row">
                <span className="detail-list__key">Observed deficiencies</span>
                <span className="detail-list__val">{lot.statistics.observedDeficiencies}</span>
              </div>
              <div className="detail-list__row">
                <span className="detail-list__key">Exceeding configured permissible error</span>
                <span className="detail-list__val">{lot.statistics.exceedingThreshold}</span>
              </div>
              <div className="detail-list__row">
                <span className="detail-list__key">Regulatory evaluations recorded</span>
                <span className="detail-list__val">{lot.statistics.evaluated}</span>
              </div>
            </div>
            <p className="cell-muted" style={{ margin: 0, fontSize: 'var(--fs-xs)' }}>
              {lot.statistics.note}
            </p>
          </section>

          <DecisionSection lot={lot} canWrite={canWrite} busy={false} onDone={reload} />

          <p className="cell-muted" style={{ margin: 0, fontSize: 'var(--fs-xs)' }}>
            {lot.boundaryNote}
          </p>
        </div>
      )}

      {measureTask && lot && measurePkg && (
        <VerificationPanel
          task={measureTask}
          row={packageRow(lot, measurePkg)}
          planner={planner}
          onClose={() => {
            setOpenMeasureTaskId(null);
            reload();
          }}
        />
      )}
    </Drawer>
  );
}

function CreateLotForm({
  inspectionId,
  onCreated,
  onCancel,
}: {
  inspectionId: string;
  onCreated: (lotId: string) => void;
  onCancel: () => void;
}) {
  const [label, setLabel] = useState('');
  const [declaredValue, setDeclaredValue] = useState('');
  const [lotSize, setLotSize] = useState('');
  const [location, setLocation] = useState('');
  const [notes, setNotes] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setError(null);
    const size = Number.parseInt(lotSize, 10);
    if (!label.trim()) return setError('A lot label is mandatory.');
    if (!declaredValue.trim()) return setError('The declared quantity is mandatory (e.g. 500 g).');
    if (!Number.isFinite(size) || size < 1) return setError('The lot size must be a whole number of at least 1.');
    setBusy(true);
    try {
      const lot = await api.createLot(inspectionId, {
        label: label.trim(),
        declaredValue: declaredValue.trim(),
        lotSize: size,
        location: location.trim() || null,
        notes: notes.trim() || null,
      });
      onCreated(lot.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'The lot could not be created');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="stack stack--sm" style={{ borderTop: '1px solid var(--border)', paddingTop: 'var(--space-3)' }}>
      <div className="grid grid--2">
        <label className="field">
          <span className="field__label">Lot label (mandatory)</span>
          <input
            className="input"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder="e.g. LOT-2026-0007"
            disabled={busy}
          />
        </label>
        <label className="field">
          <span className="field__label">Declared quantity (mandatory, immutable)</span>
          <input
            className="input"
            value={declaredValue}
            onChange={(e) => setDeclaredValue(e.target.value)}
            placeholder="e.g. 500 g"
            disabled={busy}
          />
        </label>
        <label className="field">
          <span className="field__label">Lot size — number of packages (mandatory)</span>
          <input
            className="input"
            type="number"
            min="1"
            step="1"
            inputMode="numeric"
            value={lotSize}
            onChange={(e) => setLotSize(e.target.value)}
            placeholder="e.g. 10"
            disabled={busy}
          />
        </label>
        <label className="field">
          <span className="field__label">Location (optional)</span>
          <input
            className="input"
            value={location}
            onChange={(e) => setLocation(e.target.value)}
            placeholder="e.g. Rack B, godown 2"
            disabled={busy}
          />
        </label>
      </div>
      <label className="field" style={{ margin: 0 }}>
        <span className="field__label">Notes (optional)</span>
        <textarea
          className="textarea"
          rows={2}
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder="Anything the audit trail should record about this lot"
          disabled={busy}
        />
      </label>
      {error && (
        <div className="demo-note demo-note--error" style={{ display: 'flex', gap: 8 }} role="alert">
          <Icon name="alert" size={15} />
          <span>{error}</span>
        </div>
      )}
      <div className="row" style={{ gap: 'var(--space-2)' }}>
        <button type="button" className="btn btn--primary btn--sm" disabled={busy} onClick={() => void submit()}>
          {busy ? 'Creating…' : 'Create lot + package records'}
        </button>
        <button type="button" className="btn btn--ghost btn--sm" disabled={busy} onClick={onCancel}>
          Cancel
        </button>
      </div>
      <p className="cell-muted" style={{ margin: 0, fontSize: 'var(--fs-xs)' }}>
        The declared quantity is stored verbatim and can never be overwritten — corrections happen
        through measurements, not edits. Each package gets a real record; no sample result is
        fabricated.
      </p>
    </div>
  );
}

export function LotIntelligenceCard({
  inspectionId,
  enabled,
  refreshKey,
}: {
  inspectionId: string;
  enabled: boolean;
  /** Bumped by the workspace after any verification write. */
  refreshKey: number;
}) {
  const { user } = useApp();
  const canWrite = WRITE_ROLES.includes(user.role);
  const planner = useEvidencePlan(inspectionId, enabled);
  const [creating, setCreating] = useState(false);
  const [openLotId, setOpenLotId] = useState<string | null>(null);

  const lots = useAsync(
    () => (enabled ? api.listLots(inspectionId) : Promise.resolve(null)),
    [inspectionId, enabled, refreshKey],
  );
  const rows = lots.data?.lots ?? [];
  const inProgress = rows.filter((l) => l.status === 'IN_PROGRESS').length;

  // Mirrors the planner: the lot layer appears only once perception data
  // exists for this inspection.
  if (!enabled) return null;

  return (
    <>
      <Card className="lotcard">
        <CardHead
          eyebrow="Lot intelligence"
          title="Lots under verification"
          subtitle="LOT → PACKAGES → SAMPLE → MEASUREMENTS → EVALUATION → LOT RESULT"
          actions={
            <Badge tone={inProgress > 0 ? 'warning' : 'neutral'} dot>
              {inProgress > 0 ? `${inProgress} in verification` : rows.length > 0 ? 'All decided' : 'No lots'}
            </Badge>
          }
        />
        <CardBody>
          <div className="eplan__banner" role="note">
            <Icon name="package" size={15} />
            <span>
              <strong>A lot is judged on measured packages, never on the AI&rsquo;s reading.</strong>{' '}
              Packages are real records; a sample either follows a configured legal procedure or is
              confirmed by the inspector; statistics are OBSERVED values; and the lot result is
              blocked while sampled packages remain unmeasured.
            </span>
          </div>

          {lots.status === 'error' && lots.error && (
            <div className="demo-note demo-note--error" style={{ display: 'flex', gap: 8 }} role="alert">
              <Icon name="alert" size={15} />
              <span>Could not load lots: {lots.error.message}</span>
            </div>
          )}

          {lots.status === 'loading' ? (
            <p className="cell-muted" style={{ padding: 'var(--space-3) 0' }}>Loading lots…</p>
          ) : rows.length === 0 && !creating ? (
            <p className="cell-muted" style={{ padding: 'var(--space-3) 0' }}>
              No lots recorded for this inspection{canWrite ? ' — create one to verify a batch of packages against its declared quantity' : ''}.
            </p>
          ) : (
            <DataTable
              columns={[
                {
                  key: 'label',
                  header: 'Lot',
                  render: (l) => <span className="cell-strong">{l.label}</span>,
                },
                { key: 'declared', header: 'Declared', render: (l) => l.declaredValue },
                {
                  key: 'size',
                  header: 'Packages',
                  render: (l) => `${l.lotSize}`,
                },
                {
                  key: 'progress',
                  header: 'Progress',
                  render: (l) => (
                    <span>
                      {l.progress.summary}
                      {l.progress.remaining > 0 && (
                        <span className="cell-muted" style={{ fontSize: 'var(--fs-xs)' }}>
                          {' '}
                          · {l.progress.remaining} remaining
                        </span>
                      )}
                    </span>
                  ),
                },
                {
                  key: 'status',
                  header: 'Status',
                  render: (l) => <LotStatusBadge status={l.status} />,
                },
                {
                  key: 'continue',
                  header: '',
                  render: (l) =>
                    l.status === 'IN_PROGRESS' && l.progress.remaining > 0 && l.progress.action ? (
                      <button
                        type="button"
                        className="btn btn--sm btn--subtle"
                        onClick={(e) => {
                          e.stopPropagation();
                          setOpenLotId(l.id);
                        }}
                        title="Resume this lot's verification where it left off"
                      >
                        <Icon name="arrowRight" size={13} />
                        {l.progress.action}
                      </button>
                    ) : null,
                },
              ]}
              rows={rows}
              getRowId={(l) => l.id}
              onRowClick={(l) => setOpenLotId(l.id)}
              ariaLabel="Lots of this inspection"
            />
          )}

          {rows.length > 0 && (
            <p className="cell-muted" style={{ margin: 0, fontSize: 'var(--fs-xs)' }}>
              {lots.data?.boundaryNote}
            </p>
          )}

          {canWrite && (creating ? (
            <CreateLotForm
              inspectionId={inspectionId}
              onCreated={(lotId) => {
                setCreating(false);
                setOpenLotId(lotId);
              }}
              onCancel={() => setCreating(false)}
            />
          ) : (
            <div>
              <button
                type="button"
                className="btn btn--sm btn--subtle"
                onClick={() => setCreating(true)}
              >
                <Icon name="plus" size={14} />
                Create lot
              </button>
            </div>
          ))}

          {!canWrite && (
            <p className="cell-muted" style={{ margin: 0, fontSize: 'var(--fs-xs)' }}>
              Your role can view lots but not create them, draw samples, record measurements or
              submit lot results — those are inspector, supervisor or admin actions.
            </p>
          )}
        </CardBody>
      </Card>

      {openLotId && (
        <LotDetailDrawer
          lotId={openLotId}
          canWrite={canWrite}
          planner={planner}
          refreshKey={refreshKey}
          onClose={() => setOpenLotId(null)}
        />
      )}
    </>
  );
}
