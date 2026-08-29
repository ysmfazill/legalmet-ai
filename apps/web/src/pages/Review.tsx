import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { ConfidenceMeter, RiskBadge, StatusBadge, Tag } from '../components/Badge';
import { Card, CardBody } from '../components/Card';
import type { Column } from '../components/DataTable';
import { DataTable } from '../components/DataTable';
import { EvidenceDrawer } from '../components/EvidenceDrawer';
import { Icon } from '../components/Icon';
import { PageHeader } from '../components/PageHeader';
import { Segmented } from '../components/Tabs';
import type { TabDef } from '../components/Tabs';
import { AsyncView, EmptyState } from '../components/states';
import { useAsync } from '../data/useAsync';
import { EngineReviewQueueSection } from '../compliance/EngineReviewQueueSection';
import { useApp } from '../app/AppContext';
import { formatDateTime } from '../lib/format';
import { mockApi } from '../mock/adapter';
import { allFindings } from '../mock/inspections';
import type { FindingView, ReviewQueueItem } from '../mock/types';

type RiskFilter = 'ALL' | 'HIGH' | 'MEDIUM' | 'LOW';
type QueueSource = 'demo' | 'engine';

const RISK_FILTERS: TabDef<RiskFilter>[] = [
  { id: 'ALL', label: 'All' },
  { id: 'HIGH', label: 'High' },
  { id: 'MEDIUM', label: 'Medium' },
  { id: 'LOW', label: 'Low' },
];

const RISK_ORDER: Record<string, number> = { HIGH: 0, MEDIUM: 1, LOW: 2 };

export function ReviewPage() {
  const { isLive } = useApp();
  const query = useAsync(() => mockApi.getReviewQueue(), []);
  const navigate = useNavigate();
  const [risk, setRisk] = useState<RiskFilter>('ALL');
  const [openFinding, setOpenFinding] = useState<FindingView | null>(null);
  const [reviewed, setReviewed] = useState<Set<string>>(new Set());
  const [source, setSource] = useState<QueueSource>('demo');

  // The full, linked finding powers the WHY / Evidence drawer (demo dataset).
  const findingsById = useMemo(() => new Map(allFindings.map((f) => [f.id, f])), []);

  return (
    <div className="page">
      <PageHeader
        eyebrow="Human-in-the-loop"
        title="Review Queue"
        lead="Findings the system flagged for a human decision. Open any item to inspect the evidence and record an inspector decision — the system never decides on its own."
        actions={
          isLive ? (
            <Segmented
              options={[
                { id: 'demo', label: 'Demo findings' },
                { id: 'engine', label: 'Engine findings' },
              ]}
              active={source}
              onChange={(next) => setSource(next)}
              ariaLabel="Choose finding source"
            />
          ) : undefined
        }
      />

      {isLive && source === 'engine' ? (
        <EngineReviewQueueSection />
      ) : (
        <AsyncView query={query} loadingLabel="Loading review queue…">
        {(items) => {
          const filtered = [...items]
            .filter((it) => risk === 'ALL' || it.risk === risk)
            .sort((a, b) => RISK_ORDER[a.risk] - RISK_ORDER[b.risk] || b.confidence - a.confidence);

          const columns: Column<ReviewQueueItem>[] = [
            {
              key: 'finding',
              header: 'Finding',
              render: (r) => (
                <div style={{ minWidth: 0 }}>
                  <div className="cell-strong">{r.finding}</div>
                  <div className="cell-muted" style={{ fontSize: 'var(--fs-sm)' }}>
                    {r.product}
                  </div>
                </div>
              ),
            },
            { key: 'status', header: 'Suggested', render: (r) => <StatusBadge status={r.status} /> },
            { key: 'risk', header: 'Risk', render: (r) => <RiskBadge risk={r.risk} withLabel={false} /> },
            {
              key: 'confidence',
              header: 'Confidence',
              render: (r) => <ConfidenceMeter value={r.confidence} />,
            },
            {
              key: 'created',
              header: 'Flagged',
              render: (r) => (
                <span className="cell-muted" style={{ fontSize: 'var(--fs-sm)' }}>
                  {formatDateTime(r.createdAt)}
                </span>
              ),
            },
            { key: 'assignee', header: 'Assigned', render: (r) => r.assignedTo },
            {
              key: 'action',
              header: '',
              align: 'right',
              render: (r) =>
                reviewed.has(r.findingId) ? (
                  <Tag>Recorded</Tag>
                ) : (
                  <span className="row" style={{ gap: 4, color: 'var(--accent-strong)', fontWeight: 600, justifyContent: 'flex-end' }}>
                    Review
                    <Icon name="arrowRight" size={13} />
                  </span>
                ),
            },
          ];

          return (
            <Card>
              <CardBody flush>
                <div className="filter-bar">
                  <Segmented options={RISK_FILTERS} active={risk} onChange={setRisk} ariaLabel="Filter by risk" />
                  <span className="spacer" />
                  <span className="cell-muted" style={{ fontSize: 'var(--fs-sm)' }}>
                    {filtered.length} awaiting decision
                  </span>
                </div>

                {filtered.length === 0 ? (
                  <div style={{ padding: 'var(--space-6)' }}>
                    <EmptyState
                      icon="check"
                      title="Queue clear"
                      message="No findings match this risk filter."
                    />
                  </div>
                ) : (
                  <DataTable
                    columns={columns}
                    rows={filtered}
                    getRowId={(r) => r.findingId}
                    ariaLabel="Review queue"
                    onRowClick={(r) => {
                      const f = findingsById.get(r.findingId);
                      if (f) setOpenFinding(f);
                      else navigate(`/inspections/${r.inspectionId}`);
                    }}
                  />
                )}
              </CardBody>
            </Card>
          );
        }}
      </AsyncView>
      )}

      {openFinding && (
        <EvidenceDrawer
          finding={openFinding}
          onClose={() => setOpenFinding(null)}
          onReviewed={(findingId) => setReviewed((prev) => new Set(prev).add(findingId))}
        />
      )}
    </div>
  );
}
