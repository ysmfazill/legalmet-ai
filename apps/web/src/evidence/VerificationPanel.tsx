/**
 * Verification panel (UI-06).
 *
 * Opens when an inspector acts on a verification task from the Evidence
 * Planner. Shows the task, its append-only result history, and the form for
 * recording ONE outcome.
 *
 * HONESTY CONTRACTS, all enforced visually here and by the backend:
 *
 * - MEASUREMENT entry is labelled <strong>MANUAL measurement entry</strong> —
 *   this application is NOT connected to a physical scale. The inspector
 *   reads an appropriate Legal Metrology instrument and types the reading.
 * - The DECLARED value (read from the label) and the MEASURED value (typed
 *   here) are shown side by side and stored separately. The panel never
 *   computes a difference, never says "within tolerance" and never calls the
 *   package compliant/non-compliant — the inspector weighs the evidence and
 *   makes the final decision.
 * - Instrument verification status is optional: leaving it blank records
 *   "Verification status not recorded" — never "Verified".
 * - Results are append-only: once a task is COMPLETED no further result can
 *   be added (a re-verification is a NEW task).
 */
import { useEffect, useState } from 'react';

import type {
  EvidencePlanItem,
  VerificationResultRequest,
  VerificationTask,
  VerificationTaskType,
} from '@legalmet/types';

import { Badge } from '../components/Badge';
import { Drawer } from '../components/Drawer';
import { Icon } from '../components/Icon';
import { formatDateTime } from '../lib/format';
import { EvaluationNote, ObservedDifferenceNote } from './ObservedEvaluation';
import type { EvidencePlanState } from './useEvidencePlan';

const UNIT_OPTIONS = ['mg', 'g', 'kg', 'ml', 'L'];

function TaskStatusBadge({ status }: { status: VerificationTask['status'] }) {
  const tone =
    status === 'COMPLETED'
      ? 'positive'
      : status === 'CANCELLED'
        ? 'neutral'
        : status === 'IN_PROGRESS'
          ? 'info'
          : 'warning';
  return (
    <Badge tone={tone} dot>
      {status.replace('_', ' ')}
    </Badge>
  );
}

