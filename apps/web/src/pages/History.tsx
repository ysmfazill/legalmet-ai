/**
 * UI-09 §6-§8, §25 — INSPECTION HISTORY.
 *
 * Search and review historical inspection activity: real KPIs (COUNT()s over
 * the filtered set, computed server-side), the spec's table columns, filters
 * that persist in the URL query string, server-side pagination, and the
 * per-inspection timeline built ONLY from events actually recorded in the
 * database — nothing is fabricated.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';

import {
  INSPECTION_STATUS_META,
  REPORT_RESULT_META,
  REPORT_STATUS_META,
} from '@legalmet/config';
import { INSPECTION_STATUSES } from '@legalmet/types';
import type {
  AssignableInspector,
  InspectionHistoryItem,
  InspectionTimeline,
} from '@legalmet/types';
import type { Tone } from '@legalmet/config';

import { api } from '../api/client';
import { useApp } from '../app/AppContext';
import { Badge } from '../components/Badge';
import { Card, CardBody } from '../components/Card';
import { DataTable, type Column } from '../components/DataTable';
import { Drawer } from '../components/Drawer';
import { Icon } from '../components/Icon';
import { MetricCard } from '../components/MetricCard';
import { PageHeader } from '../components/PageHeader';
import { FilterBar, SearchBar, SelectField } from '../components/inputs';
import type { SelectOption } from '../components/inputs';
import { AsyncView, EmptyState } from '../components/states';
import { useAsync } from '../data/useAsync';
import { formatDate, formatDateTime, humanizeEnum } from '../lib/format';

const PAGE_SIZE = 20;

const RESULT_OPTIONS: SelectOption[] = [
  { value: '', label: 'All results' },
  { value: 'COMPLIANT', label: 'Compliant' },
  { value: 'NON_COMPLIANT', label: 'Non-Compliant' },
  { value: 'REVIEW_REQUIRED', label: 'Review Required' },
  { value: 'NOT_EVALUATED', label: 'Not Evaluated' },
];

const STATUS_OPTIONS: SelectOption[] = [
  { value: '', label: 'All statuses' },
  ...INSPECTION_STATUSES.map((s) => ({
    value: s,
    label: INSPECTION_STATUS_META[s].label,
  })),
];

const SOURCE_OPTIONS: SelectOption[] = [
  { value: '', label: 'All sources' },
  { value: 'DIRECT_INSPECTION', label: 'Direct Inspection' },
  { value: 'CITIZEN_COMPLAINT', label: 'Citizen Complaint' },
];

function resultTone(result: string): Tone {
  return (REPORT_RESULT_META[result] ?? { tone: 'neutral' }).tone;
}

function resultLabel(result: string): string {
  return REPORT_RESULT_META[result]?.label ?? humanizeEnum(result);
}

function reportStatusLabel(status: string): string {
  return (
    (REPORT_STATUS_META as Record<string, { label: string }>)[status]?.label ??
    humanizeEnum(status)
  );
}

function statusTone(status: string): Tone {
  return (
    INSPECTION_STATUS_META[status as keyof typeof INSPECTION_STATUS_META] ?? {
      tone: 'neutral',
    }
  ).tone;
}

function statusLabel(status: string): string {
  return (
    INSPECTION_STATUS_META[status as keyof typeof INSPECTION_STATUS_META]?.label ??
    humanizeEnum(status)
  );
}

/** §25: the filter state lives in the URL — /history?result=NON_COMPLIANT&source=CITIZEN_COMPLAINT */
function filtersFromParams(params: URLSearchParams) {
  return {
    q: params.get('q') ?? '',
    status: params.get('status') ?? '',
    result: params.get('result') ?? '',
    source: params.get('source') ?? '',
    inspectorId: params.get('inspectorId') ?? '',
    dateFrom: params.get('dateFrom') ?? '',
    dateTo: params.get('dateTo') ?? '',
    page: Number(params.get('page') ?? '1') || 1,
  };
}

