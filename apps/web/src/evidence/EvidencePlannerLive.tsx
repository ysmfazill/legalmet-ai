/**
 * LIVE Evidence Planner (UI-06) — the inspector's core workspace panel.
 *
 * Core question: "AI found a potential issue. What evidence is still
 * required before an inspector can make a defensible decision?"
 *
 * Per finding / declaration the planner shows, from REAL persisted data
 * (server-computed; nothing is invented here):
 *
 *   ✓ EXISTING EVIDENCE  — image, OCR, region, extracted field, evaluation
 *   ⚠ MISSING EVIDENCE   — the open gaps, each with WHY it is needed
 *   REQUIRED ACTION      — the concrete verification task that closes it
 *
 * Honesty rules baked into this component:
 *
 * - A gap is NOT a compliance verdict — evidence completeness says nothing
 *   about the probability of violation.
 * - DECLARED (read from the label) and MEASURED (recorded by an inspector)
 *   are shown side by side and never merged.
 * - "Start verification" is an explicit human action with a mandatory
 *   reason — the engine never auto-creates tasks.
 * - REQUIRED gaps block the final decision while open (the gate lives in the
 *   backend); RECOMMENDED gaps are advice and never block.
 */
import { useEffect, useRef, useState } from 'react';

import type {
  EvidenceItemStatus,
  EvidencePlanItem,
  EvidencePlanVerificationRef,
  VerificationLevel,
  VerificationTask,
} from '@legalmet/types';

import { useApp } from '../app/AppContext';
import { Badge } from '../components/Badge';
import { Card, CardBody, CardHead } from '../components/Card';
import { Icon } from '../components/Icon';
import { formatDateTime } from '../lib/format';
import { EvaluationBadge, ObservedDifferenceLine } from './ObservedEvaluation';
import { VerificationPanel } from './VerificationPanel';
import { useEvidencePlan } from './useEvidencePlan';

const WRITE_ROLES = ['INSPECTOR', 'SUPERVISOR', 'ADMIN'];

const STATUS_META: Record<
  EvidenceItemStatus,
  { label: string; tone: 'positive' | 'warning' | 'critical' | 'neutral' | 'info' }
> = {
  AVAILABLE: { label: 'Evidence available', tone: 'positive' },
  MISSING: { label: 'Evidence missing', tone: 'critical' },
  REQUIRES_VERIFICATION: { label: 'Requires verification', tone: 'warning' },
  VERIFIED: { label: 'Verified', tone: 'positive' },
  REJECTED: { label: 'Rejected by inspector', tone: 'neutral' },
  NOT_APPLICABLE: { label: 'Not applicable', tone: 'neutral' },
};

const KIND_LABELS: Record<string, string> = {
  IMAGE: 'Image',
  OCR: 'OCR text',
  REGION: 'Region',
  FIELD: 'Extracted field',
  EVALUATION: 'Evaluation',
  MEASUREMENT: 'Measurement',
  INSPECTOR_OBSERVATION: 'Inspector observation',
};

function GapIcon({ kind }: { kind: string }) {
  const name = kind === 'MEASUREMENT' ? 'scale' : kind === 'INSPECTOR_OBSERVATION' ? 'eye' : 'camera';
  return <Icon name={name} size={12} />;
}

/** The verification task currently attached to a plan row (live status). */
function rowTask(
  row: EvidencePlanItem,
  tasks: VerificationTask[],
): VerificationTask | null {
  const ref = row.verification as EvidencePlanVerificationRef | null | undefined;
  if (!ref) return null;
  // Prefer the full task (with results) from the task list; fall back to the
  // plan's snapshot ref (still honest — just without the result history).
  return tasks.find((t) => t.id === ref.id) ?? null;
}

