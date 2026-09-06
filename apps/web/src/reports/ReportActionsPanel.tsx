/**
 * Report actions panel (UI-08 §8, §13, §16, §31).
 *
 * The right rail of the report detail page: sticky lifecycle actions plus the
 * finalization gate checklist. The gate itself is enforced by the BACKEND —
 * this panel renders the blockers it returns and offers the two spec CTAs
 * ([Resolve Missing Evidence] → the inspection workspace, and the return
 * link). Buttons are hidden for read-only roles, but the backend rejects
 * those writes independently — hiding is never the authorization.
 */
import { useState } from 'react';
import { Link } from 'react-router-dom';

import type { ReportDetail } from '@legalmet/types';

import { Badge } from '../components/Badge';
import { Card, CardBody, CardHead } from '../components/Card';
import { Modal } from '../components/Modal';
import { Icon } from '../components/Icon';
import { formatDateTime } from '../lib/format';

import { ReportStatusChip } from './ReportChips';

export interface ReportActionsPanelProps {
  report: ReportDetail;
  acting: boolean;
  canWrite: boolean;
  actionError: string | null;
  actionNotice: string | null;
  onGenerate: () => void;
  onReview: () => void;
  onFinalize: () => void;
  onAmend: (reason: string) => Promise<unknown>;
  onExport: (format: 'pdf' | 'docx') => Promise<boolean>;
  onOpenPack: () => void;
}

export function ReportActionsPanel(props: ReportActionsPanelProps) {
  const { report, acting, canWrite, actionError, actionNotice } = props;
  const [amendOpen, setAmendOpen] = useState(false);
  const [amendReason, setAmendReason] = useState('');

  const status = report.status;
  const generated = Boolean(report.generatedAt);
  const finalized = status === 'FINALIZED' || status === 'EXPORTED' || status === 'AMENDED';
  const gate = report.evidence;
  const gateBlocked = !gate.canFinalize || !hasDecision(report);

  return (
    <Card className="report-actions">
      <CardHead
        eyebrow="Lifecycle"
        title="Report actions"
        subtitle="Generation, review, the finalization gate and exports"
      />
      <CardBody>
        <div className="stack stack--sm">
          {/* ------------------------------------------------ honest feedback */}
          {actionError && (
            <div
              className="demo-note"
              style={{ borderColor: 'var(--tone-critical)', display: 'flex', gap: 8 }}
              role="alert"
            >
              <Icon name="alert" size={15} />
              <span>{actionError}</span>
            </div>
          )}
          {actionNotice && (
            <div
              className="demo-note"
              style={{ borderColor: 'var(--tone-positive)', display: 'flex', gap: 8 }}
              role="status"
            >
              <Icon name="check" size={15} />
              <span>{actionNotice}</span>
            </div>
          )}

          {/* -------------------------------------------------------- gate */}
          <FinalizationGateCard report={report} />

          {/* ------------------------------------------------------ actions */}
          {canWrite ? (
            <div className="stack stack--xs">
              {!generated && (
                <button type="button" className="btn btn--primary" disabled={acting} onClick={props.onGenerate}>
                  <Icon name="sparkscan" size={15} />
                  Generate Report
                </button>
              )}
              {generated && !finalized && (
                <>
                  {status === 'UNDER_REVIEW' && (
                    <button type="button" className="btn btn--subtle" disabled={acting} onClick={props.onReview}>
                      <Icon name="check" size={15} />
                      Mark Reviewed
                    </button>
                  )}
                  <button
                    type="button"
                    className="btn btn--primary"
                    disabled={acting || gateBlocked}
                    title={gateBlocked ? 'Resolve the missing evidence first — the backend enforces this gate.' : undefined}
                    onClick={props.onFinalize}
                  >
                    <Icon name="shield" size={15} />
                    Finalize Report
                  </button>
                </>
              )}
              {finalized && (
                <button type="button" className="btn btn--subtle" disabled={acting} onClick={() => setAmendOpen(true)}>
                  <Icon name="edit" size={15} />
                  Amend (new version)
                </button>
              )}
            </div>
          ) : (
            <p style={{ margin: 0, fontSize: 'var(--fs-sm)', color: 'var(--text-faint)' }}>
              Read-only role — lifecycle actions are unavailable (and rejected server-side).
            </p>
          )}

          {/* exports + evidence pack are read actions: any report role may
              download what was already finalized. */}
          {generated && (
            <div className="row row--wrap" style={{ gap: 8 }}>
              <button
                type="button"
                className="btn btn--subtle btn--sm"
                disabled={acting}
                onClick={() => void props.onExport('pdf')}
              >
                <Icon name="download" size={14} />
                Export PDF
              </button>
              <button
                type="button"
                className="btn btn--subtle btn--sm"
                disabled={acting}
                onClick={() => void props.onExport('docx')}
              >
                <Icon name="download" size={14} />
                Export DOCX
              </button>
              <button
                type="button"
                className="btn btn--subtle btn--sm"
                disabled={acting}
                onClick={props.onOpenPack}
              >
                <Icon name="layers" size={14} />
                Evidence Pack
              </button>
            </div>
          )}

          {/* --------------------------------------------------- versioning */}
          {report.versions.length > 0 && (
            <div>
              <div className="eyebrow">Version history</div>
              <div className="stack stack--xs" style={{ marginTop: 6 }}>
                {report.versions.map((v) => (
                  <div
                    key={v.version}
                    className="row row--between row--wrap"
                    style={{ gap: 6, fontSize: 'var(--fs-sm)' }}
                  >
                    <span>
                      <strong>v{v.version}</strong>
                      {v.version === report.version && (
                        <Badge tone="info" outline>
                          current
                        </Badge>
                      )}
                    </span>
                    <span className="cell-muted" title={v.reason}>
                      {v.reason}
                    </span>
                    <span className="cell-muted">{formatDateTime(v.createdAt)}</span>
                  </div>
                ))}
              </div>
              {report.amendmentReason && (
                <p style={{ margin: '6px 0 0', fontSize: 'var(--fs-sm)', color: 'var(--text-muted)' }}>
                  Amendment reason: {report.amendmentReason}
                </p>
              )}
            </div>
          )}
        </div>
      </CardBody>

      {amendOpen && (
        <Modal
          title="Amend this report"
          onClose={() => setAmendOpen(false)}
          footer={
            <>
              <button type="button" className="btn btn--subtle" onClick={() => setAmendOpen(false)}>
                Cancel
              </button>
              <button
                type="button"
                className="btn btn--primary"
                disabled={!amendReason.trim() || acting}
                onClick={() => {
                  const reason = amendReason.trim();
                  setAmendOpen(false);
                  setAmendReason('');
                  if (reason) void props.onAmend(reason);
                }}
              >
                Issue new version
              </button>
            </>
          }
        >
          <p style={{ marginTop: 0, fontSize: 'var(--fs-sm)', color: 'var(--text-muted)' }}>
            A new snapshot version will be generated from the current inspection data. The previous
            finalized version is preserved verbatim — amendments never silently overwrite.
          </p>
          <label className="field">
            <span className="field__label">
              Reason (mandatory — an unexplained amendment is never accepted)
            </span>
            <textarea
              className="input"
              rows={3}
              value={amendReason}
              onChange={(e) => setAmendReason(e.target.value)}
              placeholder="e.g. Physical measurement re-recorded with a verified instrument"
            />
          </label>
        </Modal>
      )}
    </Card>
  );
}

