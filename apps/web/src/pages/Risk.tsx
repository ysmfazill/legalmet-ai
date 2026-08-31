import { useNavigate } from 'react-router-dom';

import type { Tone } from '@legalmet/config';

import { Badge, ConfidenceMeter, DemoBadge, RiskBadge, RISK_META } from '../components/Badge';
import { DistributionBar } from '../components/charts';
import { SectionCard } from '../components/Card';
import type { Column } from '../components/DataTable';
import { DataTable } from '../components/DataTable';
import { Icon } from '../components/Icon';
import { PageHeader } from '../components/PageHeader';
import { AsyncView } from '../components/states';
import { useAsync } from '../data/useAsync';
import { mockApi } from '../mock/adapter';
import type { RiskCase } from '../mock/types';

const WEIGHT_TONE: Record<string, Tone> = { High: 'critical', Medium: 'warning', Low: 'neutral' };

export function RiskPage() {
  const query = useAsync(() => mockApi.getRiskCases(), []);
  const navigate = useNavigate();

  return (
    <div className="page">
      <PageHeader
        eyebrow="Prioritisation"
        title="Risk Radar"
        lead="An Inspection Assistance Risk Score helps triage which packages an inspector should look at first. It is decision-support only, never a legal grading or penalty."
        actions={<DemoBadge label="DEMO SCORING" />}
      />

      <div className="demo-note demo-note--block">
        <Icon name="shield" size={15} />
        <span>
          The <strong>Inspection Assistance Risk Score</strong> is a heuristic combining evidence
          confidence, finding severity and image quality. <strong>Prioritization signal — not a
          legal determination.</strong> It ranks which packages an inspector should look at first;
          it does <strong>not</strong> determine compliance, and the demo scores below come from
          labelled demonstration data.
        </span>
      </div>

      <AsyncView query={query} loadingLabel="Loading risk radar…">
        {({ cases, factors }) => {
          const high = cases.filter((c) => c.risk === 'HIGH').length;
          const medium = cases.filter((c) => c.risk === 'MEDIUM').length;
          const low = cases.filter((c) => c.risk === 'LOW').length;

          const columns: Column<RiskCase>[] = [
            {
              key: 'product',
              header: 'Package',
              render: (c) => (
                <div style={{ minWidth: 0 }}>
                  <div className="cell-strong">{c.product}</div>
                  <div className="cell-muted" style={{ fontSize: 'var(--fs-sm)' }}>
                    {c.category}
                  </div>
                </div>
              ),
            },
            { key: 'finding', header: 'Leading factor', render: (c) => c.reason },
            { key: 'risk', header: 'Risk', render: (c) => <RiskBadge risk={c.risk} withLabel={false} /> },
            {
              key: 'score',
              header: 'Score',
              align: 'right',
              render: (c) => (
                <Badge tone={RISK_META[c.risk].tone} square>
                  {c.riskScore}
                </Badge>
              ),
            },
            { key: 'confidence', header: 'Confidence', render: (c) => <ConfidenceMeter value={c.confidence} /> },
            {
              key: 'action',
              header: 'Recommended',
              render: (c) => (
                <span className="cell-muted" style={{ fontSize: 'var(--fs-sm)' }}>
                  {c.recommendedAction}
                </span>
              ),
            },
          ];

          return (
            <>
              <SectionCard
                eyebrow="Distribution"
                title="Assistance risk bands"
                subtitle={`${cases.length} packages currently carrying elevated assistance risk`}
              >
                <DistributionBar
                  segments={[
                    { label: 'High', value: high, tone: 'critical' },
                    { label: 'Medium', value: medium, tone: 'warning' },
                    { label: 'Low', value: low, tone: 'neutral' },
                  ]}
                />
              </SectionCard>

              <SectionCard
                eyebrow="Model"
                title="What drives the score"
                subtitle="Transparent, weighted factors — no black box"
              >
                <div className="detail-list">
                  {factors.map((f) => (
                    <div key={f.label} className="detail-list__row">
                      <span className="detail-list__key">{f.label}</span>
                      <span className="detail-list__val">
                        <Badge tone={WEIGHT_TONE[f.weight] ?? 'neutral'}>{f.weight}</Badge>
                      </span>
                    </div>
                  ))}
                </div>
              </SectionCard>

              <SectionCard
                eyebrow="Queue"
                title="Prioritised packages"
                subtitle="Highest assistance risk first — open to review the evidence"
                flush
              >
                <DataTable
                  columns={columns}
                  rows={cases}
                  getRowId={(c) => c.inspectionId + c.finding}
                  ariaLabel="Risk cases"
                  onRowClick={(c) => navigate(`/inspections/${c.inspectionId}`)}
                />
              </SectionCard>
            </>
          );
        }}
      </AsyncView>
    </div>
  );
}
