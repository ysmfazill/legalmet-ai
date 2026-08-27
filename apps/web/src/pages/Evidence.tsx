import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { FIELD_TYPE_LABELS } from '@legalmet/config';
import type { FieldType } from '@legalmet/types';

import { ConfidenceMeter, DemoBadge, StatusBadge } from '../components/Badge';
import { Card, CardBody } from '../components/Card';
import { Icon } from '../components/Icon';
import { FilterBar, SearchBar, SelectField } from '../components/inputs';
import type { SelectOption } from '../components/inputs';
import { PageHeader } from '../components/PageHeader';
import { AsyncView, EmptyState } from '../components/states';
import { useAsync } from '../data/useAsync';
import { mockApi } from '../mock/adapter';
import type { EvidenceItem } from '../mock/types';

export function EvidencePage() {
  const query = useAsync(() => mockApi.getEvidenceItems(), []);
  const navigate = useNavigate();
  const [search, setSearch] = useState('');
  const [field, setField] = useState('');

  return (
    <div className="page">
      <PageHeader
        eyebrow="Extraction"
        title="Evidence Explorer"
        lead="Every value the system extracted from a package label, with the region it came from and its detection confidence. Open an item to see it in the inspection workspace."
        actions={<DemoBadge label="DEMO EVIDENCE" />}
      />

      <AsyncView query={query} loadingLabel="Loading evidence…">
        {(items) => {
          const fieldOptions: SelectOption[] = [
            { value: '', label: 'All fields' },
            ...Array.from(new Set(items.map((i) => i.fieldType)))
              .map((ft) => ({ value: ft, label: FIELD_TYPE_LABELS[ft] }))
              .sort((a, b) => a.label.localeCompare(b.label)),
          ];
          return (
            <EvidenceBody
              items={items}
              search={search}
              field={field}
              fieldOptions={fieldOptions}
              onSearch={setSearch}
              onField={setField}
              onClear={() => {
                setSearch('');
                setField('');
              }}
              onOpen={(id) => navigate(`/inspections/${id}`)}
            />
          );
        }}
      </AsyncView>
    </div>
  );
}

function EvidenceBody({
  items,
  search,
  field,
  fieldOptions,
  onSearch,
  onField,
  onClear,
  onOpen,
}: {
  items: EvidenceItem[];
  search: string;
  field: string;
  fieldOptions: SelectOption[];
  onSearch: (v: string) => void;
  onField: (v: string) => void;
  onClear: () => void;
  onOpen: (inspectionId: string) => void;
}) {
  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return items.filter(
      (i) =>
        (!field || i.fieldType === field) &&
        (!q ||
          i.value.toLowerCase().includes(q) ||
          i.product.toLowerCase().includes(q) ||
          i.finding.toLowerCase().includes(q)),
    );
  }, [items, search, field]);

  const hasFilters = Boolean(search || field);

  return (
    <Card>
      <CardBody flush>
        <FilterBar>
          <SearchBar
            value={search}
            onChange={onSearch}
            placeholder="Search value, product or finding…"
            ariaLabel="Search evidence"
            className="filter-bar__search"
          />
          <SelectField label="Field" value={field} options={fieldOptions} onChange={onField} />
          <span className="spacer" />
          {hasFilters && (
            <button type="button" className="btn btn--ghost btn--sm" onClick={onClear}>
              <Icon name="close" size={14} />
              Clear
            </button>
          )}
        </FilterBar>

        {filtered.length === 0 ? (
          <div style={{ padding: 'var(--space-6)' }}>
            <EmptyState icon="evidence" title="No evidence matches" message="Try a different field or search." />
          </div>
        ) : (
          <div style={{ padding: 'var(--space-5)' }}>
            <div className="evi-grid">
              {filtered.map((item) => (
                <EvidenceCard key={item.id} item={item} onOpen={() => onOpen(item.inspectionId)} />
              ))}
            </div>
          </div>
        )}
      </CardBody>
    </Card>
  );
}

function EvidenceCard({ item, onOpen }: { item: EvidenceItem; onOpen: () => void }) {
  return (
    <button type="button" className="evi-card" onClick={onOpen}>
      <div className="evi-card__thumb" aria-hidden>
        <div
          className="evi-card__region"
          style={{
            left: `${item.region.x * 100}%`,
            top: `${item.region.y * 100}%`,
            width: `${item.region.width * 100}%`,
            height: `${item.region.height * 100}%`,
          }}
        />
      </div>
      <div className="evi-card__body">
        <span className="eyebrow">{FIELD_TYPE_LABELS[item.fieldType as FieldType]}</span>
        <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 'var(--fw-semibold)' }}>{item.value}</span>
        <span className="cell-muted" style={{ fontSize: 'var(--fs-sm)' }}>
          {item.product}
        </span>
        <div className="row row--between" style={{ marginTop: 'var(--space-2)' }}>
          <StatusBadge status={item.status} dot={false} />
          <ConfidenceMeter value={item.confidence} />
        </div>
      </div>
    </button>
  );
}
