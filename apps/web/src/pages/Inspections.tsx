import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';

import { INSPECTION_STATUS_META } from '@legalmet/config';
import { INSPECTION_STATUSES } from '@legalmet/types';
import type { Inspection } from '@legalmet/types';

import { Card, CardBody } from '../components/Card';
import { Icon } from '../components/Icon';
import { FilterBar, SearchBar, SelectField } from '../components/inputs';
import type { SelectOption } from '../components/inputs';
import { InspectionTable } from '../components/InspectionTable';
import { PageHeader } from '../components/PageHeader';
import { AsyncView, EmptyState } from '../components/states';
import { useAsync } from '../data/useAsync';
import { mockApi } from '../mock/adapter';

const PAGE_SIZE = 6;

const STATUS_OPTIONS: SelectOption[] = [
  { value: '', label: 'All statuses' },
  ...INSPECTION_STATUSES.map((s) => ({ value: s, label: INSPECTION_STATUS_META[s].label })),
];

export function InspectionsPage() {
  const query = useAsync(() => mockApi.listInspections(), []);
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const qParam = params.get('q') ?? '';

  const [search, setSearch] = useState(qParam);
  const [status, setStatus] = useState('');
  const [category, setCategory] = useState('');
  const [page, setPage] = useState(1);

  // Keep the search box in sync with the top-bar global search (`?q=`).
  useEffect(() => setSearch(qParam), [qParam]);
  // Any filter change returns to the first page.
  useEffect(() => setPage(1), [search, status, category]);

  return (
    <div className="page">
      <PageHeader
        eyebrow="Casework"
        title="Inspections"
        lead="Browse and filter packaged-commodity inspections. Open any inspection to review its evidence and findings."
        actions={
          <button type="button" className="btn btn--primary" onClick={() => navigate('/inspections/new')}>
            <Icon name="plus" size={16} />
            New inspection
          </button>
        }
      />

      <AsyncView query={query} loadingLabel="Loading inspections…">
        {(all) => {
          const categories = Array.from(
            new Set(all.map((i) => i.product?.category).filter((c): c is string => Boolean(c))),
          ).sort();
          const categoryOptions: SelectOption[] = [
            { value: '', label: 'All categories' },
            ...categories.map((c) => ({ value: c, label: c })),
          ];
          return (
            <InspectionsBody
              all={all}
              search={search}
              status={status}
              category={category}
              page={page}
              categoryOptions={categoryOptions}
              onSearch={(v) => {
                setSearch(v);
                setParams(v ? { q: v } : {}, { replace: true });
              }}
              onStatus={setStatus}
              onCategory={setCategory}
              onPage={setPage}
              onClear={() => {
                setSearch('');
                setStatus('');
                setCategory('');
                setParams({}, { replace: true });
              }}
              onOpen={(id) => navigate(`/inspections/${id}`)}
            />
          );
        }}
      </AsyncView>
    </div>
  );
}

function InspectionsBody({
  all,
  search,
  status,
  category,
  page,
  categoryOptions,
  onSearch,
  onStatus,
  onCategory,
  onPage,
  onClear,
  onOpen,
}: {
  all: Inspection[];
  search: string;
  status: string;
  category: string;
  page: number;
  categoryOptions: SelectOption[];
  onSearch: (v: string) => void;
  onStatus: (v: string) => void;
  onCategory: (v: string) => void;
  onPage: (n: number) => void;
  onClear: () => void;
  onOpen: (id: string) => void;
}) {
  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return all.filter(
      (i) =>
        (!status || i.status === status) &&
        (!category || i.product?.category === category) &&
        (!q ||
          i.referenceNo.toLowerCase().includes(q) ||
          (i.product?.name.toLowerCase().includes(q) ?? false)),
    );
  }, [all, search, status, category]);

  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const current = Math.min(page, pageCount);
  const rows = filtered.slice((current - 1) * PAGE_SIZE, current * PAGE_SIZE);
  const hasFilters = Boolean(search || status || category);

  return (
    <Card>
      <CardBody flush>
        <FilterBar>
          <SearchBar
            value={search}
            onChange={onSearch}
            placeholder="Search reference or product…"
            ariaLabel="Search inspections"
            className="filter-bar__search"
          />
          <SelectField label="Status" value={status} options={STATUS_OPTIONS} onChange={onStatus} />
          <SelectField label="Category" value={category} options={categoryOptions} onChange={onCategory} />
          <span className="spacer" />
          {hasFilters && (
            <button type="button" className="btn btn--ghost btn--sm" onClick={onClear}>
              <Icon name="close" size={14} />
              Clear
            </button>
          )}
        </FilterBar>

        {rows.length === 0 ? (
          <div style={{ padding: 'var(--space-6)' }}>
            <EmptyState
              icon="inspections"
              title="No inspections match"
              message="Try adjusting the search or filters."
              action={
                hasFilters ? (
                  <button type="button" className="btn btn--subtle btn--sm" onClick={onClear}>
                    Clear filters
                  </button>
                ) : undefined
              }
            />
          </div>
        ) : (
          <>
            <InspectionTable inspections={rows} onOpen={onOpen} />
            <div className="row row--between" style={{ padding: 'var(--space-3) var(--space-4)' }}>
              <span className="cell-muted" style={{ fontSize: 'var(--fs-sm)' }}>
                Showing {rows.length} of {filtered.length}
              </span>
              <div className="row" style={{ gap: 'var(--space-2)' }}>
                <button
                  type="button"
                  className="btn btn--subtle btn--sm"
                  disabled={current <= 1}
                  onClick={() => onPage(current - 1)}
                >
                  <Icon name="chevronLeft" size={14} />
                  Prev
                </button>
                <span className="cell-muted" style={{ fontSize: 'var(--fs-sm)', alignSelf: 'center' }}>
                  Page {current} of {pageCount}
                </span>
                <button
                  type="button"
                  className="btn btn--subtle btn--sm"
                  disabled={current >= pageCount}
                  onClick={() => onPage(current + 1)}
                >
                  Next
                  <Icon name="chevronRight" size={14} />
                </button>
              </div>
            </div>
          </>
        )}
      </CardBody>
    </Card>
  );
}