/** §8 timeline: the recorded chain, shown as a drawer from the history table. */
function TimelineDrawer({
  inspectionId,
  onClose,
}: {
  inspectionId: string | null;
  onClose: () => void;
}) {
  const query = useAsync(
    () => (inspectionId ? api.inspectionTimeline(inspectionId) : Promise.resolve(null)),
    [inspectionId],
  );
  if (!inspectionId) return null;
  return (
    <Drawer title="Inspection timeline" onClose={onClose} wide>
      <AsyncView query={query} loadingLabel="Loading timeline…">
        {(timeline: InspectionTimeline | null) =>
          timeline && timeline.events.length > 0 ? (
            <>
              <p className="cell-muted" style={{ marginBottom: 'var(--space-4)' }}>
                {timeline.reference} — only events actually recorded in the database
                are shown. If an event does not exist, it is not fabricated.
              </p>
              <ul className="htimeline">
                {timeline.events.map((e, i) => (
                  <li className="htimeline__item" key={`${e.stage}-${i}`}>
                    <span
                      className={
                        e.stage === 'DECISION'
                          ? 'htimeline__dot htimeline__dot--decision'
                          : e.stage.startsWith('REPORT')
                            ? 'htimeline__dot htimeline__dot--report'
                            : 'htimeline__dot'
                      }
                      aria-hidden
                    />
                    <div className="htimeline__body">
                      <span className="htimeline__label">{e.label}</span>
                      <span className="htimeline__meta">
                        {formatDateTime(e.at)}
                        {e.actorName ? ` · ${e.actorName}` : ''}
                      </span>
                      {e.detail && <span className="htimeline__meta">{e.detail}</span>}
                      {e.decision && (
                        <Badge tone={resultTone(e.decision)}>{resultLabel(e.decision)}</Badge>
                      )}
                      {e.reportId && (
                        <Link className="btn btn--subtle btn--sm" to={`/reports/${e.reportId}`}>
                          <Icon name="reports" size={14} />
                          View report
                        </Link>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            </>
          ) : (
            <EmptyState
              icon="clock"
              title="No timeline events recorded."
              message="This inspection has no recorded activity beyond its creation."
            />
          )
        }
      </AsyncView>
    </Drawer>
  );
}

export function HistoryPage() {
  const { isLive } = useApp();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();

  const filters = filtersFromParams(params);

  // Local draft state — applied to the URL on [Apply] (§25).
  const [draft, setDraft] = useState(filters);
  useEffect(() => setDraft(filtersFromParams(params)), [params]);

  const inspectorsQuery = useAsync(
    () => (isLive ? api.complaintInspectors() : Promise.resolve([])),
    [isLive],
  );
  const inspectorOptions: SelectOption[] = useMemo(() => {
    const list = (inspectorsQuery.data ?? []) as AssignableInspector[];
    return [
      { value: '', label: 'All inspectors' },
      ...list.map((i) => ({ value: i.id, label: i.fullName })),
    ];
  }, [inspectorsQuery.data]);

  const historyQuery = useAsync(
    () =>
      isLive
        ? api.inspectionHistory({
            q: filters.q || undefined,
            status: filters.status || undefined,
            result: filters.result || undefined,
            source: filters.source || undefined,
            inspectorId: filters.inspectorId || undefined,
            dateFrom: filters.dateFrom || undefined,
            dateTo: filters.dateTo || undefined,
            page: filters.page,
            pageSize: PAGE_SIZE,
          })
        : Promise.resolve(null),
    [
      isLive,
      filters.q,
      filters.status,
      filters.result,
      filters.source,
      filters.inspectorId,
      filters.dateFrom,
      filters.dateTo,
      filters.page,
    ],
  );

  const [timelineFor, setTimelineFor] = useState<string | null>(null);

  const apply = useCallback(() => {
    const next = new URLSearchParams();
    if (draft.q) next.set('q', draft.q);
    if (draft.status) next.set('status', draft.status);
    if (draft.result) next.set('result', draft.result);
    if (draft.source) next.set('source', draft.source);
    if (draft.inspectorId) next.set('inspectorId', draft.inspectorId);
    if (draft.dateFrom) next.set('dateFrom', draft.dateFrom);
    if (draft.dateTo) next.set('dateTo', draft.dateTo);
    setParams(next, { replace: false });
  }, [draft, setParams]);

  const clear = useCallback(() => setParams(new URLSearchParams()), [setParams]);

  const goToPage = useCallback(
    (page: number) => {
      const next = new URLSearchParams(params);
      if (page > 1) next.set('page', String(page));
      else next.delete('page');
      setParams(next, { replace: false });
    },
    [params, setParams],
  );

  const items = historyQuery.data?.items ?? [];
  const kpis = historyQuery.data?.kpis;
  const total = historyQuery.data?.total ?? 0;
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const columns = useMemo<Column<InspectionHistoryItem>[]>(
    () => [
      {
        key: 'reference',
        header: 'Inspection ID',
        render: (r) => (
          <div>
            <Link className="cell-strong" to={`/inspections/${r.id}`}>
              {r.reference}
            </Link>
            {r.sourceComplaintReference && (
              <div className="cell-muted" style={{ fontSize: 'var(--fs-sm)' }}>
                from {r.sourceComplaintReference}
              </div>
            )}
          </div>
        ),
      },
      {
        key: 'date',
        header: 'Date',
        render: (r) => <span className="cell-muted">{formatDate(r.createdAt)}</span>,
      },
      {
        key: 'product',
        header: 'Product',
        render: (r) => r.productName ?? <span className="cell-muted">—</span>,
      },
      {
        key: 'establishment',
        header: 'Establishment',
        render: (r) => r.establishment ?? <span className="cell-muted">—</span>,
      },
      {
        key: 'inspector',
        header: 'Inspector',
        render: (r) => r.inspectorName ?? <span className="cell-muted">—</span>,
      },
      {
        key: 'source',
        header: 'Source',
        render: (r) => (
          <Badge tone={r.source === 'CITIZEN_COMPLAINT' ? 'info' : 'neutral'} outline>
            {r.source === 'CITIZEN_COMPLAINT' ? 'Citizen Complaint' : 'Direct Inspection'}
          </Badge>
        ),
      },
      {
        key: 'result',
        header: 'Result',
        render: (r) => (
          <Badge tone={resultTone(r.result)}>{resultLabel(r.result)}</Badge>
        ),
      },
      {
        key: 'evidence',
        header: 'Evidence',
        render: (r) => (
          <span className="cell-muted" title="Captured package images">
            <Icon name="image" size={13} /> {r.imageCount}
          </span>
        ),
      },
      {
        key: 'report',
        header: 'Report',
        render: (r) =>
          r.report ? (
            <Link className="btn btn--subtle btn--sm" to={`/reports/${r.report.id}`}>
              {reportStatusLabel(r.report.status)} · v{r.report.version}
            </Link>
          ) : (
            <span className="cell-muted">—</span>
          ),
      },
      {
        key: 'status',
        header: 'Status',
        render: (r) => (
          <Badge tone={statusTone(r.status)} dot>
            {statusLabel(r.status)}
          </Badge>
        ),
      },
      {
        key: 'actions',
        header: 'Timeline',
        align: 'right',
        render: (r) => (
          <button
            type="button"
            className="btn btn--subtle btn--sm"
            onClick={(e) => {
              e.stopPropagation();
              setTimelineFor(r.id);
            }}
          >
            <Icon name="clock" size={14} />
            View
          </button>
        ),
      },
    ],
    [],
  );

  return (
    <div className="page">
      <PageHeader
        eyebrow="Intelligence"
        title="Inspection History"
        lead="Search and review historical inspection activity."
      />

      {!isLive ? (
        <Card>
          <CardBody>
            <EmptyState
              icon="alert"
              title="Backend unavailable"
              message="Inspection history is real, database-backed data and requires the live backend. Start the API service and reload."
            />
          </CardBody>
        </Card>
      ) : (
        <>
          {kpis && (
            <div className="grid grid--metrics">
              <MetricCard label="Total" value={kpis.total} icon="inspections" />
              <MetricCard label="Compliant" value={kpis.compliant} icon="check" />
              <MetricCard label="Non-Compliant" value={kpis.nonCompliant} icon="alert" />
              <MetricCard label="Review Required" value={kpis.reviewRequired} icon="review" />
              <MetricCard label="Open" value={kpis.open} icon="clock" />
            </div>
          )}

          {/* §25: reusable filter bar; state persists in the URL. */}
          <Card>
            <CardBody>
              <FilterBar>
                <SearchBar
                  value={draft.q}
                  onChange={(q) => setDraft((d) => ({ ...d, q }))}
                  placeholder="Search reference or product…"
                  ariaLabel="Search history"
                />
                <SelectField
                  label="Status"
                  value={draft.status}
                  options={STATUS_OPTIONS}
                  onChange={(status) => setDraft((d) => ({ ...d, status }))}
                />
                <SelectField
                  label="Result"
                  value={draft.result}
                  options={RESULT_OPTIONS}
                  onChange={(result) => setDraft((d) => ({ ...d, result }))}
                />
                <SelectField
                  label="Source"
                  value={draft.source}
                  options={SOURCE_OPTIONS}
                  onChange={(source) => setDraft((d) => ({ ...d, source }))}
                />
                <SelectField
                  label="Inspector"
                  value={draft.inspectorId}
                  options={inspectorOptions}
                  onChange={(inspectorId) => setDraft((d) => ({ ...d, inspectorId }))}
                />
                <label className="field">
                  <span className="field__label">Date from</span>
                  <input
                    className="input"
                    type="date"
                    value={draft.dateFrom}
                    onChange={(e) => setDraft((d) => ({ ...d, dateFrom: e.target.value }))}
                  />
                </label>
                <label className="field">
                  <span className="field__label">Date to</span>
                  <input
                    className="input"
                    type="date"
                    value={draft.dateTo}
                    onChange={(e) => setDraft((d) => ({ ...d, dateTo: e.target.value }))}
                  />
                </label>
                <div className="row" style={{ gap: 'var(--space-2)', alignItems: 'flex-end' }}>
                  <button type="button" className="btn btn--primary" onClick={apply}>
                    Apply
                  </button>
                  <button type="button" className="btn btn--subtle" onClick={clear}>
                    Clear
                  </button>
                </div>
              </FilterBar>
            </CardBody>
          </Card>

          <AsyncView query={historyQuery} loadingLabel="Loading inspection history…">
            {(data) =>
              data && data.items.length > 0 ? (
                <Card>
                  <CardBody flush>
                    <DataTable
                      columns={columns}
                      rows={items}
                      getRowId={(r) => r.id}
                      onRowClick={(r) => navigate(`/inspections/${r.id}`)}
                      ariaLabel="Inspection history"
                    />
                    {pageCount > 1 && (
                      <div
                        className="row"
                        style={{
                          justifyContent: 'space-between',
                          padding: 'var(--space-3)',
                          borderTop: '1px solid var(--border)',
                        }}
                      >
                        <span className="cell-muted">
                          Page {filters.page} of {pageCount} · {total} inspections
                        </span>
                        <span className="row" style={{ gap: 'var(--space-2)' }}>
                          <button
                            type="button"
                            className="btn btn--subtle btn--sm"
                            disabled={filters.page <= 1}
                            onClick={() => goToPage(filters.page - 1)}
                          >
                            <Icon name="chevronLeft" size={14} />
                            Previous
                          </button>
                          <button
                            type="button"
                            className="btn btn--subtle btn--sm"
                            disabled={filters.page >= pageCount}
                            onClick={() => goToPage(filters.page + 1)}
                          >
                            Next
                            <Icon name="chevronRight" size={14} />
                          </button>
                        </span>
                      </div>
                    )}
                  </CardBody>
                </Card>
              ) : (
                <Card>
                  <CardBody>
                    <EmptyState
                      icon="inspections"
                      title="No inspections found for the selected filters."
                      message="Adjust or clear the filters to see more historical activity."
                      action={
                        <button type="button" className="btn btn--subtle" onClick={clear}>
                          <Icon name="reset" size={15} />
                          Clear filters
                        </button>
                      }
                    />
                  </CardBody>
                </Card>
              )
            }
          </AsyncView>
        </>
      )}

      <TimelineDrawer inspectionId={timelineFor} onClose={() => setTimelineFor(null)} />
    </div>
  );
}
