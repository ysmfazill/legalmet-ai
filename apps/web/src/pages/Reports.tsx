/**
 * Report Center (UI-08 §2, §3, §20, §25).
 *
 * The /reports list: real records only. KPIs are live group-by counts from
 * the reports table — never fabricated numbers. Each row links to the report
 * detail page (/reports/:id) where generation, the finalization gate,
 * exports and the evidence pack live.
 *
 * The mock/demo adapter is NOT consulted here: a report is an official,
 * traceable artifact, and only real backend records may be listed.
 */
import { useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import { REPORT_STATUS_META, REPORT_RESULT_META } from '@legalmet/config';
import { REPORT_STATUSES } from '@legalmet/types';
import type { ReportSummary } from '@legalmet/types';
import type { Tone } from '@legalmet/config';

import { api } from '../api/client';
import { useApp } from '../app/AppContext';
import { Badge } from '../components/Badge';
import { Card, CardBody } from '../components/Card';
import { DataTable, type Column } from '../components/DataTable';
import { Icon } from '../components/Icon';
import { MetricCard } from '../components/MetricCard';
import { PageHeader } from '../components/PageHeader';
import { SearchBar, SelectField, FilterBar } from '../components/inputs';
import type { SelectOption } from '../components/inputs';
import { AsyncView, EmptyState } from '../components/states';
import { useAsync } from '../data/useAsync';
import { formatRelative, humanizeEnum } from '../lib/format';

const STATUS_OPTIONS: SelectOption[] = [
  { value: '', label: 'All statuses' },
  ...REPORT_STATUSES.map((s) => ({ value: s, label: REPORT_STATUS_META[s].label })),
];

function statusTone(status: string): Tone {
  return (REPORT_STATUS_META[status as keyof typeof REPORT_STATUS_META] ?? { tone: 'neutral' }).tone;
}

function resultTone(result: string): Tone {
  return (REPORT_RESULT_META[result] ?? { tone: 'neutral' }).tone;
}

export function ReportsPage() {
  const { isLive, user } = useApp();
  const navigate = useNavigate();

  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('');

  // §20: search + filter server-side. Refetch when either changes.
  const listQuery = useAsync(
    () =>
      isLive
        ? api.listReports({ q: search.trim() || undefined, status: status || undefined, pageSize: 100 })
        : Promise.resolve(null),
    [isLive, search, status],
  );
  const kpiQuery = useAsync(
    () => (isLive ? api.reportKpis() : Promise.resolve(null)),
    [isLive],
  );

  const reports = listQuery.data?.items ?? [];
  const kpis = kpiQuery.data;

  const columns = useMemo<Column<ReportSummary>[]>(
    () => [
      {
        key: 'reference',
        header: 'Report',
        render: (r) => (
          <div>
            <Link className="cell-strong" to={`/reports/${r.id}`}>
              {r.inspectionReference || 'Report'}
            </Link>
            <div className="cell-muted" style={{ fontSize: 'var(--fs-sm)' }}>
              v{r.version} · {r.evidenceCount} evidence items
            </div>
          </div>
        ),
      },
      {
        key: 'product',
        header: 'Product / Package',
        render: (r) => r.productName ?? <span className="cell-muted">—</span>,
      },
      {
        key: 'inspectionDate',
        header: 'Inspection Date',
        render: (r) => <span className="cell-muted">{formatRelative(r.inspectionDate)}</span>,
      },
      {
        key: 'inspector',
        header: 'Inspector',
        render: (r) => r.inspectorName ?? <span className="cell-muted">—</span>,
      },
      {
        key: 'result',
        header: 'Result',
        render: (r) => (
          <Badge tone={resultTone(r.result)}>
            {REPORT_RESULT_META[r.result]?.label ?? humanizeEnum(r.result)}
          </Badge>
        ),
      },
      {
        key: 'evidence',
        header: 'Evidence Status',
        render: (r) =>
          r.generatedAt ? (
            <Badge tone="positive" outline>
              {r.evidenceCount} items frozen
            </Badge>
          ) : (
            <Badge tone="warning" outline>
              Not generated
            </Badge>
          ),
      },
      {
        key: 'status',
        header: 'Report Status',
        render: (r) => (
          <Badge tone={statusTone(r.status)} dot>
            {REPORT_STATUS_META[r.status]?.label ?? humanizeEnum(r.status)}
          </Badge>
        ),
      },
      {
        key: 'updated',
        header: 'Last Updated',
        render: (r) => <span className="cell-muted">{formatRelative(r.updatedAt)}</span>,
      },
      {
        key: 'actions',
        header: 'Actions',
        align: 'right',
        render: (r) => (
          <Link className="btn btn--subtle btn--sm" to={`/reports/${r.id}`}>
            <Icon name="eye" size={14} />
            View
          </Link>
        ),
      },
    ],
    [],
  );

  return (
    <div className="page">
      <PageHeader
        eyebrow="Output"
        title="Reports"
        lead="Generate, review and export evidence-backed inspection reports."
        actions={
          <Link className="btn btn--primary" to="/inspections">
            <Icon name="inspections" size={16} />
            Generate Report
          </Link>
        }
      />

      {!isLive ? (
        <Card>
          <CardBody>
            <EmptyState
              icon="alert"
              title="Backend unavailable"
              message="Reports are real, traceable records and require the live backend. Start the API service and reload."
            />
          </CardBody>
        </Card>
      ) : (
        <>
          {/* §2: KPIs from real DB records — no fabricated numbers. */}
          {kpis && (
            <div className="grid grid--metrics">
              <MetricCard label="Total Reports" value={kpis.total} icon="reports" />
              <MetricCard label="Draft" value={kpis.draft} icon="edit" />
              <MetricCard label="Finalized" value={kpis.finalized} icon="check" />
              <MetricCard label="Exported" value={kpis.exported} icon="download" />
              <MetricCard
                label="Requires Review"
                value={kpis.underReview + kpis.amended}
                icon="alert"
                hint="Under review or amended"
              />
            </div>
          )}

          <Card>
            <CardBody>
              <FilterBar>
                <SearchBar
                  value={search}
                  onChange={setSearch}
                  placeholder="Search report ID, inspection, product or inspector…"
                  ariaLabel="Search reports"
                />
                <SelectField
                  label="Status"
                  value={status}
                  options={STATUS_OPTIONS}
                  onChange={setStatus}
                />
              </FilterBar>
            </CardBody>
          </Card>

          <AsyncView query={listQuery} loadingLabel="Loading reports…">
            {(list) =>
              list && list.items.length > 0 ? (
                <Card>
                  <CardBody flush>
                    <DataTable
                      columns={columns}
                      rows={reports}
                      getRowId={(r) => r.id}
                      onRowClick={(r) => navigate(`/reports/${r.id}`)}
                      ariaLabel="Inspection reports"
                    />
                  </CardBody>
                </Card>
              ) : (
                <Card>
                  <CardBody>
                    <EmptyState
                      icon="reports"
                      title="No finalized reports yet."
                      message={
                        reports.length === 0
                          ? 'Open an inspection, generate and finalize its report — it will appear here.'
                          : 'No reports match the current filters.'
                      }
                      action={
                        reports.length === 0 && user.role !== 'AUDITOR' ? (
                          <Link className="btn btn--primary" to="/inspections">
                            <Icon name="inspections" size={15} />
                            Open Inspection
                          </Link>
                        ) : undefined
                      }
                    />
                  </CardBody>
                </Card>
              )
            }
          </AsyncView>
        </>
      )}
    </div>
  );
}
