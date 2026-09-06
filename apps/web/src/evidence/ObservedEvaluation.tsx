/**
 * Observed difference + frozen regulatory evaluation display (UI-07).
 *
 * Two honesty contracts, rendered identically wherever a measurement appears
 * (verification panel, evidence planner, measurement history, lot table):
 *
 * - The DECLARED-vs-MEASURED difference is labelled <strong>Observed
 *   difference</strong> — pure arithmetic on normalized values. It is never
 *   called a legal deficiency.
 * - The regulatory evaluation is a FROZEN rule result (rule code + version
 *   recorded at evaluation time). WITHIN/EXCEEDS the configured permissible
 *   error is a rule outcome, never a violation — the inspector decides.
 *   UNAVAILABLE means "not configured — inspector review required", never a
 *   guessed tolerance.
 */
import type { MeasurementEvaluation, ObservedDifference } from '@legalmet/types';

import { Badge } from '../components/Badge';
import { Icon } from '../components/Icon';
import { formatDateTime } from '../lib/format';

/** The tolerance block the backend freezes into `evaluation.detail`. */
interface ToleranceBlock {
  type?: string;
  value?: string;
  limitInDeclaredUnit?: string;
  observedMagnitude?: string;
}

function readTolerance(evaluation: MeasurementEvaluation): ToleranceBlock | null {
  const raw = evaluation.detail?.tolerance;
  return raw && typeof raw === 'object' ? (raw as ToleranceBlock) : null;
}

function readString(detail: Record<string, unknown> | undefined, key: string): string | null {
  const value = detail?.[key];
  return typeof value === 'string' ? value : null;
}

/** Compact badge — the evaluation outcome for dense tables and plan rows. */
export function EvaluationBadge({ evaluation }: { evaluation?: MeasurementEvaluation | null }) {
  if (!evaluation) return null;
  if (evaluation.status === 'EVALUATED') {
    const exceeds = evaluation.outcome === 'EXCEEDS_TOLERANCE';
    return (
      <Badge tone={exceeds ? 'warning' : 'positive'} outline title={evaluation.ruleCode ?? undefined}>
        {exceeds ? 'Exceeds permissible error' : 'Within permissible error'}
        {evaluation.ruleCode ? ` · ${evaluation.ruleCode}` : ''}
      </Badge>
    );
  }
  return (
    <Badge tone="neutral" outline title={readString(evaluation.detail, 'reason') ?? undefined}>
      Evaluation unavailable — inspector review
    </Badge>
  );
}

/** One-line observed difference (no evaluation content) for dense layouts. */
export function ObservedDifferenceLine({ observed }: { observed?: ObservedDifference | null }) {
  if (!observed) return null;
  if (!observed.comparable) return null;
  const unit = observed.declared?.unit ?? '';
  return (
    <span className="cell-muted" style={{ fontSize: 'var(--fs-xs)' }}>
      Observed difference {observed.difference ?? '—'}
      {unit ? ` ${unit}` : ''}
      {observed.percentDifference != null ? ` (${observed.percentDifference}%)` : ''}
    </span>
  );
}

/** The full observed-difference block (panel/drawer usage). */
export function ObservedDifferenceNote({ observed }: { observed?: ObservedDifference | null }) {
  if (!observed) return null;
  if (!observed.comparable) {
    return (
      <div className="demo-note" style={{ display: 'flex', gap: 8 }} role="note">
        <Icon name="info" size={15} />
        <span>
          <strong>Observed difference — not computed.</strong>{' '}
          {observed.reason ??
            'The declared and measured values cannot be compared deterministically; no difference is calculated and no conclusion is drawn.'}
        </span>
      </div>
    );
  }
  const unit = observed.declared?.unit ?? '';
  return (
    <div className="demo-note" style={{ display: 'flex', gap: 8 }} role="note">
      <Icon name="scale" size={15} />
      <span>
        <strong>Observed difference:</strong> {observed.difference}
        {unit ? ` ${unit}` : ''} ({observed.percentDifference}% of the declaration) — computed on
        normalized values ({observed.declared?.normalized ?? ''} declared vs{' '}
        {observed.measured?.normalized ?? ''} measured).{' '}
        {observed.note ??
          'Observed difference — arithmetic only; this is NOT a legal deficiency.'}
      </span>
    </div>
  );
}

/** The full frozen-evaluation block (panel/drawer/history usage). */
export function EvaluationNote({ evaluation }: { evaluation?: MeasurementEvaluation | null }) {
  if (!evaluation) return null;
  const detail = evaluation.detail;

  if (evaluation.status !== 'EVALUATED') {
    const reason =
      readString(detail, 'reason') ??
      'Applicable permissible error/procedure is not configured.';
    return (
      <div className="demo-note" style={{ display: 'flex', gap: 8 }} role="note">
        <Icon name="alert" size={15} />
        <span>
          <strong>Regulatory evaluation unavailable.</strong> {reason}{' '}
          <strong>Inspector review required.</strong>
        </span>
      </div>
    );
  }

  const tolerance = readTolerance(evaluation);
  const within = evaluation.outcome === 'WITHIN_TOLERANCE';
  return (
    <div
      className="demo-note"
      style={{
        display: 'flex',
        gap: 8,
        borderColor: within ? 'var(--tone-positive)' : 'var(--tone-warning)',
      }}
      role="note"
    >
      <Icon name="shield" size={15} />
      <span>
        <strong>Regulatory evaluation ({within ? 'within' : 'exceeds'} the configured permissible error):</strong>{' '}
        {evaluation.ruleCode ? `rule ${evaluation.ruleCode}` : 'configured rule'} permits{' '}
        {tolerance?.type === 'PERCENT'
          ? `${tolerance?.value ?? '—'}% of the declared quantity (limit ${tolerance?.limitInDeclaredUnit ?? '—'})`
          : `an absolute difference of ${tolerance?.value ?? '—'}; observed magnitude ${tolerance?.observedMagnitude ?? '—'}`}
        . Evaluated {formatDateTime(evaluation.evaluatedAt)} against the rule version in force at
        record time — later rule changes never rewrite this result.{' '}
        {readString(detail, 'note') ??
          'This is a rule result, not a violation — the inspector weighs it in the final decision.'}
      </span>
    </div>
  );
}
