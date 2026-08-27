import type { FindingCounts } from '@legalmet/types';

import { ConfidenceMeter, DemoBadge } from '../components/Badge';
import { BarList, DonutChart } from '../components/charts';
import { Card, CardHead, SectionCard } from '../components/Card';
import type { Column } from '../components/DataTable';
import { DataTable } from '../components/DataTable';
import { Icon } from '../components/Icon';
import { MetricCard } from '../components/MetricCard';
import { PageHeader } from '../components/PageHeader';
import { AsyncView } from '../components/states';
import { useAsync } from '../data/useAsync';
import { humanizeEnum } from '../lib/format';
import { mockApi } from '../mock/adapter';
import type { CategoryStat } from '../mock/types';
import { complianceSegments } from './Dashboard';

const EMPTY_COUNTS: FindingCounts = {
  total: 0,
  compliant: 0,
  potentialViolation: 0,
  reviewRequired: 0,
  notApplicable: 0,
  lowConfidence: 0,
  imageQualityInsufficient: 0,
};

const pct = (v: number) => `${Math.round(v * 100)}%`;

export function BatchesPage() {
  const query = useAsync(() => mockApi.getBatchIntelligence(), []);

  return (
    <div className="page">
      <PageHeader
        eyebrow="Bulk analysis"
        title="Batch Intelligence"
        lead="Aggregate AI-assisted analysis across a retail sweep — compliance distribution, recurring issue patterns and category hotspots. Decision-support only."
        actions={<DemoBadge label="DEMO BATCH" />}
      />

      <AsyncView query={query} loadingLabel="Loading batch intelligence…">
        {({ batch, summary, patterns, categories }) => {
          const counts: FindingCounts = batch.stats
            ? {
                total: batch.stats.total,
                compliant: batch.stats.byStatus.COMPLIANT,
                potentialViolation: batch.stats.byStatus.POTENTIAL_VIOLATION,
                reviewRequired: batch.stats.byStatus.REVIEW_REQUIRED,
                notApplicable: batch.stats.byStatus.NOT_APPLICABLE,
                lowConfidence: batch.stats.byStatus.LOW_CONFIDENCE,
                imageQualityInsufficient: batch.stats.byStatus.IMAGE_QUALITY_INSUFFICIENT,
              }
            : EMPTY_COUNTS;

          const categoryColumns: Column<CategoryStat>[] = [
            { key: 'category', header: 'Category', render: (c) => <span className="cell-strong">{c.category}</span> },
            { key: 'total', header: 'Packages', align: 'right', render: (c) => c.total },
            { key: 'violation', header: 'Violation rate', align: 'right', render: (c) => pct(c.violationRate) },
            { key: 'review', header: 'Review rate', align: 'right', render: (c) => pct(c.reviewRate) },
            {
              key: 'confidence',
              header: 'Avg confidence',
              render: (c) => <ConfidenceMeter value={c.confidence} />,
            },
          ];

          return (
            <>
              <Card>
                <CardHead
                  eyebrow="Batch"
                  title={batch.name}
                  subtitle={batch.description ?? undefined}
                  actions={<span className="badge badge--info badge--square">{humanizeEnum(batch.status)}</span>}
                />
              </Card>

              <div className="grid grid--metrics">
                <MetricCard label="Packages scanned" value={summary.scanned} icon="package" />
                <MetricCard label="Compliant" value={summary.compliant} icon="check" hint="AI-assisted" />
                <MetricCard label="Awaiting review" value={summary.review} icon="review" hint="inspector decision" />
                <MetricCard label="Potential violations" value={summary.violations} icon="alert" />
              </div>

              <div className="grid grid--2">
                <SectionCard
                  eyebrow="Findings"
                  title="Compliance distribution"
                  subtitle={`${counts.total} packages analysed`}
                >
                  <DonutChart
                    segments={complianceSegments(counts)}
                    centerValue={counts.total}
                    centerLabel="packages"
                  />
                </SectionCard>

                <SectionCard
                  eyebrow="Patterns"
                  title="Recurring issue patterns"
                  subtitle="Most frequent flagged issues in this batch (DEMO)"
                >
                  <BarList
                    rows={patterns.map((p) => ({
                      label: p.label,
                      value: p.count,
                      display: String(p.count),
                      tone: 'critical' as const,
                    }))}
                  />
                </SectionCard>
              </div>

              <SectionCard
                eyebrow="Hotspots"
                title="Category analysis"
                subtitle="Where flags concentrate across product categories"
                actions={
                  <span className="row" style={{ gap: 6, color: 'var(--text-faint)', fontSize: 'var(--fs-sm)' }}>
                    <Icon name="info" size={14} />
                    Average confidence, not a legal grading
                  </span>
                }
                flush
              >
                <DataTable
                  columns={categoryColumns}
                  rows={categories}
                  getRowId={(c) => c.category}
                  ariaLabel="Category analysis"
                />
              </SectionCard>
            </>
          );
        }}
      </AsyncView>
    </div>
  );
}
