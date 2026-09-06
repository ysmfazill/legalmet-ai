/**
 * UI-09 §12-§24 — OPERATIONAL INTELLIGENCE (/analytics).
 *
 * Every number on this page comes from the /analytics/operational endpoint —
 * a server-side aggregation over real database rows. There is no new AI risk
 * score (§20), no fabricated data: rates the backend cannot compute arrive
 * null and render as N/A, a small dataset renders the honest "Limited data"
 * banner, and location intelligence without accumulated locations says so.
 */
import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';

import { REPORT_RESULT_META } from '@legalmet/config';
import type {
  ComplaintPipeline,
  FindingCategorySlice,
  LocationIntelligence,
  OperationalAnalytics,
  OutcomeSlice,
  RepeatFindingPattern,
  TrendPoint,
} from '@legalmet/types';
import type { Tone } from '@legalmet/config';

import { api } from '../api/client';
import { useApp } from '../app/AppContext';
import { Badge } from '../components/Badge';
import { Card, CardBody, CardHead } from '../components/Card';
import { BarList, DistributionBar, type BarRow } from '../components/charts';
import { Icon } from '../components/Icon';
import { MetricCard } from '../components/MetricCard';
import { PageHeader } from '../components/PageHeader';
import { FilterBar, SelectField } from '../components/inputs';
import type { SelectOption } from '../components/inputs';
import { AsyncView, EmptyState } from '../components/states';
import { useAsync } from '../data/useAsync';
import { formatDateTime, formatPercent, humanizeEnum } from '../lib/format';

const GRANULARITY_OPTIONS: SelectOption[] = [
  { value: 'day', label: 'Daily' },
  { value: 'week', label: 'Weekly' },
  { value: 'month', label: 'Monthly' },
];

const OUTCOME_TONES: Record<string, Tone> = {
  COMPLIANT: 'positive',
  NON_COMPLIANT: 'critical',
  REVIEW_REQUIRED: 'warning',
  NOT_EVALUATED: 'neutral',
};

function outcomeLabel(result: string): string {
  return REPORT_RESULT_META[result]?.label ?? humanizeEnum(result);
}

/** null → N/A — never a fabricated 0% (§14). */
function rateOrNa(rate: number | null | undefined): string {
  return rate == null ? 'N/A' : formatPercent(rate, 1);
}

/** Compact period label for the trend axis. */
function periodLabel(period: string, granularity: string): string {
  if (granularity === 'month') {
    const [, m, y] = period.split('-');
    const names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    const idx = Number(m) - 1;
    return `${names[idx] ?? m} ${y?.slice(2) ?? ''}`;
  }
  if (granularity === 'day') return period.slice(5).replace('-', '/');
  return `W${period.split('-').pop() ?? ''}`;
}

/** §13: inspection trend — vertical bars over the existing chart styles. */
function TrendChart({ points, granularity }: { points: TrendPoint[]; granularity: string }) {
  const VIEW_W = 340;
  const PAD_L = 6;
  const PAD_R = 6;
  const BASE_Y = 104;
  const PLOT_H = 92;
  const plotW = VIEW_W - PAD_L - PAD_R;
  const n = Math.max(points.length, 1);
  const groupW = plotW / n;
  const barW = Math.min(groupW * 0.6, 20);
  const max = Math.max(...points.map((p) => p.count), 1);
  const gridYs = [0, 0.25, 0.5, 0.75, 1];

  return (
    <div className="stack stack--sm">
      <div className="chart">
        <svg viewBox={`0 0 ${VIEW_W} 124`} role="img" aria-label="Inspections over time">
          <g className="chart__grid">
            {gridYs.map((g) => (
              <line
                key={g}
                x1={PAD_L}
                x2={VIEW_W - PAD_R}
                y1={BASE_Y - g * PLOT_H}
                y2={BASE_Y - g * PLOT_H}
              />
            ))}
          </g>
          <g className="chart__axis">
            {points.map((p, i) => {
              const gx = PAD_L + i * groupW + groupW / 2;
              const h = (p.count / max) * PLOT_H;
              return (
                <g key={p.period}>
                  <rect
                    className="chart__bar"
                    x={gx - barW / 2}
                    y={BASE_Y - h}
                    width={barW}
                    height={h}
                    rx={2}
                  >
                    <title>{`${p.period}: ${p.count} inspection${p.count === 1 ? '' : 's'}`}</title>
                  </rect>
                  {points.length <= 14 && (
                    <text x={gx} y={BASE_Y + 14} textAnchor="middle">
                      {periodLabel(p.period, granularity)}
                    </text>
                  )}
                </g>
              );
            })}
          </g>
        </svg>
      </div>
    </div>
  );
}

