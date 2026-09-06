import { Link, useNavigate } from 'react-router-dom';

import { DemoBadge } from '../components/Badge';
import { Card, CardBody, CardHead, SectionCard } from '../components/Card';
import { Icon } from '../components/Icon';
import { MetricCard } from '../components/MetricCard';
import { PageHeader } from '../components/PageHeader';
import { useApp } from '../app/AppContext';
import { useAsync } from '../data/useAsync';
import { AsyncView, EmptyState } from '../components/states';
import { formatDateTime } from '../lib/format';
import { mockApi } from '../mock/adapter';
import { allFindings } from '../mock/inspections';

const RISK_ORDER: Record<string, number> = { HIGH: 0, MEDIUM: 1, LOW: 2 };

/**
 * INSPECTOR DASHBOARD — a personal workspace: what the signed-in inspector
 * must verify next, and the INSPECT → VERIFY → DECIDE flow in one glance.
 * Final decisions are always the inspector's own.
 */
export function InspectorPage() {
  const { user, isLive } = useApp();
  const navigate = useNavigate();
  const queue = useAsync(() => mockApi.getReviewQueue(), []);

  // Demo dataset is authored around the demo inspector; when a real session
  // exists, live engine findings are reached via Review → Engine findings.
  const mine = (queue.data ?? []).filter(
    (it) => it.assignedTo === user.fullName || !isLive,
  );
  const openInspection = (id: string) => navigate(`/inspections/${id}`);

  return (
    <div className="page">
      <PageHeader
        eyebrow="Inspector"
        title="Inspector Workspace"
        lead={`Your verification workload, ${user.fullName}. Inspect → verify → decide: the system surfaces findings; the final decision is yours and is recorded in your name.`}
        actions={
          <>
            <Link to="/inspections/new" className="btn btn--primary">
              <Icon name="plus" size={16} />
              New inspection
            </Link>
            <DemoBadge />
          </>
        }
      />

      <div className="demo-note demo-note--block">
        <Icon name="info" size={15} />
        <span>
          The queue below is <strong>demonstration data</strong>.{' '}
          {isLive
            ? 'Live engine findings awaiting your decision are in Review Queue → Engine findings.'
            : 'Start the backend to reach the live engine findings.'}
        </span>
      </div>

      <AsyncView query={queue} loadingLabel="Loading your workload…">
        {() => {
          const sorted = [...mine].sort(
            (a, b) => RISK_ORDER[a.risk] - RISK_ORDER[b.risk] || b.confidence - a.confidence,
          );
          return (
            <>
              <div className="grid grid--metrics">
                <MetricCard label="Awaiting my decision" value={sorted.length} icon="review" hint="verify → decide" />
                <MetricCard
                  label="High-risk findings"
                  value={sorted.filter((it) => it.risk === 'HIGH').length}
                  icon="alert"
                  hint="check evidence first"
                />
                <MetricCard
                  label="Demo inspections reviewed"
                  value={new Set(allFindings.filter((f) => f.isReviewed).map((f) => f.inspectionId)).size}
                  icon="check"
                  hint="demo dataset"
                />
                <MetricCard
                  label="Engine decisions (live)"
                  value={0}
                  icon="shield"
                  hint={isLive ? 'recorded under your login' : 'backend offline — demo mode'}
                />
              </div>

              <SectionCard
                eyebrow="Verify"
                title="My verification queue"
                subtitle="Open a finding to see its evidence chain — requirement, rule version, OCR text, image region"
                actions={
                  <Link to="/review" className="btn btn--subtle btn--sm">
                    Review Queue
                    <Icon name="arrowRight" size={14} />
                  </Link>
                }
                flush
              >
                {sorted.length === 0 ? (
                  <div style={{ padding: 'var(--space-6)' }}>
                    <EmptyState
                      icon="check"
                      title="Nothing awaiting your decision"
                      message="Findings you verify and decide on will appear here."
                    />
                  </div>
                ) : (
                  <ul className="stack stack--sm" style={{ padding: 'var(--space-4)' }}>
                    {sorted.slice(0, 8).map((it) => (
                      <li
                        key={it.findingId}
                        className="row row--between row--wrap card"
                        style={{ padding: 'var(--space-3) var(--space-4)', gap: 'var(--space-3)' }}
                      >
                        <div style={{ minWidth: 0 }}>
                          <div className="cell-strong">{it.finding}</div>
                          <div className="cell-muted" style={{ fontSize: 'var(--fs-sm)' }}>
                            {it.product} · {formatDateTime(it.createdAt)}
                          </div>
                        </div>
                        <button
                          type="button"
                          className="btn btn--subtle btn--sm"
                          onClick={() => openInspection(it.inspectionId)}
                        >
                          Open workspace
                          <Icon name="arrowRight" size={14} />
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </SectionCard>

              <Card>
                <CardHead
                  eyebrow="Flow"
                  title="How an inspection runs"
                  subtitle="The system's role stops at evidence; the decision is yours"
                />
                <CardBody>
                  <ol className="detail-list" style={{ padding: 0 }}>
                    {[
                      {
                        title: 'INSPECT',
                        desc: 'Capture or upload the package label. The system runs real OCR and extracts declarations with confidence values.',
                      },
                      {
                        title: 'VERIFY',
                        desc: 'Open any finding to trace it: requirement → rule version in force → evaluation → extracted field → OCR text → image region. Correct a field if the reading is wrong — your correction is tagged HUMAN.',
                      },
                      {
                        title: 'DECIDE',
                        desc: 'Record the final decision — COMPLIANT, NON-COMPLIANT, REVIEW REQUIRED or INSUFFICIENT EVIDENCE. It is recorded in your name and audited. The system can only suggest.',
                      },
                    ].map((step) => (
                      <li key={step.title} className="detail-list__row">
                        <span className="detail-list__key">
                          <span className="eyebrow">{step.title}</span>
                        </span>
                        <span className="detail-list__val" style={{ textAlign: 'left', maxWidth: '70ch' }}>
                          {step.desc}
                        </span>
                      </li>
                    ))}
                  </ol>
                </CardBody>
              </Card>
            </>
          );
        }}
      </AsyncView>
    </div>
  );
}
