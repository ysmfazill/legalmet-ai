/**
 * Compliance panel for the REAL Inspection Workspace (Prompt 6).
 *
 * Two cards, deliberately honest:
 *
 * - {@link ComplianceControlCard} — run the deterministic evaluation, see the
 *   evaluation status and a COUNTS-ONLY summary. Never a percentage, never a
 *   "legal confidence" number.
 * - {@link ComplianceFindingsCard} — one row per (requirement, finding) with
 *   its status badge and a click-through to the full deterministic
 *   explanation + provenance drawer.
 *
 * The panel performs no approval/rejection: the queue says "System finding —
 * inspector decision pending", and the final enforcement decision belongs to
 * the inspector (recorded in a later phase).
 */
import { ENGINE_FINDING_STATUS_META } from '@legalmet/config';
import type { Tone } from '@legalmet/config';
import type { ComplianceEvaluation, EngineFinding } from '@legalmet/types';

import {
  ApplicabilityBadge,
  EngineFindingBadge,
  EvaluationStatusBadge,
  FindingReviewStateBadge,
} from '../components/Badge';
import { Card, CardBody, CardHead } from '../components/Card';
import { EmptyState } from '../components/states';
import { Icon } from '../components/Icon';
import { toneColor, toneSoft } from '../lib/tone';

/** Findings grouped for the count-only summary (order = display order). */
const SUMMARY_ORDER: Array<{ status: EngineFinding['status']; tone: Tone }> = [
  { status: 'COMPLIANT', tone: 'positive' },
  { status: 'NON_COMPLIANT', tone: 'critical' },
  { status: 'REVIEW_REQUIRED', tone: 'warning' },
  { status: 'NOT_DETECTED', tone: 'warning' },
  { status: 'NOT_APPLICABLE', tone: 'neutral' },
  { status: 'NOT_EVALUATED', tone: 'neutral' },
];

export function ComplianceControlCard({
  evaluation,
  evaluating,
  error,
  onEvaluate,
  hasEvidence,
}: {
  evaluation: ComplianceEvaluation | null;
  evaluating: boolean;
  error: string | null;
  onEvaluate: () => void;
  hasEvidence: boolean;
}) {
  return (
    <Card>
      <CardHead
        eyebrow="Compliance engine"
        title="Deterministic evaluation"
        subtitle="Rules checked against the regulatory version in force — no AI judgement"
        actions={evaluation ? <EvaluationStatusBadge status={evaluation.status} /> : undefined}
      />
      <CardBody>
        <div className="stack stack--sm">
          {error && (
            <div className="demo-note" style={{ borderColor: 'var(--tone-critical)', display: 'flex', gap: 8 }}>
              <Icon name="alert" size={15} />
              <span>{error}</span>
            </div>
          )}

          {evaluation?.error && (
            <div className="demo-note" style={{ borderColor: 'var(--tone-critical)', display: 'flex', gap: 8 }}>
              <Icon name="alert" size={15} />
              <span>
                <strong>Engine failure ({evaluation.error.code}).</strong> {evaluation.error.message} A
                failed run is never treated as compliance.
              </span>
            </div>
          )}

          {!evaluation && (
            <p style={{ color: 'var(--text-muted)', margin: 0 }}>
              No evaluation has been run yet. The engine will check every requirement in force at
              this inspection's context date against the perceived declarations — deterministically,
              with every conclusion traceable to evidence.
            </p>
          )}

          {evaluation && <SummaryCounts evaluation={evaluation} />}

          <div className="row" style={{ gap: 'var(--space-2)' }}>
            <button
              type="button"
              className="btn btn--primary btn--sm"
              onClick={onEvaluate}
              disabled={evaluating || !hasEvidence}
            >
              {evaluating ? (
                <>
                  <span className="spinner spinner--sm" aria-hidden /> Evaluating…
                </>
              ) : (
                <>
                  <Icon name="scale" size={15} />
                  {evaluation ? 'Run new evaluation' : 'Run evaluation'}
                </>
              )}
            </button>
            {evaluation && (
              <span className="cell-muted" style={{ fontSize: 'var(--fs-sm)', alignSelf: 'center' }}>
                engine v{evaluation.engineVersion} · each run is preserved as history
              </span>
            )}
          </div>

          {!hasEvidence && (
            <p style={{ fontSize: 'var(--fs-sm)', color: 'var(--text-muted)', margin: 0 }}>
              Run perception first — the engine only evaluates declarations the system perceived.
            </p>
          )}
        </div>
      </CardBody>
    </Card>
  );
}