/** §16: complaint → inspection pipeline — real counts only. */
function PipelineView({ pipeline }: { pipeline: ComplaintPipeline }) {
  const max = Math.max(...pipeline.stages.map((s) => s.count), 1);
  return (
    <div className="pipeline">
      {pipeline.stages.map((s) => (
        <div className="pipeline__row" key={s.stage}>
          <div className="stack" style={{ gap: 2 }}>
            <span className="pipeline__label">{s.label}</span>
            <span className="pipeline__track">
              <span className="pipeline__fill" style={{ width: `${(s.count / max) * 100}%` }} />
            </span>
          </div>
          <span className="pipeline__count">{s.count}</span>
        </div>
      ))}
      <p className="cell-muted" style={{ fontSize: 'var(--fs-sm)' }}>
        Complaint → inspection conversion:{' '}
        <strong>{rateOrNa(pipeline.conversionRate)}</strong>
      </p>
    </div>
  );
}

/** §22: location intelligence — real locations or the honest note. */
function LocationView({ locations }: { locations: LocationIntelligence }) {
  if (!locations.sufficient) {
    return (
      <EmptyState
        icon="risk"
        title="Not enough location data yet."
        message={locations.note ?? 'Not enough geographically-tagged activity yet.'}
      />
    );
  }
  const rows: BarRow[] = locations.locations.map((l) => ({
    label: l.location,
    value: l.complaintCount + l.inspectionCount,
    display: `${l.complaintCount} complaints · ${l.inspectionCount} inspections`,
  }));
  return <BarList rows={rows} />;
}