export function VerificationPanel({
  task,
  row,
  planner,
  onClose,
}: {
  task: VerificationTask;
  /** The plan row the task is anchored to (declared value display). */
  row: EvidencePlanItem | null;
  planner: EvidencePlanState;
  onClose: () => void;
}) {
  const isMeasurement = task.taskType === ('MEASUREMENT' as VerificationTaskType);
  const open = task.status === 'PENDING' || task.status === 'IN_PROGRESS';
  const canWrite = open && !planner.busy;

  const [measuredValue, setMeasuredValue] = useState('');
  const [unit, setUnit] = useState(row?.unit ?? '');
  const [observation, setObservation] = useState('');
  const [instrumentId, setInstrumentId] = useState('');
  const [instrumentStatus, setInstrumentStatus] = useState('');
  const [notes, setNotes] = useState('');
  const [formError, setFormError] = useState<string | null>(null);
  const [cancelling, setCancelling] = useState(false);
  const [cancelReason, setCancelReason] = useState('');

  // Reset the form when a different task opens in the same panel instance.
  useEffect(() => {
    setMeasuredValue('');
    setUnit(row?.unit ?? '');
    setObservation('');
    setInstrumentId('');
    setInstrumentStatus('');
    setNotes('');
    setFormError(null);
    setCancelling(false);
    setCancelReason('');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [task.id]);

  const submit = async () => {
    setFormError(null);
    const body: VerificationResultRequest = {};
    if (isMeasurement) {
      const value = Number.parseFloat(measuredValue);
      if (!Number.isFinite(value) || value <= 0) {
        setFormError('Enter the measured value as a positive number (e.g. 492).');
        return;
      }
      if (!unit.trim()) {
        setFormError('A unit is mandatory (e.g. mg, g, kg, ml, L).');
        return;
      }
      body.measuredValue = value;
      body.unit = unit.trim();
    } else {
      if (!observation.trim()) {
        setFormError('An observation is mandatory for an inspector observation task.');
        return;
      }
      body.observation = observation.trim();
    }
    if (instrumentId.trim()) body.instrumentId = instrumentId.trim();
    if (instrumentStatus.trim()) body.instrumentVerificationStatus = instrumentStatus.trim();
    if (notes.trim()) body.notes = notes.trim();

    const updated = await planner.recordResult(task.id, body);
    if (updated) onClose();
  };

  const cancel = async () => {
    if (!cancelReason.trim() || cancelReason.trim().length < 3) {
      setFormError('A cancellation reason is mandatory — the audit trail must show why.');
      return;
    }
    const updated = await planner.cancelTask(task.id, cancelReason.trim());
    if (updated) onClose();
  };

  const latest = task.results[task.results.length - 1] ?? null;

  return (
    <Drawer
      title={isMeasurement ? 'Measurement verification' : 'Inspector observation'}
      subtitle={row ? row.title : 'Verification task'}
      onClose={onClose}
    >
      <div className="stack">
        <div className="row row--wrap" style={{ gap: 6 }}>
          <TaskStatusBadge status={task.status} />
          <Badge tone={task.requirementLevel === 'REQUIRED' ? 'critical' : 'info'} outline>
            {task.requirementLevel}
          </Badge>
          {isMeasurement && <Badge tone="neutral" outline>Manual measurement entry</Badge>}
        </div>

        <div className="detail-list">
          <div className="detail-list__row">
            <span className="detail-list__key">Reason</span>
            <span className="detail-list__val">{task.reason}</span>
          </div>
          <div className="detail-list__row">
            <span className="detail-list__key">Created</span>
            <span className="detail-list__val">
              {task.createdByName ?? task.createdBy.slice(0, 8) + '…'} ·{' '}
              {formatDateTime(task.createdAt)}
            </span>
          </div>
          {task.startedAt && (
            <div className="detail-list__row">
              <span className="detail-list__key">Started</span>
              <span className="detail-list__val">{formatDateTime(task.startedAt)}</span>
            </div>
          )}
          {task.completedAt && (
            <div className="detail-list__row">
              <span className="detail-list__key">Completed</span>
              <span className="detail-list__val">{formatDateTime(task.completedAt)}</span>
            </div>
          )}
          {task.cancelledReason && (
            <div className="detail-list__row">
              <span className="detail-list__key">Cancellation reason</span>
              <span className="detail-list__val">{task.cancelledReason}</span>
            </div>
          )}
        </div>

        {isMeasurement && (
          <div className="demo-note demo-note--block" style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}>
            <Icon name="scale" size={15} />
            <span>
              <strong>Manual measurement entry.</strong> This application is not connected to a
              physical scale or any measuring instrument. You read an appropriate Legal Metrology
              instrument yourself and record the reading here. It is stored as{' '}
              <strong>measured evidence</strong> — separate from the declared value, which is never
              modified here. A permissible-error evaluation, when a rule is configured, is shown
              below once recorded; the final judgement remains the inspector&rsquo;s.
            </span>
          </div>
        )}

        {/* DECLARED vs MEASURED — side by side, never merged, never judged. */}
        {isMeasurement && row && (
          <div className="eplan__values">
            <div className="eplan__value">
              <span className="eplan__value-label">Declared value</span>
              <span className="eplan__value-num">
                {row.declaredValue ?? 'NOT DETECTED'}
                {row.unit ? ` ${row.unit}` : ''}
              </span>
              <span className="eplan__value-src">Read from the label — never modified here</span>
            </div>
            <div className="eplan__arrow" aria-hidden>
              <Icon name="arrowRight" size={14} />
            </div>
            <div className="eplan__value">
              <span className="eplan__value-label">Measured value</span>
              <span
                className={`eplan__value-num ${latest?.measuredValue != null ? '' : 'eplan__value-num--muted'}`}
              >
                {latest?.measuredValue != null
                  ? `${latest.measuredValue} ${latest.unit ?? ''}`.trim()
                  : 'NOT RECORDED'}
              </span>
              <span className="eplan__value-src">
                {latest?.measuredValue != null
                  ? 'Recorded by the inspector from an instrument reading'
                  : 'No instrument reading recorded yet'}
              </span>
            </div>
          </div>
        )}
        {/* Observed difference (arithmetic) + the frozen regulatory evaluation
            (rule result) — computed by the backend from real rows only. */}
        {isMeasurement && latest?.measuredValue != null && (
          <>
            <ObservedDifferenceNote observed={row?.verification?.observed ?? null} />
            <EvaluationNote evaluation={row?.verification?.evaluation ?? null} />
          </>
        )}

        {/* Result history — append-only, oldest first. */}
        {task.results.length > 0 && (
          <div>
            <h3 className="cell-strong" style={{ margin: 0, fontSize: 'var(--fs-sm)' }}>
              Recorded results ({task.results.length}
              {task.results.length > 1 ? ' — append-only history' : ''})
            </h3>
            <ul className="stack stack--sm" style={{ marginTop: 'var(--space-2)', padding: 0, listStyle: 'none' }}>
              {task.results.map((r) => (
                <li key={r.id} className="detail-list" style={{ fontSize: 'var(--fs-sm)' }}>
                  <div className="detail-list__row">
                    <span className="detail-list__key">
                      {formatDateTime(r.recordedAt)} · {r.recordedByName ?? r.recordedBy.slice(0, 8) + '…'}
                    </span>
                    <span className="detail-list__val">
                      {r.measuredValue != null
                        ? `${r.measuredValue} ${r.unit ?? ''}`.trim()
                        : r.observation ?? '—'}
                      {r.instrumentId ? ` · instrument ${r.instrumentId}` : ''}
                      {' · '}
                      {r.instrumentVerificationStatus
                        ? `instrument: ${r.instrumentVerificationStatus}`
                        : 'instrument verification status not recorded'}
                    </span>
                  </div>
                  {r.notes && (
                    <div className="detail-list__row">
                      <span className="detail-list__key">Notes</span>
                      <span className="detail-list__val">{r.notes}</span>
                    </div>
                  )}
                </li>
              ))}
            </ul>
          </div>
        )}

        {planner.error && (
          <div className="demo-note demo-note--error" style={{ display: 'flex', gap: 8 }} role="alert">
            <Icon name="alert" size={15} />
            <span>{planner.error}</span>
          </div>
        )}
        {formError && (
          <div className="demo-note demo-note--error" style={{ display: 'flex', gap: 8 }} role="alert">
            <Icon name="alert" size={15} />
            <span>{formError}</span>
          </div>
        )}

        {/* The recording form — only while the task is open. */}
        {open ? (
          <div className="stack stack--sm" style={{ borderTop: '1px solid var(--border)', paddingTop: 'var(--space-3)' }}>
            {isMeasurement ? (
              <div className="grid grid--2">
                <label className="field">
                  <span className="field__label">Measured value (mandatory)</span>
                  <input
                    className="input"
                    type="number"
                    min="0"
                    step="any"
                    inputMode="decimal"
                    value={measuredValue}
                    onChange={(e) => setMeasuredValue(e.target.value)}
                    placeholder="e.g. 492"
                    disabled={!canWrite}
                  />
                </label>
                <label className="field">
                  <span className="field__label">Unit (mandatory)</span>
                  <input
                    className="input"
                    list="verification-units"
                    value={unit}
                    onChange={(e) => setUnit(e.target.value)}
                    placeholder="mg, g, kg, ml, L…"
                    disabled={!canWrite}
                  />
                  <datalist id="verification-units">
                    {UNIT_OPTIONS.map((u) => (
                      <option key={u} value={u} />
                    ))}
                  </datalist>
                </label>
                <label className="field">
                  <span className="field__label">Instrument ID (optional)</span>
                  <input
                    className="input"
                    value={instrumentId}
                    onChange={(e) => setInstrumentId(e.target.value)}
                    placeholder="e.g. SCALE-LM-0142"
                    disabled={!canWrite}
                  />
                </label>
                <label className="field">
                  <span className="field__label">
                    Instrument verification status (optional)
                  </span>
                  <input
                    className="input"
                    value={instrumentStatus}
                    onChange={(e) => setInstrumentStatus(e.target.value)}
                    placeholder="Leave blank — recorded as “not recorded”, never “verified”"
                    disabled={!canWrite}
                  />
                </label>
              </div>
            ) : (
              <label className="field">
                <span className="field__label">Observation (mandatory)</span>
                <textarea
                  className="textarea"
                  rows={3}
                  value={observation}
                  onChange={(e) => setObservation(e.target.value)}
                  placeholder="What you verified in person (e.g. re-read the MRP marking)"
                  disabled={!canWrite}
                />
              </label>
            )}
            <label className="field">
              <span className="field__label">Notes (optional, audited)</span>
              <textarea
                className="textarea"
                rows={2}
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="e.g. average of three weighings"
                disabled={!canWrite}
              />
            </label>

            <div className="row row--wrap" style={{ gap: 'var(--space-2)' }}>
              <button
                type="button"
                className="btn btn--primary btn--sm"
                disabled={!canWrite}
                onClick={() => void submit()}
              >
                {planner.busy ? <span className="spinner" aria-hidden /> : <Icon name="check" size={14} />}
                Record result &amp; complete task
              </button>
              {task.status === 'PENDING' && (
                <button
                  type="button"
                  className="btn btn--subtle btn--sm"
                  disabled={!canWrite}
                  onClick={() => void planner.startTask(task.id)}
                  title="PENDING → IN_PROGRESS"
                >
                  Mark in progress
                </button>
              )}
              <button
                type="button"
                className="btn btn--ghost btn--sm"
                disabled={!canWrite}
                onClick={() => setCancelling(true)}
              >
                Cancel task…
              </button>
            </div>

            {cancelling && (
              <div className="demo-note" style={{ borderColor: 'var(--tone-warning)' }}>
                <label className="field" style={{ marginTop: 0 }}>
                  <span className="field__label">Cancellation reason (mandatory, audited)</span>
                  <textarea
                    className="textarea"
                    rows={2}
                    value={cancelReason}
                    onChange={(e) => setCancelReason(e.target.value)}
                    placeholder="Why is this verification being dropped?"
                    disabled={!canWrite}
                  />
                </label>
                <div className="row" style={{ gap: 'var(--space-2)' }}>
                  <button
                    type="button"
                    className="btn btn--subtle btn--sm"
                    disabled={!canWrite}
                    onClick={() => void cancel()}
                  >
                    Confirm cancellation
                  </button>
                  <button
                    type="button"
                    className="btn btn--ghost btn--sm"
                    disabled={!canWrite}
                    onClick={() => setCancelReason('')}
                  >
                    Back
                  </button>
                </div>
              </div>
            )}
          </div>
        ) : (
          <p className="cell-muted" style={{ margin: 0, fontSize: 'var(--fs-sm)' }}>
            This task is {task.status === 'COMPLETED' ? 'completed' : 'cancelled'} — results are
            append-only and the task cannot be reopened. A re-verification is a new task.
          </p>
        )}
      </div>
    </Drawer>
  );
}