function hasDecision(report: ReportDetail): boolean {
  const snapshot = report.snapshot as Record<string, unknown> | null;
  return Boolean(snapshot?.['decision']);
}

/** §8 + §13: the finalization gate checklist, rendered from the backend gate. */
function FinalizationGateCard({ report }: { report: ReportDetail }) {
  const gate = report.evidence;
  const decision = hasDecision(report);
  const findingsFrozen = Boolean(report.generatedAt);

  const items: Array<{ ok: boolean; label: string; hint?: string }> = [
    {
      ok: findingsFrozen,
      label: 'Snapshot generated',
      hint: findingsFrozen
        ? `Frozen at ${formatDateTime(report.generatedAt)}`
        : 'Generate the report to freeze its evidence and findings.',
    },
    {
      ok: gate.requiredOpen === 0,
      label: `${gate.requiredTotal - gate.requiredOpen} / ${gate.requiredTotal} required evidence satisfied`,
      hint:
        gate.requiredOpen > 0
          ? 'Report cannot be finalized until required evidence is resolved.'
          : 'All required evidence is resolved.',
    },
    {
      ok: decision,
      label: 'Inspector decision recorded',
      hint: decision
        ? undefined
        : 'No inspector decision recorded — the report cannot state a result without one.',
    },
  ];

  const allowed = findingsFrozen && gate.requiredOpen === 0 && decision;

  return (
    <div className="gate">
      <div className="row row--between" style={{ gap: 6 }}>
        <strong style={{ fontSize: 'var(--fs-sm)' }}>Finalization gate</strong>
        <ReportStatusChip status={report.status} />
      </div>
      <ul style={{ listStyle: 'none', margin: '8px 0 0', padding: 0 }} className="stack stack--xs">
        {items.map((item) => (
          <li key={item.label} className="row" style={{ gap: 8, alignItems: 'flex-start' }}>
            <Icon name={item.ok ? 'check' : 'alert'} size={14} />
            <div>
              <span style={{ fontSize: 'var(--fs-sm)' }}>{item.label}</span>
              {item.hint && (
                <div style={{ fontSize: 'var(--fs-sm)', color: 'var(--text-muted)' }}>{item.hint}</div>
              )}
            </div>
          </li>
        ))}
      </ul>
      {!allowed && gate.blockers.length > 0 && (
        <div className="stack stack--xs" style={{ marginTop: 8 }}>
          {gate.blockers.slice(0, 5).map((b, i) => (
            <div
              key={i}
              style={{ fontSize: 'var(--fs-sm)', color: 'var(--tone-critical)' }}
              title={b}
            >
              • {b}
            </div>
          ))}
        </div>
      )}
      {gate.recommendedOpen > 0 && (
        <p style={{ margin: '8px 0 0', fontSize: 'var(--fs-sm)', color: 'var(--text-faint)' }}>
          {gate.recommendedOpen} recommended evidence item(s) remain unresolved — recommended, not
          legally required.
        </p>
      )}
      {!allowed && (
        <div className="row row--wrap" style={{ gap: 8, marginTop: 10 }}>
          <Link
            className="btn btn--subtle btn--sm"
            to={`/inspections/${report.inspectionId}`}
          >
            <Icon name="evidence" size={14} />
            Resolve Missing Evidence
          </Link>
          <Link className="btn btn--ghost btn--sm" to={`/inspections/${report.inspectionId}`}>
            Return to Inspection
          </Link>
        </div>
      )}
    </div>
  );
}
