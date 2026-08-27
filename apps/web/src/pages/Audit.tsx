import { useState } from 'react';

import { AuditTimeline } from '../components/AuditTimeline';
import { DemoBadge } from '../components/Badge';
import { Card, CardBody } from '../components/Card';
import { Icon } from '../components/Icon';
import { FilterBar, SelectField } from '../components/inputs';
import type { SelectOption } from '../components/inputs';
import { PageHeader } from '../components/PageHeader';
import { AsyncView, EmptyState } from '../components/states';
import { useAsync } from '../data/useAsync';
import { mockApi } from '../mock/adapter';
import { inspectorName } from '../mock/fixtures';
import { inspections } from '../mock/inspections';

const referenceOf = (id?: string | null): string =>
  (id && inspections.find((i) => i.id === id)?.referenceNo) || (id ?? '—');

export function AuditPage() {
  const query = useAsync(() => mockApi.getAudit(), []);
  const [inspectionId, setInspectionId] = useState('');

  return (
    <div className="page">
      <PageHeader
        eyebrow="Accountability"
        title="Audit Trail"
        lead="An append-only record of every lifecycle event — creation, analysis, findings and human review — with actor and timestamp. System actions are labelled System."
        actions={<DemoBadge label="DEMO AUDIT" />}
      />

      <AsyncView query={query} loadingLabel="Loading audit trail…">
        {(events) => {
          const inspectionOptions: SelectOption[] = [
            { value: '', label: 'All inspections' },
            ...Array.from(new Set(events.map((e) => e.inspectionId).filter((v): v is string => Boolean(v)))).map(
              (id) => ({ value: id, label: referenceOf(id) }),
            ),
          ];

          const filtered = [...events]
            .filter((e) => !inspectionId || e.inspectionId === inspectionId)
            .sort((a, b) => b.createdAt.localeCompare(a.createdAt));

          return (
            <Card>
              <CardBody flush>
                <FilterBar>
                  <SelectField
                    label="Inspection"
                    value={inspectionId}
                    options={inspectionOptions}
                    onChange={setInspectionId}
                  />
                  <span className="spacer" />
                  <span className="row" style={{ gap: 6, color: 'var(--text-faint)', fontSize: 'var(--fs-sm)' }}>
                    <Icon name="shield" size={14} />
                    Append-only · {filtered.length} events
                  </span>
                </FilterBar>
                <div style={{ padding: 'var(--space-5)' }}>
                  {filtered.length === 0 ? (
                    <EmptyState icon="audit" title="No audit events" message="No events for this inspection." />
                  ) : (
                    <AuditTimeline events={filtered} resolveActor={inspectorName} />
                  )}
                </div>
              </CardBody>
            </Card>
          );
        }}
      </AsyncView>
    </div>
  );
}
