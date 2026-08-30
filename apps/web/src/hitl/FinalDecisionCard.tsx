/**
 * Final-decision card (Prompt 8, Phases 11–14).
 *
 * This is the ONLY place in the product where a legal conclusion is recorded —
 * by an authorised human, never by the engine. The card shows:
 *
 * - review progress (per-state counts, critical unresolved findings)
 * - the DECISION GATE: critical/major findings still PENDING_REVIEW or
 *   ESCALATED block COMPLIANT / NON_COMPLIANT; REQUIRES_FURTHER_REVIEW is
 *   always available as the honest deferral
 * - the current decision + the full supersede history (nothing is deleted)
 *
 * The submit button only REQUESTS the decision — the backend owns the gate.
 */
import { useState } from 'react';

import { INSPECTION_DECISION_META } from '@legalmet/config';
import type { InspectionDecisionType } from '@legalmet/types';

import { DecisionBadge } from '../components/Badge';
import { Card, CardBody, CardHead } from '../components/Card';
import { Icon } from '../components/Icon';
import { formatDateTime } from '../lib/format';
import type { HitlState } from './useHitl';

const CHOICES: InspectionDecisionType[] = [
  'COMPLIANT',
  'NON_COMPLIANT',
  'REQUIRES_FURTHER_REVIEW',
];

/** A reason is mandatory for these decisions — an unexplained conclusion is impossible. */
const REASON_REQUIRED: ReadonlySet<InspectionDecisionType> = new Set([
  'NON_COMPLIANT',
  'REQUIRES_FURTHER_REVIEW',
]);