function SummaryCounts({ evaluation }: { evaluation: ComplianceEvaluation }) {
  const summary = evaluation.summary;
  return (
    <div className="summary-breakdown">
      {SUMMARY_ORDER.filter((s) => (summary.byStatus[s.status] ?? 0) > 0).map((s) => (
        <div
          key={s.status}
          className="summary-breakdown__item"
          style={{ background: toneSoft(s.tone) }}
          title={ENGINE_FINDING_STATUS_META[s.status].description}
        >
          <span className="row" style={{ gap: 6 }}>
            <span className="badge__dot" style={{ color: toneColor(s.tone) }} aria-hidden />
            {ENGINE_FINDING_STATUS_META[s.status].label}
          </span>
          <span className="summary-breakdown__count">{summary.byStatus[s.status]}</span>
        </div>
      ))}
      <div className="summary-breakdown__item">
        <span className="row" style={{ gap: 6 }}>
          <Icon name="check" size={13} /> Requirements evaluated
        </span>
        <span className="summary-breakdown__count">{summary.requirementsEvaluated}</span>
      </div>
    </div>
  );
}

export function ComplianceFindingsCard({
  findings,
  onOpen,
  selectedFindingId,
}: {
  findings: EngineFinding[];
  onOpen: (finding: EngineFinding) => void;
  selectedFindingId: string | null;
}) {
  return (
    <Card>
      <CardHead
        eyebrow="Engine findings"
        title="Compliance findings"
        subtitle="Open any finding for its deterministic explanation and regulatory provenance"
      />
      <CardBody flush>
        {findings.length === 0 ? (
          <div style={{ padding: 'var(--space-5)' }}>
            <EmptyState
              icon="scale"
              title="No findings yet"
              message="Run the deterministic evaluation to produce findings."
            />
          </div>
        ) : (
          <div className="stack stack--sm" style={{ padding: 'var(--space-4)' }}>
            {findings.map((finding) => (
              <button
                key={finding.id}
                type="button"
                className="finding-row"
                style={{
                  display: 'flex',
                  width: '100%',
                  gap: 'var(--space-3)',
                  alignItems: 'flex-start',
                  textAlign: 'left',
                  padding: 'var(--space-3)',
                  background: selectedFindingId === finding.id ? 'var(--surface-raised)' : 'transparent',
                  border: '1px solid var(--border)',
                  borderRadius: 'var(--radius-md)',
                  cursor: 'pointer',
                }}
                onClick={() => onOpen(finding)}
              >
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div className="row" style={{ gap: 6, flexWrap: 'wrap' }}>
                    <span className="tag">{finding.provenance?.requirementCode ?? '—'}</span>
                    <span className="cell-strong" style={{ fontSize: 'var(--fs-sm)' }}>
                      {finding.provenance?.requirementTitle ?? 'Requirement'}
                    </span>
                  </div>
                  <div
                    className="cell-muted"
                    style={{ fontSize: 'var(--fs-sm)', marginTop: 4, overflowWrap: 'anywhere' }}
                  >
                    {finding.detectedValue
                      ? `Detected: ${finding.detectedValue}`
                      : 'Nothing detected — not evidence of absence'}
                  </div>
                </div>
                <div className="stack" style={{ gap: 4, alignItems: 'flex-end' }}>
                  <EngineFindingBadge status={finding.status} />
                  <FindingReviewStateBadge state={finding.reviewState} />
                  {finding.applicability !== 'YES' && (
                    <ApplicabilityBadge outcome={finding.applicability} />
                  )}
                </div>
              </button>
            ))}
            <p style={{ fontSize: 'var(--fs-sm)', color: 'var(--text-faint)', margin: 0 }}>
              System findings with their human review state — open a finding to review it (confirm,
              correct, reject or escalate). Compliance findings are system-generated
              decision-support outputs; they are not, by themselves, legal enforcement
              determinations. The final decision is recorded separately by the inspector.
            </p>
          </div>
        )}
      </CardBody>
    </Card>
  );
}