function PlanRow({
  row,
  tasks,
  planner,
  canWrite,
  onOpenTask,
}: {
  row: EvidencePlanItem;
  tasks: VerificationTask[];
  planner: ReturnType<typeof useEvidencePlan>;
  canWrite: boolean;
  onOpenTask: (task: VerificationTask) => void;
}) {
  const [starting, setStarting] = useState(false);
  const [reason, setReason] = useState('');
  const [level, setLevel] = useState<VerificationLevel | null>(null);

  const meta = STATUS_META[row.status] ?? STATUS_META.AVAILABLE;
  const task = rowTask(row, tasks);
  const openGaps = row.gaps;
  const gapKinds = new Set(openGaps.map((g) => g.kind));
  const lowConfidence = gapKinds.has('INSPECTOR_OBSERVATION');
  const primaryGap = openGaps[0] ?? null;
  const primaryKind = primaryGap?.kind ?? 'MEASUREMENT';

  const startTask = async () => {
    if (!reason.trim() || reason.trim().length < 3) return;
    const created = await planner.createTask({
      findingId: row.findingId ?? null,
      fieldId: row.fieldId ?? null,
      type: primaryKind === 'MEASUREMENT' ? 'MEASUREMENT' : 'INSPECTOR_OBSERVATION',
      reason: reason.trim(),
      requirementLevel: level ?? (primaryGap?.defaultLevel as VerificationLevel) ?? 'REQUIRED',
    });
    if (created) {
      setStarting(false);
      setReason('');
      setLevel(null);
      onOpenTask(created);
    }
  };

  return (
    <div className="eplan__row">
      <div className="eplan__row-head">
        <span className="eplan__declaration">
          {row.title}
          {row.requirementCode ? (
            <span className="cell-muted" style={{ fontSize: 'var(--fs-xs)' }}>
              {' '}
              · {row.requirementCode}
              {row.versionLabel ? ` · ${row.versionLabel}` : ''}
            </span>
          ) : null}
        </span>
        <Badge tone={meta.tone} dot title={row.summary}>
          {meta.label}
        </Badge>
      </div>

      {row.summary && (
        <p className="cell-muted" style={{ margin: 0, fontSize: 'var(--fs-sm)' }}>
          {row.summary}
        </p>
      )}

      <div className="eplan__values">
        <div className="eplan__value">
          <span className="eplan__value-label">Declared value</span>
          <span className="eplan__value-num">
            {row.declaredValue ?? 'NOT DETECTED'}
            {row.unit ? ` ${row.unit}` : ''}
          </span>
          <span className="eplan__value-src">
            {row.declaredValue != null
              ? `Read from label${
                  row.confidence != null
                    ? ` · ${Math.round(row.confidence * 100)}% reading confidence`
                    : ''
                }`
              : 'No readable declaration'}
            {lowConfidence ? ' · LOW CONFIDENCE — verify before relying on it' : ''}
          </span>
        </div>
        <div className="eplan__arrow" aria-hidden>
          <Icon name="arrowRight" size={14} />
        </div>
        <div className="eplan__value">
          <span className="eplan__value-label">Measured value</span>
          <span
            className={`eplan__value-num ${
              row.verification?.latestResult?.measuredValue != null ? '' : 'eplan__value-num--muted'
            }`}
          >
            {row.verification?.latestResult?.measuredValue != null
              ? `${row.verification.latestResult.measuredValue} ${row.verification.latestResult.unit ?? ''}`.trim()
              : 'NOT VERIFIED'}
          </span>
          <span className="eplan__value-src">
            {row.verification?.latestResult?.measuredValue != null
              ? `Inspector reading · ${formatDateTime(row.verification.latestResult.recordedAt)}`
              : 'Only an inspector can record a measurement — the system never guesses'}
          </span>
          {/* Observed difference (arithmetic) + frozen evaluation (rule
              result) — server-computed, never a compliance verdict. */}
          <ObservedDifferenceLine observed={row.verification?.observed ?? null} />
        </div>
      </div>

      {row.verification?.latestResult?.measuredValue != null && (
        <div className="row row--wrap" style={{ gap: 6 }}>
          <EvaluationBadge evaluation={row.verification?.evaluation ?? null} />
        </div>
      )}

      {/* Existing evidence — every ✓ is a real persisted record. */}
      <div className="row row--wrap" style={{ gap: 6 }}>
        {row.evidence.map((e) => (
          <span
            key={e.kind}
            className="chip"
            title={e.detail ?? e.label}
            style={{ opacity: e.status === 'MISSING' ? 0.65 : 1 }}
          >
            {e.status === 'AVAILABLE' || e.status === 'VERIFIED' ? (
              <Icon name="check" size={12} />
            ) : (
              <Icon name="close" size={12} />
            )}
            {KIND_LABELS[e.kind] ?? e.kind}
          </span>
        ))}
      </div>

      {/* Open gaps + the action that closes them. */}
      {openGaps.length > 0 && (
        <div className="eplan__gap">
          <span className="eplan__gap-label">Required next step</span>
          <ul style={{ margin: 0, padding: 0, listStyle: 'none' }} className="stack stack--sm">
            {openGaps.map((g) => (
              <li key={g.kind} className="row row--wrap" style={{ gap: 6 }}>
                <span className="chip">
                  <GapIcon kind={g.kind} />
                  {KIND_LABELS[g.kind] ?? g.kind}
                </span>
                <Badge tone={g.required ? 'critical' : 'info'} outline>
                  {g.required ? 'REQUIRED' : 'RECOMMENDED'}
                </Badge>
                {g.taskId ? (
                  <span className="cell-muted" style={{ fontSize: 'var(--fs-xs)' }}>
                    task {g.taskId.slice(0, 8)}… is {g.taskStatus}
                  </span>
                ) : (
                  <span className="cell-muted" style={{ fontSize: 'var(--fs-xs)' }}>
                    no task created yet
                  </span>
                )}
              </li>
            ))}
          </ul>
          <p className="cell-muted" style={{ margin: 0, fontSize: 'var(--fs-xs)' }}>
            {primaryGap?.reason}
          </p>

          {starting ? (
            <div className="stack stack--sm">
              <label className="field" style={{ margin: 0 }}>
                <span className="field__label">
                  Reason (mandatory — audited with the task)
                </span>
                <textarea
                  className="textarea"
                  rows={2}
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  placeholder={
                    primaryKind === 'MEASUREMENT'
                      ? 'e.g. Verify the physical net quantity with a calibrated scale'
                      : 'e.g. Re-read the low-confidence marking in person'
                  }
                  disabled={planner.busy}
                />
              </label>
              <label className="field" style={{ margin: 0 }}>
                <span className="field__label">Requirement level</span>
                <select
                  className="input"
                  value={level ?? (primaryGap?.defaultLevel as VerificationLevel) ?? 'REQUIRED'}
                  onChange={(e) => setLevel(e.target.value as VerificationLevel)}
                  disabled={planner.busy}
                >
                  <option value="REQUIRED">REQUIRED — blocks the final decision while open</option>
                  <option value="RECOMMENDED">RECOMMENDED — advisory, never blocks</option>
                </select>
              </label>
              <div className="row" style={{ gap: 'var(--space-2)' }}>
                <button
                  type="button"
                  className="btn btn--primary btn--sm"
                  disabled={planner.busy || reason.trim().length < 3}
                  onClick={() => void startTask()}
                >
                  {planner.busy ? 'Creating…' : 'Create verification task'}
                </button>
                <button
                  type="button"
                  className="btn btn--ghost btn--sm"
                  disabled={planner.busy}
                  onClick={() => setStarting(false)}
                >
                  Back
                </button>
              </div>
            </div>
          ) : (
            <div className="row row--wrap" style={{ gap: 6 }}>
              {canWrite && !task && (
                <button
                  type="button"
                  className="btn btn--sm btn--primary"
                  onClick={() => setStarting(true)}
                  title={`Begin collecting the ${(KIND_LABELS[primaryKind] ?? 'verification').toLowerCase()} evidence as the inspector`}
                >
                  <GapIcon kind={primaryKind} />
                  Start {(KIND_LABELS[primaryKind] ?? 'verification').toLowerCase()}
                </button>
              )}
              {task && (task.status === 'PENDING' || task.status === 'IN_PROGRESS') && canWrite && (
                <button
                  type="button"
                  className="btn btn--sm btn--primary"
                  onClick={() => onOpenTask(task)}
                >
                  <GapIcon kind={task.taskType} />
                  Record {task.taskType === 'MEASUREMENT' ? 'measurement' : 'observation'}
                </button>
              )}
              {task && task.status === 'COMPLETED' && (
                <button
                  type="button"
                  className="btn btn--sm btn--subtle"
                  onClick={() => onOpenTask(task)}
                >
                  <Icon name="evidence" size={14} />
                  View recorded evidence
                </button>
              )}
            </div>
          )}
        </div>
      )}

      {/* No open gaps — show the recorded verification evidence (if any). */}
      {openGaps.length === 0 && task && task.status === 'COMPLETED' && (
        <div className="row row--wrap" style={{ gap: 6 }}>
          <button
            type="button"
            className="btn btn--sm btn--subtle"
            onClick={() => onOpenTask(task)}
          >
            <Icon name="evidence" size={14} />
            View recorded verification
          </button>
        </div>
      )}
    </div>
  );
}

