import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import type { FindingCounts } from '@legalmet/types';
import type { Tone } from '@legalmet/config';

import { ActivityChart, BarList, DistributionBar, DonutChart } from '../components/charts';
import type { DonutSegment } from '../components/charts';
import { ConfidenceMeter, RiskBadge } from '../components/Badge';
import { Card, CardBody, CardHead, SectionCard } from '../components/Card';
import { Icon } from '../components/Icon';
import { InspectionTable } from '../components/InspectionTable';
import { MetricCard } from '../components/MetricCard';
import { EmptyState } from '../components/states';
import { AsyncView } from '../components/states';
import { PageHeader } from '../components/PageHeader';
import { Segmented } from '../components/Tabs';
import { useAsync } from '../data/useAsync';
import { formatDateTime } from '../lib/format';
import { mockApi } from '../mock/adapter';
import type { ReviewQueueItem } from '../mock/types';

type Range = 'today' | 'week' | 'month';

const RANGE_TABS = [
  { id: 'today' as const, label: 'Today' },
  { id: 'week' as const, label: 'This week' },
  { id: 'month' as const, label: 'This month' },
];

const RISK_ORDER: Record<string, number> = { HIGH: 0, MEDIUM: 1, LOW: 2 };

/** Compliance-status → donut segments (shared shape with Batch Intelligence). */
export function complianceSegments(f: FindingCounts): DonutSegment[] {
  const rows: { label: string; value: number; tone: Tone }[] = [
    { label: 'Compliant', value: f.compliant, tone: 'positive' },
    { label: 'Review required', value: f.reviewRequired, tone: 'warning' },
    { label: 'Potential violation', value: f.potentialViolation, tone: 'critical' },
    { label: 'Not applicable', value: f.notApplicable, tone: 'neutral' },
    { label: 'Low confidence', value: f.lowConfidence, tone: 'info' },
    { label: 'Image quality', value: f.imageQualityInsufficient, tone: 'info' },
  ];
  return rows.filter((r) => r.value > 0);
}

function trendLabel(delta: number, note: string): string {
  return `${delta > 0 ? '+' : ''}${delta} · ${note}`;
}

