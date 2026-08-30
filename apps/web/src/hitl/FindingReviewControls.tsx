/**
 * Per-finding human review controls (Prompt 8).
 *
 * The AI half of the panel is read-only: status, explanation, evidence links —
 * all frozen system outputs. The HUMAN half records the inspector's verdict:
 *
 *   CONFIRM   — the inspector agrees with the system finding
 *   CORRECT   — the underlying value is wrong; a correction is recorded
 *               (append-only — the AI original is never overwritten) and the
 *               review state moves to CORRECTED
 *   REJECT    — the inspector rejects the finding (reason mandatory)
 *   ESCALATE  — route to a supervisor (reason mandatory)
 *   OVERRIDE  — supervisor/admin only, overrides a reviewed outcome
 *               (reason mandatory — an unexplained override is impossible)
 *
 * The buttons only ever REQUEST an action: the backend owns the state machine
 * (illegal transitions return 409 and are surfaced here verbatim).
 */
import { useEffect, useState } from 'react';

import { FINDING_REVIEW_STATE_META } from '@legalmet/config';
import type { FindingReviewAction } from '@legalmet/types';

import { api } from '../api/client';
import { useApp } from '../app/AppContext';
import { FindingReviewStateBadge } from '../components/Badge';
import { Icon } from '../components/Icon';
import type { EngineFinding } from '@legalmet/types';
import type { HitlState } from './useHitl';
import { formatDateTime } from '../lib/format';

type Action = FindingReviewAction;

const REASON_REQUIRED: ReadonlySet<Action> = new Set(['REJECT', 'OVERRIDE', 'ESCALATE']);

/** Actions the current user may request, given their role. */
function availableActions(role: string | undefined): Action[] {
  const base: Action[] = ['CONFIRM', 'CORRECT', 'REJECT', 'ESCALATE'];
  if (role === 'SUPERVISOR' || role === 'ADMIN') base.push('OVERRIDE');
  return base;
}

const ACTION_LABEL: Record<Action, string> = {
  CONFIRM: 'Confirm',
  CORRECT: 'Correct value',
  REJECT: 'Reject finding',
  ESCALATE: 'Escalate',
  OVERRIDE: 'Override',
};

const ACTION_HINT: Record<Action, string> = {
  CONFIRM: 'Agree with the system finding.',
  CORRECT: 'Record the true value — the AI extraction stays in history.',
  REJECT: 'Reject the system finding. A reason is mandatory.',
  ESCALATE: 'Route this finding to a supervisor. A reason is mandatory.',
  OVERRIDE: 'Override the reviewed outcome (supervisor/admin only). A reason is mandatory.',
};