export function EvidencePlannerLive({
  inspectionId,
  enabled,
  onChanged,
}: {
  inspectionId: string;
  /** Only meaningful once perception/evaluation data exists. */
  enabled: boolean;
  /** Notified after any verification write (e.g. to refresh the decision gate). */
  onChanged?: () => void;
}) {
  const { user } = useApp();
  const canWrite = WRITE_ROLES.includes(user.role);
  const planner = useEvidencePlan(inspectionId, enabled);
  const [openTaskId, setOpenTaskId] = useState<string | null>(null);

  const plan = planner.plan;
  const openTask = openTaskId ? (planner.tasks.find((t) => t.id === openTaskId) ?? null) : null;
  const openTaskRow =
    openTask && plan
      ? (plan.items.find(
          (i) =>
            (openTask.findingId != null && i.findingId === openTask.findingId) ||
            (openTask.findingId == null &&
              openTask.extractedFieldId != null &&
              i.fieldId === openTask.extractedFieldId),
        ) ?? null)
      : null;

  // Propagate every plan reload upward — the decision gate (FinalDecisionCard)
  // depends on the verification-task state. The tasks array identity changes
  // only when the hook reloads (after a write or an explicit reload).
  const onChangedRef = useRef(onChanged);
  onChangedRef.current = onChanged;
  useEffect(() => {
    if (!enabled || planner.loading) return;
    onChangedRef.current?.();
  }, [planner.tasks, enabled, planner.loading]);

  if (!enabled) return null;
  if (planner.loading) {
    return (
      <Card className="eplan">
        <CardHead
          eyebrow="Evidence planner"
          title="Evidence completeness"
          subtitle="What the system knows, what is still unverified, and what closes the gap"
        />
        <CardBody>
          <p className="cell-muted" style={{ padding: 'var(--space-3) 0' }}>
            Loading the evidence plan…
          </p>
        </CardBody>
      </Card>
    );
  }
  if (planner.error && !plan) {
    return (
      <Card className="eplan">
        <CardHead eyebrow="Evidence planner" title="Evidence completeness" />
        <CardBody>
          <div className="demo-note demo-note--error" style={{ display: 'flex', gap: 8 }} role="alert">
            <Icon name="alert" size={15} />
            <span>Could not load the evidence plan: {planner.error}</span>
          </div>
        </CardBody>
      </Card>
    );
  }

  const counts = plan?.counts;
  const incomplete = counts?.requiringVerification ?? 0;
  const openRequired = counts?.openRequiredTasks ?? 0;

  return (
    <>
      <Card className="eplan">
        <CardHead
          eyebrow="Evidence planner"
          title="Evidence completeness"
          subtitle="What the system knows, what is still unverified, and what closes the gap"
          actions={
            <Badge tone={incomplete > 0 || openRequired > 0 ? 'warning' : 'positive'} dot>
              {openRequired > 0
                ? `${openRequired} required task${openRequired > 1 ? 's' : ''} open`
                : incomplete > 0
                  ? `${incomplete} to verify`
                  : 'Complete'}
            </Badge>
          }
        />
        <CardBody>
          <div className="eplan__banner" role="note">
            <Icon name="shield" size={15} />
            <span>
              <strong>AI reads declarations; it cannot measure contents.</strong> A measurement is
              recorded manually by an authorised inspector from an appropriate instrument — the
              system never converts a declared-vs-measured difference into a violation. A gap below
              means the evidence is incomplete — it is NOT a compliance verdict.
            </span>
          </div>

          {planner.error && (
            <div className="demo-note demo-note--error" style={{ display: 'flex', gap: 8 }} role="alert">
              <Icon name="alert" size={15} />
              <span>{planner.error}</span>
            </div>
          )}

          {!plan || plan.items.length === 0 ? (
            <p className="cell-muted" style={{ padding: 'var(--space-3) 0' }}>
              No evidence plan yet — run perception (and an evaluation) to extract declarations and
              findings first.
            </p>
          ) : (
            <div className="stack">
              {plan.items.map((row) => (
                <PlanRow
                  key={row.findingId ?? row.fieldId ?? row.title}
                  row={row}
                  tasks={planner.tasks}
                  planner={planner}
                  canWrite={canWrite}
                  onOpenTask={(task) => {
                    setOpenTaskId(task.id);
                    onChanged?.();
                  }}
                />
              ))}
            </div>
          )}

          {!canWrite && plan && plan.items.some((i) => i.gaps.length > 0) && (
            <p className="cell-muted" style={{ margin: 0, fontSize: 'var(--fs-xs)' }}>
              Your role can view the plan but not create verification tasks — only an inspector,
              supervisor or admin may verify evidence.
            </p>
          )}
        </CardBody>
      </Card>

      {openTask && (
        <VerificationPanel
          task={openTask}
          row={openTaskRow}
          planner={planner}
          onClose={() => {
            setOpenTaskId(null);
            onChanged?.();
          }}
        />
      )}
    </>
  );
}
