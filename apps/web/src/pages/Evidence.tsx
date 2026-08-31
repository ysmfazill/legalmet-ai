import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { FIELD_TYPE_LABELS } from '@legalmet/config';
import type { FieldType } from '@legalmet/types';

import { ConfidenceMeter, DemoBadge, StatusBadge } from '../components/Badge';
import { Card, CardBody, SectionCard } from '../components/Card';
import { Icon } from '../components/Icon';
import { FilterBar, SearchBar, SelectField } from '../components/inputs';
import type { SelectOption } from '../components/inputs';
import { PageHeader } from '../components/PageHeader';
import { AsyncView, EmptyState } from '../components/states';
import { useAsync } from '../data/useAsync';
import { useApp } from '../app/AppContext';
import { LiveEvidenceCard } from '../evidence/LiveEvidenceCard';
import { useLiveEvidence } from '../evidence/useLiveEvidence';
import type { LiveEvidenceItem } from '../evidence/useLiveEvidence';
import { mockApi } from '../mock/adapter';
import type { EvidenceItem } from '../mock/types';

type Source = 'live' | 'demo';

export function EvidencePage() {
  const { isLive } = useApp();
  const navigate = useNavigate();
  const [source, setSource] = useState<Source>('live');
  const [search, setSearch] = useState('');
  const [field, setField] = useState('');

  const demoQuery = useAsync(() => mockApi.getEvidenceItems(), []);
  const liveQuery = useLiveEvidence(isLive && source === 'live');

  const liveItems = liveQuery.data?.items ?? [];

  const fieldOptions: SelectOption[] = useMemo(() => {
    const items =
      source === 'live'
        ? liveItems.map((i) => ({ fieldType: i.fieldType as FieldType, value: i.value }))
        : (demoQuery.data ?? []).map((i) => ({ fieldType: i.fieldType as FieldType, value: i.value }));
    return [
      { value: '', label: 'All fields' },
      ...Array.from(new Set(items.map((i) => i.fieldType)))
        .map((ft) => ({ value: ft, label: FIELD_TYPE_LABELS[ft] }))
        .sort((a, b) => a.label.localeCompare(b.label)),
    ];
  }, [source, liveItems, demoQuery.data]);

  const openLive = (item: LiveEvidenceItem) =>
    navigate(
      `/inspections/${item.inspectionId}?field=${encodeURIComponent(item.fieldId)}`,
    );

  return (
    <div className="page">
      <PageHeader
        eyebrow="Extraction"
        title="Evidence Explorer"
        lead="Every value the system extracted from a package label, with the region it came from and its detection confidence. Open an item to see it in the inspection workspace."
        actions={
          isLive ? (
            <div className="row" style={{ gap: 'var(--space-2)' }}>
              <button
                type="button"
                className={`btn btn--sm ${source === 'live' ? 'btn--subtle' : 'btn--ghost'}`}
                aria-pressed={source === 'live'}
                onClick={() => setSource('live')}
              >
                <Icon name="camera" size={14} />
                Live inspections
              </button>
              <button
                type="button"
                className={`btn btn--sm ${source === 'demo' ? 'btn--subtle' : 'btn--ghost'}`}
                aria-pressed={source === 'demo'}
                onClick={() => setSource('demo')}
              >
                Demonstration data
              </button>
            </div>
          ) : (
            <DemoBadge label="DEMO EVIDENCE" />
          )
        }
      />

      {source === 'live' && isLive ? (
        liveQuery.data && liveQuery.data.pendingInspections.length > 0 ? (
          <div className="demo-note demo-note--block">
            <Icon name="info" size={15} />
            <span>
              {liveQuery.data.pendingInspections.length} live inspection(s) have images but no
              perception evidence yet — run perception from their workspace to extract declarations.
            </span>
          </div>
        ) : null
      ) : null}

      {source === 'live' && isLive ? (
        <AsyncView query={liveQuery} loadingLabel="Loading live evidence…">
          {(data) => (
            <LiveEvidenceBody
              items={data.items}
              search={search}
              field={field}
              fieldOptions={fieldOptions}
              onSearch={setSearch}
              onField={setField}
              onClear={() => {
                setSearch('');
                setField('');
              }}
              onOpen={openLive}
            />
          )}
        </AsyncView>
      ) : (
        <AsyncView query={demoQuery} loadingLabel="Loading evidence…">
          {(items) => (
            <DemoEvidenceBody
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
          )}
        </AsyncView>
      )}
    </div>
  );
}

function LiveEvidenceBody({
  items,
  search,
  field,
  fieldOptions,
  onSearch,
  onField,
  onClear,
  onOpen,
}: {
  items: LiveEvidenceItem[];
  search: string;
  field: string;
  fieldOptions: SelectOption[];
  onSearch: (v: string) => void;
  onField: (v: string) => void;
  onClear: () => void;
  onOpen: (item: LiveEvidenceItem) => void;
}) {
  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return items.filter(
      (i) =>
        (!field || i.fieldType === field) &&
        (!q ||
          i.value.toLowerCase().includes(q) ||
          i.rawText.toLowerCase().includes(q) ||
          i.referenceNo.toLowerCase().includes(q) ||
          i.productName.toLowerCase().includes(q)),
    );
  }, [items, search, field]);

  const hasFilters = Boolean(search || field);

  return (
    <SectionCard
      eyebrow="Live inspections"
      title="Real extracted evidence"
      subtitle="Photographed labels → OCR → extracted declarations — every card traces to real stored pixels"
      actions={<span className="tag tag--live">LIVE EVIDENCE</span>}
    >
      <FilterBar>
        <SearchBar
          value={search}
          onChange={onSearch}
          placeholder="Search value, OCR text or inspection…"
          ariaLabel="Search live evidence"
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
          <EmptyState
            icon="evidence"
            title="No live evidence yet"
            message="Create an inspection, upload a package image and run perception — extracted declarations appear here with their real image regions."
          />
        </div>
      ) : (
        <div style={{ padding: 'var(--space-5)' }}>
          <div className="evi-grid">
            {filtered.map((item) => (
              <LiveEvidenceCard key={item.fieldId} item={item} onOpen={onOpen} />
            ))}
          </div>
        </div>
      )}
    </SectionCard>
  );
}

function DemoEvidenceBody({
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