export function DashboardPage() {
  const [range, setRange] = useState<Range>('week');
  const dash = useAsync(() => mockApi.getDashboard(), []);
  const queue = useAsync(() => mockApi.getReviewQueue(), []);
  const navigate = useNavigate();
  const openInspection = (id: string) => navigate(`/inspections/${id}`);

  return (
    <div className="page">
      <PageHeader
        eyebrow="Overview"
        title="Command Center"
        lead="AI-assisted triage across packaged-commodity inspections. Every figure is decision-support only — inspectors make the final call."
        actions={
          <Link to="/inspections/new" className="btn btn--primary">
            <Icon name="plus" size={16} />
            New inspection
          </Link>
        }
      />

      <div className="demo-note demo-note--block">
        <Icon name="info" size={15} />
        <span>
          Aggregate statistics on this page come from <strong>clearly labelled demonstration data</strong>{' '}
          — they illustrate the shape of the system and are not live inspection counts. Real
          inspections you create appear in <Link to="/inspections">Inspections</Link> (Live source),{' '}
          <Link to="/review">Review</Link> (Engine findings) and <Link to="/evidence">Evidence Explorer</Link>.
        </span>
      </div>

      <AsyncView query={dash} loadingLabel="Loading command center…">
        {({ summary, trends, activity, risk }) => (
          <>
            <div className="grid grid--metrics">
              <MetricCard
                label="Total inspections"
                value={trends.totalInspections.value}
                icon="inspections"
                trend={{ dir: trends.totalInspections.dir, label: trendLabel(trends.totalInspections.delta, trends.totalInspections.note) }}
              />
              <MetricCard
                label="Packages scanned"
                value={trends.packagesScanned.value}
                icon="package"
                trend={{ dir: trends.packagesScanned.dir, label: trendLabel(trends.packagesScanned.delta, trends.packagesScanned.note) }}
              />
              <MetricCard
                label="Awaiting review"
                value={trends.reviewRequired.value}
                icon="review"
                trend={{ dir: trends.reviewRequired.dir, label: trendLabel(trends.reviewRequired.delta, trends.reviewRequired.note), good: false }}
                hint="inspector decision"
              />
              <MetricCard
                label="Potential violations"
                value={trends.potentialViolations.value}
                icon="alert"
                trend={{ dir: trends.potentialViolations.dir, label: trendLabel(trends.potentialViolations.delta, trends.potentialViolations.note), good: true }}
              />
            </div>

            <div className="grid grid--2">
              <Card>
                <CardHead
                  eyebrow="Throughput"
                  title="Scan activity"
                  subtitle="Packages scanned vs. flagged for review"
                  actions={<Segmented options={RANGE_TABS} active={range} onChange={setRange} ariaLabel="Activity range" />}
                />
                <CardBody>
                  <ActivityChart points={activity[range]} />
                </CardBody>
              </Card>

              <SectionCard
                eyebrow="Findings"
                title="Finding status distribution"
                subtitle={`${summary.findings.total} findings analysed (demonstration data — not live inspection counts)`}
              >
                <DonutChart
                  segments={complianceSegments(summary.findings)}
                  centerValue={summary.findings.total}
                  centerLabel="findings"
                />
              </SectionCard>
            </div>

            <div className="grid grid--2">
              <SectionCard
                eyebrow="Assistance risk"
                title="Risk overview"
                subtitle="Indicative inspection-assistance risk bands — not a legal grading"
              >
                <DistributionBar
                  segments={[
                    { label: 'High', value: risk.high, tone: 'critical' },
                    { label: 'Medium', value: risk.medium, tone: 'warning' },
                    { label: 'Low', value: risk.low, tone: 'neutral' },
                  ]}
                />
              </SectionCard>

              <SectionCard
                eyebrow="Patterns"
                title="Recurring findings"
                subtitle="Most frequent flagged declarations (DEMO)"
              >
                <BarList
                  rows={summary.recurringViolations.map((v) => ({
                    label: `${v.ruleCode ?? v.fieldType ?? 'Unknown'}`,
                    value: v.count,
                    display: `${v.count} · ${v.affectedInspections} insp.`,
                    tone: 'critical' as const,
                  }))}
                />
              </SectionCard>
            </div>

            <SectionCard
              eyebrow="Queue"
              title="Recent inspections"
              actions={
                <Link to="/inspections" className="btn btn--subtle btn--sm">
                  View all
                  <Icon name="arrowRight" size={14} />
                </Link>
              }
              flush
            >
              <InspectionTable inspections={summary.recentInspections} onOpen={openInspection} />
            </SectionCard>

            <SectionCard
              eyebrow="Priority"
              title="Priority review"
              subtitle="Highest-risk findings awaiting an inspector decision"
              flush
            >
              <AsyncView query={queue}>
                {(items) => <PriorityList items={items} onOpen={openInspection} />}
              </AsyncView>
            </SectionCard>
          </>
        )}
      </AsyncView>
    </div>
  );
}

function PriorityList({ items, onOpen }: { items: ReviewQueueItem[]; onOpen: (id: string) => void }) {
  const top = [...items]
    .sort((a, b) => (RISK_ORDER[a.risk] - RISK_ORDER[b.risk]) || b.confidence - a.confidence)
    .slice(0, 4);
  if (top.length === 0) {
    return (
      <div style={{ padding: 'var(--space-5)' }}>
        <EmptyState icon="check" title="Nothing awaiting review" message="All findings have been reviewed." />
      </div>
    );
  }
  return (
    <ul className="stack stack--sm" style={{ padding: 'var(--space-4)' }}>
      {top.map((it) => (
        <li key={it.findingId} className="row row--between row--wrap card" style={{ padding: 'var(--space-3) var(--space-4)', gap: 'var(--space-3)' }}>
          <div style={{ minWidth: 0 }}>
            <div className="cell-strong">{it.finding}</div>
            <div className="cell-muted" style={{ fontSize: 'var(--fs-sm)' }}>
              {it.product} · {formatDateTime(it.createdAt)}
            </div>
          </div>
          <div className="row" style={{ gap: 'var(--space-3)' }}>
            <RiskBadge risk={it.risk} />
            <ConfidenceMeter value={it.confidence} showValue={false} />
            <button type="button" className="btn btn--subtle btn--sm" onClick={() => onOpen(it.inspectionId)}>
              Open
              <Icon name="arrowRight" size={14} />
            </button>
          </div>
        </li>
      ))}
    </ul>
  );
}