export function AnalyticsPage() {
  const { isLive } = useApp();
  const [granularity, setGranularity] = useState<'day' | 'week' | 'month'>('month');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [applied, setApplied] = useState<{ dateFrom: string; dateTo: string }>({
    dateFrom: '',
    dateTo: '',
  });

  const query = useAsync(
    () =>
      isLive
        ? api.operationalAnalytics({
            granularity,
            dateFrom: applied.dateFrom || undefined,
            dateTo: applied.dateTo || undefined,
          })
        : Promise.resolve(null),
    [isLive, granularity, applied.dateFrom, applied.dateTo],
  );

  const data = query.data ?? null;

  const outcomeSegments = useMemo(
    () =>
      (data?.outcomes ?? []).map((o: OutcomeSlice) => ({
        label: outcomeLabel(o.result),
        value: o.count,
        tone: OUTCOME_TONES[o.result] ?? 'neutral',
      })),
    [data],
  );

  const categoryRows: BarRow[] = useMemo(
    () =>
      (data?.findingCategories ?? []).map((c: FindingCategorySlice) => ({
        label: `${c.ruleCode} — ${c.label}`,
        value: c.count,
        display:
          c.percentage != null
            ? `${c.count} (${formatPercent(c.percentage, 0)})`
            : String(c.count),
      })),
    [data],
  );

  const repeatRows: BarRow[] = useMemo(
    () =>
      (data?.repeatFindings ?? []).map((r: RepeatFindingPattern) => ({
        label: `${r.productName} — ${r.ruleCode}`,
        value: r.occurrenceCount,
        display: `${r.occurrenceCount} findings across ${r.inspectionCount} inspections`,
        tone: 'warning' as Tone,
      })),
    [data],
  );

  return (
    <div className="page">
      <PageHeader
        eyebrow="Intelligence"
        title="Operational Intelligence"
        lead="Analytics computed from real inspection, complaint, evidence and report records."
        actions={
          <>
            <Link className="btn btn--subtle" to="/reports">
              <Icon name="reports" size={15} />
              View Reports
            </Link>
            <Link className="btn btn--subtle" to="/audit">
              <Icon name="audit" size={15} />
              View Audit Trail
            </Link>
          </>
        }
      />

      {!isLive ? (
        <Card>
          <CardBody>
            <EmptyState
              icon="alert"
              title="Backend unavailable"
              message="Operational analytics are real, database-backed aggregates and require the live backend. Start the API service and reload."
            />
          </CardBody>
        </Card>
      ) : (
        <AsyncView
          query={query}
          loadingLabel="Loading operational analytics…"
          errorTitle="Unable to load operational data."
        >
          {(analytics: OperationalAnalytics | null | undefined) =>
            analytics ? (
              <>
                {/* §12: honest banner when the dataset is small. */}
                {analytics.dataNote && (
                  <Card>
                    <CardBody>
                      <div
                        className="row"
                        style={{ gap: 'var(--space-2)', alignItems: 'center' }}
                        role="note"
                      >
                        <Icon name="info" size={16} />
                        <span>{analytics.dataNote}</span>
                      </div>
                    </CardBody>
                  </Card>
                )}

                {/* §14: KPIs — null rates render N/A, never fake 0%. */}
                <div className="grid grid--metrics">
                  <MetricCard
                    label="Total Inspections"
                    value={analytics.kpis.totalInspections}
                    icon="inspections"
                  />
                  <MetricCard
                    label="Complaint-Led Inspections"
                    value={analytics.kpis.complaintLedInspections}
                    icon="complaints"
                  />
                  <MetricCard
                    label="Compliance Rate"
                    value={rateOrNa(analytics.kpis.complianceRate)}
                    icon="check"
                    hint={`${analytics.kpis.decidedInspections} decided`}
                  />
                  <MetricCard
                    label="Non-Compliance Rate"
                    value={rateOrNa(analytics.kpis.nonComplianceRate)}
                    icon="alert"
                  />
                  <MetricCard
                    label="Review Required"
                    value={analytics.kpis.reviewRequired}
                    icon="review"
                  />
                  <MetricCard
                    label="Open Inspections"
                    value={analytics.kpis.openInspections}
                    icon="clock"
                  />
                  <MetricCard
                    label="Avg Evidence Completeness"
                    value={rateOrNa(analytics.kpis.averageEvidenceCompleteness)}
                    icon="evidence"
                  />
                  <MetricCard
                    label="Reports Blocked by Evidence"
                    value={analytics.evidenceQuality.reportsBlockedByEvidence}
                    icon="scale"
                  />
                </div>

                <Card>
                  <CardHead
                    title="Inspection trend"
                    subtitle="Inspections created per period — real creation timestamps only."
                    actions={
                      <div className="row" style={{ gap: 'var(--space-2)' }}>
                        <SelectField
                          label="Granularity"
                          value={granularity}
                          options={GRANULARITY_OPTIONS}
                          onChange={(g) => setGranularity(g as 'day' | 'week' | 'month')}
                        />
                      </div>
                    }
                  />
                  <CardBody>
                    <FilterBar>
                      <label className="field">
                        <span className="field__label">Date from</span>
                        <input
                          className="input"
                          type="date"
                          value={dateFrom}
                          onChange={(e) => setDateFrom(e.target.value)}
                        />
                      </label>
                      <label className="field">
                        <span className="field__label">Date to</span>
                        <input
                          className="input"
                          type="date"
                          value={dateTo}
                          onChange={(e) => setDateTo(e.target.value)}
                        />
                      </label>
                      <div className="row" style={{ gap: 'var(--space-2)', alignItems: 'flex-end' }}>
                        <button
                          type="button"
                          className="btn btn--primary"
                          onClick={() => setApplied({ dateFrom, dateTo })}
                        >
                          Apply
                        </button>
                        <button
                          type="button"
                          className="btn btn--subtle"
                          onClick={() => {
                            setDateFrom('');
                            setDateTo('');
                            setApplied({ dateFrom: '', dateTo: '' });
                          }}
                        >
                          Clear
                        </button>
                      </div>
                    </FilterBar>
                    {analytics.trend.length > 0 ? (
                      <TrendChart points={analytics.trend} granularity={analytics.granularity} />
                    ) : (
                      <EmptyState
                        icon="inspections"
                        title="Not enough data for this analysis."
                        message="No inspections fall inside the selected date range."
                      />
                    )}
                  </CardBody>
                </Card>

                <div className="grid grid--2">
                  <Card>
                    <CardHead
                      title="Outcome distribution"
                      subtitle="Human decision when recorded, else engine evaluation status."
                    />
                    <CardBody>
                      {outcomeSegments.some((s) => s.value > 0) ? (
                        <DistributionBar segments={outcomeSegments} />
                      ) : (
                        <EmptyState
                          icon="scale"
                          title="Not enough data for this analysis."
                          message="No inspection outcomes have been recorded yet."
                        />
                      )}
                    </CardBody>
                  </Card>

                  <Card>
                    <CardHead
                      title="Complaint → inspection pipeline"
                      subtitle="Every count is a real database record."
                    />
                    <CardBody>
                      <PipelineView pipeline={analytics.complaintPipeline} />
                    </CardBody>
                  </Card>
                </div>

                <Card>
                  <CardHead
                    title="Evidence quality"
                    subtitle="From the evidence planner: what exists, what is missing, what blocks reports."
                  />
                  <CardBody>
                    <div className="grid grid--metrics">
                      <MetricCard
                        label="Inspections with Evidence Plan"
                        value={analytics.evidenceQuality.inspectionsWithPlanner}
                        icon="evidence"
                      />
                      <MetricCard
                        label="Incomplete Inspections"
                        value={analytics.evidenceQuality.incompleteInspections}
                        icon="alert"
                      />
                      <MetricCard
                        label="Missing Required Evidence"
                        value={analytics.evidenceQuality.missingRequiredEvidence}
                        icon="shield"
                      />
                      <MetricCard
                        label="Measurements Pending"
                        value={analytics.evidenceQuality.measurementsPending}
                        icon="clock"
                      />
                    </div>
                  </CardBody>
                </Card>

                <div className="grid grid--2">
                  <Card>
                    <CardHead
                      title="Finding categories"
                      subtitle="Requirements most frequently flagged by the existing rule engine."
                    />
                    <CardBody>
                      {categoryRows.length > 0 ? (
                        <BarList rows={categoryRows} />
                      ) : (
                        <EmptyState
                          icon="review"
                          title="Not enough data for this analysis."
                          message="No engine findings have been recorded yet."
                        />
                      )}
                    </CardBody>
                  </Card>

                  <Card>
                    <CardHead
                      title="Repeated inspection findings"
                      subtitle="Historical patterns across inspections of the same product — not a violator label."
                    />
                    <CardBody>
                      {repeatRows.length > 0 ? (
                        <div className="stack" style={{ gap: 'var(--space-3)' }}>
                          {analytics.repeatFindings.map((r) => (
                            <div key={`${r.productName}-${r.ruleCode}`} className="stack" style={{ gap: 2 }}>
                              <Badge tone="warning" outline>
                                Repeated inspection finding
                              </Badge>
                              <span className="cell-strong">
                                {r.productName} — {r.ruleCode}
                              </span>
                              <span className="cell-muted" style={{ fontSize: 'var(--fs-sm)' }}>
                                {r.label} · {r.occurrenceCount} finding
                                {r.occurrenceCount === 1 ? '' : 's'} across {r.inspectionCount}{' '}
                                inspection{r.inspectionCount === 1 ? '' : 's'}
                              </span>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <EmptyState
                          icon="check"
                          title="No repeated findings."
                          message="No requirement has been flagged on multiple inspections of the same product."
                        />
                      )}
                    </CardBody>
                  </Card>
                </div>

                <div className="grid grid--2">
                  <Card>
                    <CardHead
                      title="Location intelligence"
                      subtitle="Where complaints and inspections are concentrated — real reported locations only."
                    />
                    <CardBody>
                      <LocationView locations={analytics.locations} />
                    </CardBody>
                  </Card>

                  <Card>
                    <CardHead
                      title="Report analytics"
                      subtitle="Real report lifecycle records and export events."
                      actions={
                        <Link className="btn btn--subtle btn--sm" to="/reports">
                          View Reports
                        </Link>
                      }
                    />
                    <CardBody>
                      <div className="grid grid--metrics">
                        <MetricCard label="Generated" value={analytics.reports.generated} icon="reports" />
                        <MetricCard label="Finalized" value={analytics.reports.finalized} icon="check" />
                        <MetricCard label="Amended" value={analytics.reports.amended} icon="edit" />
                        <MetricCard
                          label="PDF / DOCX Exports"
                          value={`${analytics.reports.pdfExports} / ${analytics.reports.docxExports}`}
                          icon="download"
                        />
                      </div>
                    </CardBody>
                  </Card>
                </div>

                <Card>
                  <CardBody>
                    <div
                      className="row"
                      style={{
                        justifyContent: 'space-between',
                        gap: 'var(--space-3)',
                        flexWrap: 'wrap',
                      }}
                    >
                      <span className="cell-muted" style={{ fontSize: 'var(--fs-sm)' }}>
                        Generated {formatDateTime(analytics.generatedAt)} · every figure is a
                        server-side count over real records. Export of analytics is a future-ready
                        action — it activates when the reporting pipeline supports it.
                      </span>
                      <button type="button" className="btn btn--subtle" disabled title="Not yet available">
                        <Icon name="download" size={15} />
                        Export Analytics
                      </button>
                    </div>
                  </CardBody>
                </Card>
              </>
            ) : (
              <Card>
                <CardBody>
                  <EmptyState
                    icon="alert"
                    title="Unable to load operational data."
                    message="The analytics service did not return data. Retry, or check the backend logs."
                  />
                </CardBody>
              </Card>
            )
          }
        </AsyncView>
      )}
    </div>
  );
}