export function FinalDecisionCard({
  hitl,
  hasFindings,
}: {
  hitl: HitlState;
  /** With no evaluation yet there is nothing to decide on. */
  hasFindings: boolean;
}) {
  const [choice, setChoice] = useState<InspectionDecisionType | null>(null);
  const [reason, setReason] = useState('');
  const [confirming, setConfirming] = useState(false);

  const status = hitl.status;
  const current = status?.decision ?? null;
  const history = hitl.decisions?.history ?? [];
  const blockers = status?.decisionBlockers ?? [];
  const gateOpen = Boolean(status?.decisionAllowed) || blockers.length === 0;

  const reasonRequired = choice !== null && REASON_REQUIRED.has(choice);
  const blockedByGate =
    choice === 'COMPLIANT' || choice === 'NON_COMPLIANT'
      ? blockers.length > 0
      : false;
  const canSubmit =
    choice !== null &&
    hasFindings &&
    !blockedByGate &&
    !hitl.submitting &&
    (!reasonRequired || reason.trim().length >= 3);

  const submit = async () => {
    if (choice === null) return;
    const decision = await hitl.submitDecision({
      decision: choice,
      reason: reason.trim() || null,
    });
    if (decision) {
      setChoice(null);
      setReason('');
      setConfirming(false);
    }
  };

  return (
    <Card>
      <CardHead
        eyebrow="Human decision"
        title="Final inspection decision"
        subtitle="Recorded by an authorised inspector — never by the engine"
        actions={current ? <DecisionBadge decision={current.decision} /> : undefined}
      />
      <CardBody>
        <div className="stack stack--sm">
          <p className="demo-note demo-note--block" style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}>
            <Icon name="shield" size={15} />
            <span>
              AI assists. The inspector decides. This decision is the only legal conclusion the
              system records; the deterministic engine never produces it.
            </span>
          </p>

          {/* Review progress */}
          {status && status.totalFindings > 0 && (
            <div className="detail-list">
              <div className="detail-list__row">
                <span className="detail-list__key">Findings reviewed</span>
                <span className="detail-list__val">
                  {status.totalFindings - status.pendingReview - status.unreviewed}
                  {' of '}
                  {status.totalFindings}
                </span>
              </div>
              <div className="detail-list__row">
                <span className="detail-list__key">Pending review</span>
                <span className="detail-list__val">
                  {status.pendingReview + status.unreviewed}
                </span>
              </div>
              <div className="detail-list__row">
                <span className="detail-list__key">Escalated</span>
                <span className="detail-list__val">{status.escalated}</span>
              </div>
              <div className="detail-list__row">
                <span className="detail-list__key">Critical unresolved</span>
                <span
                  className="detail-list__val"
                  style={{ color: status.criticalUnresolved > 0 ? 'var(--tone-critical)' : undefined }}
                >
                  {status.criticalUnresolved}
                </span>
              </div>
            </div>
          )}

          {/* Decision gate */}
          {blockers.length > 0 && (
            <div className="demo-note" style={{ borderColor: 'var(--tone-warning)', display: 'flex', gap: 8 }}>
              <Icon name="alert" size={15} />
              <span>
                <strong>Decision gate.</strong> {blockers.length} critical/major finding
                {blockers.length > 1 ? 's are' : ' is'} still unresolved. Resolve them (confirm,
                reject or escalate) before recording COMPLIANT / NON_COMPLIANT — or record
                REQUIRES_FURTHER_REVIEW to defer honestly.
              </span>
            </div>
          )}

          {hitl.error && (
            <div className="demo-note" style={{ borderColor: 'var(--tone-critical)', display: 'flex', gap: 8 }}>
              <Icon name="alert" size={15} />
              <span>{hitl.error}</span>
            </div>
          )}

          {/* Current decision + history */}
          {current ? (
            <div className="detail-list">
              <div className="detail-list__row">
                <span className="detail-list__key">Current decision</span>
                <span className="detail-list__val">
                  {INSPECTION_DECISION_META[current.decision].label}
                </span>
              </div>
              <div className="detail-list__row">
                <span className="detail-list__key">Decided by</span>
                <span className="detail-list__val">
                  {current.decidedByName ?? current.decidedBy.slice(0, 8) + '…'} ·{' '}
                  {formatDateTime(current.decidedAt)}
                </span>
              </div>
              {current.reason && (
                <div className="detail-list__row">
                  <span className="detail-list__key">Reason</span>
                  <span className="detail-list__val">{current.reason}</span>
                </div>
              )}
            </div>
          ) : (
            <p style={{ margin: 0, fontSize: 'var(--fs-sm)', color: 'var(--text-muted)' }}>
              No decision recorded yet{hasFindings ? '' : ' — run an evaluation first'}.
            </p>
          )}

          {history.length > 1 && (
            <details>
              <summary style={{ cursor: 'pointer', fontSize: 'var(--fs-sm)', color: 'var(--text-muted)' }}>
                Decision history ({history.length} — previous decisions are never deleted)
              </summary>
              <div className="stack stack--sm" style={{ marginTop: 'var(--space-2)' }}>
                {history.map((d) => (
                  <div key={d.id} className="detail-list__row" style={{ fontSize: 'var(--fs-sm)' }}>
                    <span className="detail-list__key">
                      {formatDateTime(d.decidedAt)}
                    </span>
                    <span className="detail-list__val">
                      {INSPECTION_DECISION_META[d.decision].label}
                      {d.supersedesDecisionId ? ' (supersedes previous)' : ''}
                      {d.reason ? ` — ${d.reason}` : ''}
                    </span>
                  </div>
                ))}
              </div>
            </details>
          )}

          {/* Recording a (new) decision */}
          {choice === null ? (
            <div className="row row--wrap" style={{ gap: 'var(--space-2)' }}>
              {CHOICES.map((c) => (
                <button
                  key={c}
                  type="button"
                  className="btn btn--subtle btn--sm"
                  title={INSPECTION_DECISION_META[c].description}
                  disabled={!hasFindings || !gateOpen}
                  onClick={() => setChoice(c)}
                >
                  Record {INSPECTION_DECISION_META[c].label}
                </button>
              ))}
            </div>
          ) : (
            <div className="stack stack--sm" style={{ borderTop: '1px solid var(--border)', paddingTop: 'var(--space-3)' }}>
              <div className="row row--wrap" style={{ gap: 6 }}>
                <DecisionBadge decision={choice} />
                {current && (
                  <span className="cell-muted" style={{ fontSize: 'var(--fs-sm)' }}>
                    This will supersede the current decision — history is preserved.
                  </span>
                )}
              </div>
              <p style={{ margin: 0, fontSize: 'var(--fs-sm)', color: 'var(--text-muted)' }}>
                {INSPECTION_DECISION_META[choice].description}
              </p>

              {blockedByGate && (
                <div className="demo-note" style={{ borderColor: 'var(--tone-warning)', display: 'flex', gap: 8 }}>
                  <Icon name="alert" size={15} />
                  <span>
                    Blocked by the decision gate — {blockers.length} unresolved critical/major
                    finding{blockers.length > 1 ? 's' : ''}. Resolve them or choose REQUIRES_FURTHER_REVIEW.
                  </span>
                </div>
              )}

              <label className="field">
                <span className="field__label">
                  Reason {reasonRequired ? '(mandatory)' : '(optional)'}
                </span>
                <textarea
                  className="textarea"
                  rows={2}
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  placeholder={
                    reasonRequired
                      ? 'Why this decision? This is recorded in the audit trail.'
                      : 'Optional note recorded with the decision.'
                  }
                />
              </label>

              {confirming ? (
                <div className="demo-note" style={{ borderColor: 'var(--tone-warning)', display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                  <Icon name="alert" size={15} />
                  <span>
                    Record <strong>{INSPECTION_DECISION_META[choice].label}</strong> as the final
                    decision for this inspection? This is an audit-logged human action.
                  </span>
                  <button
                    type="button"
                    className="btn btn--primary btn--sm"
                    disabled={!canSubmit}
                    onClick={() => void submit()}
                  >
                    {hitl.submitting ? 'Recording…' : 'Yes, record decision'}
                  </button>
                  <button
                    type="button"
                    className="btn btn--ghost btn--sm"
                    disabled={hitl.submitting}
                    onClick={() => setConfirming(false)}
                  >
                    Cancel
                  </button>
                </div>
              ) : (
                <div className="row" style={{ gap: 'var(--space-2)' }}>
                  <button
                    type="button"
                    className="btn btn--primary btn--sm"
                    disabled={!canSubmit}
                    onClick={() => setConfirming(true)}
                  >
                    Continue…
                  </button>
                  <button
                    type="button"
                    className="btn btn--ghost btn--sm"
                    onClick={() => {
                      setChoice(null);
                      setReason('');
                    }}
                  >
                    Cancel
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      </CardBody>
    </Card>
  );
}
