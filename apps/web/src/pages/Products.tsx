/**
 * UI-09 §9 — PRODUCT REPOSITORY (list).
 *
 * "Search packages and review their inspection history." Real aggregate counts
 * per product; server-side search + pagination. Each row links to the product
 * detail page (/products/:id) — the historical record, never a compliance
 * claim about the current package.
 */
import { useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import { REPORT_RESULT_META } from '@legalmet/config';
import type { ProductSummary } from '@legalmet/types';
import type { Tone } from '@legalmet/config';

import { api } from '../api/client';
import { useApp } from '../app/AppContext';
import { Badge } from '../components/Badge';
import { Card, CardBody } from '../components/Card';
import { DataTable, type Column } from '../components/DataTable';
import { Icon } from '../components/Icon';
import { PageHeader } from '../components/PageHeader';
import { FilterBar, SearchBar } from '../components/inputs';
import { AsyncView, EmptyState } from '../components/states';
import { useAsync } from '../data/useAsync';
import { formatRelative, humanizeEnum } from '../lib/format';

const PAGE_SIZE = 20;

function resultTone(result: string): Tone {
  return (REPORT_RESULT_META[result] ?? { tone: 'neutral' }).tone;
}

function resultLabel(result: string): string {
  return REPORT_RESULT_META[result]?.label ?? humanizeEnum(result);
}

export function ProductsPage() {
  const { isLive } = useApp();
  const navigate = useNavigate();
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);

  // §29: search + pagination are server-side.
  const listQuery = useAsync(
    () =>
      isLive
        ? api.listProducts({ q: search.trim() || undefined, page, pageSize: PAGE_SIZE })
        : Promise.resolve(null),
    [isLive, search, page],
  );

  const items = listQuery.data?.items ?? [];
  const total = listQuery.data?.total ?? 0;
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const columns = useMemo<Column<ProductSummary>[]>(
    () => [
      {
        key: 'name',
        header: 'Product',
        render: (p) => (
          <div>
            <Link className="cell-strong" to={`/products/${p.id}`}>
              {p.name}
            </Link>
            <div className="cell-muted" style={{ fontSize: 'var(--fs-sm)' }}>
              {p.category}
              {p.gtin ? ` · GTIN ${p.gtin}` : ''}
            </div>
          </div>
        ),
      },
      {
        key: 'inspections',
        header: 'Inspections',
        render: (p) => p.inspectionCount,
      },
      {
        key: 'findings',
        header: 'Findings',
        render: (p) => p.findingCount,
      },
      {
        key: 'last',
        header: 'Last Inspected',
        render: (p) =>
          p.lastInspectionAt ? (
            <span className="cell-muted">{formatRelative(p.lastInspectionAt)}</span>
          ) : (
            <span className="cell-muted">Never</span>
          ),
      },
      {
        key: 'latest',
        header: 'Latest Result',
        render: (p) => (
          <Badge tone={resultTone(p.latestResult)}>{resultLabel(p.latestResult)}</Badge>
        ),
      },
      {
        key: 'actions',
        header: 'Actions',
        align: 'right',
        render: (p) => (
          <Link className="btn btn--subtle btn--sm" to={`/products/${p.id}`}>
            <Icon name="eye" size={14} />
            View history
          </Link>
        ),
      },
    ],
    [],
  );

  return (
    <div className="page">
      <PageHeader
        eyebrow="Intelligence"
        title="Product Repository"
        lead="Search packages and review their inspection history."
      />

      {!isLive ? (
        <Card>
          <CardBody>
            <EmptyState
              icon="alert"
              title="Backend unavailable"
              message="The product repository is real, database-backed data and requires the live backend. Start the API service and reload."
            />
          </CardBody>
        </Card>
      ) : (
        <>
          <Card>
            <CardBody>
              <FilterBar>
                <SearchBar
                  value={search}
                  onChange={(v) => {
                    setSearch(v);
                    setPage(1);
                  }}
                  placeholder="Search product name, category or GTIN…"
                  ariaLabel="Search products"
                />
              </FilterBar>
            </CardBody>
          </Card>

          <AsyncView query={listQuery} loadingLabel="Loading products…">
            {(data) =>
              data && data.items.length > 0 ? (
                <Card>
                  <CardBody flush>
                    <DataTable
                      columns={columns}
                      rows={items}
                      getRowId={(p) => p.id}
                      onRowClick={(p) => navigate(`/products/${p.id}`)}
                      ariaLabel="Product repository"
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
                          Page {page} of {pageCount} · {total} products
                        </span>
                        <span className="row" style={{ gap: 'var(--space-2)' }}>
                          <button
                            type="button"
                            className="btn btn--subtle btn--sm"
                            disabled={page <= 1}
                            onClick={() => setPage((p) => p - 1)}
                          >
                            <Icon name="chevronLeft" size={14} />
                            Previous
                          </button>
                          <button
                            type="button"
                            className="btn btn--subtle btn--sm"
                            disabled={page >= pageCount}
                            onClick={() => setPage((p) => p + 1)}
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
                      icon="package"
                      title="No product records available."
                      message={
                        search.trim()
                          ? 'No products match the current search.'
                          : 'Products appear here once inspections record their packages.'
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