export function FindingReviewControls({
  finding,
  hitl,
  onReviewed,
}: {
  finding: EngineFinding;
  hitl: HitlState;
  /** Called after a successful action so the caller can refresh findings. */
  onReviewed?: () => void;
}) {
  const { user } = useApp();
  const [action, setAction] = useState<Action | null>(null);
  const [reason, setReason] = useState('');
  const [correctedValue, setCorrectedValue] = useState('');
  const [fieldReview, setFieldReview] = useState<{
    originalValue?: string | null;
    aiConfidence?: number | null;
    correctedValue?: string | null;
  } | null>(null);

  // Load the AI-vs-human comparison when the inspector starts a correction.
  useEffect(() => {
    if (action !== 'CORRECT' || !finding.extractedFieldId) return;
    let cancelled = false;
    api
      .getFieldReview(finding.extractedFieldId)
      .then((review) => {
        if (!cancelled) {
          setFieldReview(review);
          setCorrectedValue(review.correctedValue ?? review.originalValue ?? '');
        }
      })
      .catch(() => {
        if (!cancelled) setFieldReview(null);
      });
    return () => {
      cancelled = true;
    };
  }, [action, finding.extractedFieldId]);

  const terminal =
    finding.reviewState === 'REJECTED' || finding.reviewState === 'OVERRIDDEN';
  const reasonRequired = action !== null && REASON_REQUIRED.has(action);
  const canSubmit =
    action !== null &&
    !hitl.submitting &&
    (!reasonRequired || reason.trim().length >= 3) &&
    (action !== 'CORRECT' ||
      (Boolean(finding.extractedFieldId) && correctedValue.trim().length > 0));

  const submit = async () => {
    if (action === null) return;
    const review = await hitl.reviewFinding(finding.id, {
      action,
      reason: reason.trim() || null,
      correctedValue: action === 'CORRECT' ? correctedValue.trim() : undefined,
    });
    if (review) {
      setAction(null);
      setReason('');
      onReviewed?.();
    }
  };

  return (
    <section className="stack stack--sm">
      <div className="eyebrow">Inspector review</div>

      <div className="row row--wrap" style={{ gap: 6 }}>
        <FindingReviewStateBadge state={finding.reviewState} />
        {finding.reviewedAt && (
          <span className="cell-muted" style={{ fontSize: 'var(--fs-sm)' }}>
            last action {formatDateTime(finding.reviewedAt)}
          </span>
        )}
      </div>
      <p style={{ margin: 0, fontSize: 'var(--fs-sm)', color: 'var(--text-muted)' }}>
        {FINDING_REVIEW_STATE_META[finding.reviewState].description}
      </p>

      {hitl.error && (
        <div
          className="demo-note"
          style={{ borderColor: 'var(--tone-critical)', display: 'flex', gap: 8 }}
        >
          <Icon name="alert" size={15} />
          <span>{hitl.error}</span>
        </div>
      )}

      {terminal ? (
        <p style={{ margin: 0, fontSize: 'var(--fs-sm)', color: 'var(--text-muted)' }}>
          This review is in a terminal state ({finding.reviewState}). It cannot be changed —
          the history is preserved exactly as recorded.
        </p>
      ) : (
        <>
          <div className="row row--wrap" style={{ gap: 'var(--space-2)' }}>
            {availableActions(user?.role).map((a) => (
              <button
                key={a}
                type="button"
                className={a === 'CONFIRM' ? 'btn btn--primary btn--sm' : 'btn btn--subtle btn--sm'}
                aria-pressed={action === a}
                title={ACTION_HINT[a]}
                disabled={hitl.submitting}
                onClick={() => {
                  setAction((cur) => (cur === a ? null : a));
                  setReason('');
                }}
              >
                {ACTION_LABEL[a]}
              </button>
            ))}
          </div>

          {action && (
            <div className="stack stack--sm" style={{ borderTop: '1px solid var(--border)', paddingTop: 'var(--space-3)' }}>
              <p style={{ margin: 0, fontSize: 'var(--fs-sm)', color: 'var(--text-muted)' }}>
                {ACTION_HINT[action]}
              </p>

              {action === 'CORRECT' && (
                <div className="stack stack--sm">
                  {!finding.extractedFieldId ? (
                    <p style={{ margin: 0, fontSize: 'var(--fs-sm)', color: 'var(--tone-critical)' }}>
                      This finding has no extracted field to correct.
                    </p>
                  ) : (
                    <>
                      <div className="detail-list">
                        <div className="detail-list__row">
                          <span className="detail-list__key">AI-extracted value</span>
                          <span className="detail-list__val" style={{ fontFamily: 'var(--font-mono)' }}>
                            {fieldReview?.originalValue ?? finding.detectedValue ?? '—'}
                          </span>
                        </div>
                        {fieldReview?.aiConfidence != null && (
                          <div className="detail-list__row">
                            <span className="detail-list__key">AI confidence</span>
                            <span className="detail-list__val">
                              {Math.round(fieldReview.aiConfidence * 100)}%
                            </span>
                          </div>
                        )}
                      </div>
                      <label className="field">
                        <span className="field__label">Corrected value</span>
                        <input
                          className="input"
                          value={correctedValue}
                          onChange={(e) => setCorrectedValue(e.target.value)}
                          placeholder="The true value, as verified on the physical package"
                        />
                      </label>
                      <p style={{ margin: 0, fontSize: 'var(--fs-xs)', color: 'var(--text-faint)' }}>
                        The original AI extraction stays in the correction history — nothing is
                        overwritten. After correcting, run a new evaluation to re-check this
                        requirement against the corrected value.
                      </p>
                    </>
                  )}
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
                      ? 'Why this action? This is recorded in the audit trail.'
                      : 'Optional note recorded with the action.'
                  }
                />
              </label>

              <div className="row" style={{ gap: 'var(--space-2)' }}>
                <button
                  type="button"
                  className="btn btn--primary btn--sm"
                  disabled={!canSubmit}
                  onClick={() => void submit()}
                >
                  {hitl.submitting ? (
                    <>
                      <span className="spinner spinner--sm" aria-hidden /> Recording…
                    </>
                  ) : (
                    `Record ${ACTION_LABEL[action].toLowerCase()}`
                  )}
                </button>
                <button
                  type="button"
                  className="btn btn--ghost btn--sm"
                  disabled={hitl.submitting}
                  onClick={() => {
                    setAction(null);
                    setReason('');
                  }}
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </section>
  );
}
