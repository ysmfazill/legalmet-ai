import { useState } from 'react';

import type { Tone } from '@legalmet/config';

import { Badge, DemoBadge, Tag } from '../components/Badge';
import { Card, CardBody } from '../components/Card';
import { Icon } from '../components/Icon';
import { PageHeader } from '../components/PageHeader';
import { ReportPreview } from '../components/ReportPreview';
import { AsyncView, EmptyState } from '../components/states';
import { useAsync } from '../data/useAsync';
import { formatDate } from '../lib/format';
import { mockApi } from '../mock/adapter';
import type { ReportItem } from '../mock/types';

const STATUS_TONE: Record<ReportItem['status'], Tone> = { DRAFT: 'warning', FINALIZED: 'positive' };

/** Prefer the fully-worked hero inspection so the preview is rich by default. */
function defaultReport(list: ReportItem[]): ReportItem | undefined {
  return (
    list.find((r) => r.inspectionId === 'ins-10482') ??
    list.find((r) => r.inspectionId) ??
    list[0]
  );
}

export function ReportsPage() {
  const listQuery = useAsync(() => mockApi.getReports(), []);

  return (
    <div className="page">
      <PageHeader
        eyebrow="Output"
        title="Reports"
        lead="Audit-ready inspection reports. Each clearly separates the AI-assisted analysis from the inspector's decision, and carries the mandatory demonstration disclaimer."
        actions={<DemoBadge label="DEMO REPORTS" />}
      />

      <AsyncView query={listQuery} loadingLabel="Loading reports…">
        {(list) => (list.length === 0 ? (
          <Card>
            <CardBody>
              <EmptyState icon="reports" title="No reports yet" message="Completed inspections will appear here." />
            </CardBody>
          </Card>
        ) : (
          <ReportsBody list={list} />
        ))}
      </AsyncView>
    </div>
  );
}

function ReportsBody({ list }: { list: ReportItem[] }) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const selected = list.find((r) => r.id === selectedId) ?? defaultReport(list);

  const detailQuery = useAsync(
    () =>
      selected?.inspectionId
        ? mockApi.getInspectionDetail(selected.inspectionId)
        : Promise.resolve(undefined),
    [selected?.id],
  );

  return (
    <>
      <div className="row row--wrap" style={{ gap: 'var(--space-3)', alignItems: 'stretch' }}>
        {list.map((r) => {
          const isSelected = r.id === selected?.id;
          return (
            <button
              key={r.id}
              type="button"
              className="card"
              aria-pressed={isSelected}
              onClick={() => setSelectedId(r.id)}
              style={{
                flex: '1 1 240px',
                textAlign: 'left',
                padding: 'var(--space-4)',
                cursor: 'pointer',
                borderColor: isSelected ? 'var(--accent)' : undefined,
                boxShadow: isSelected ? '0 0 0 1px var(--accent)' : undefined,
              }}
            >
              <div className="row row--between" style={{ gap: 'var(--space-2)' }}>
                <Tag>{r.type}</Tag>
                <Badge tone={STATUS_TONE[r.status]}>{r.status}</Badge>
              </div>
              <div className="cell-strong" style={{ marginTop: 'var(--space-2)' }}>
                {r.title}
              </div>
              <div className="cell-muted" style={{ fontSize: 'var(--fs-sm)', marginTop: 4 }}>
                {r.inspector} · {formatDate(r.createdAt)}
              </div>
            </button>
          );
        })}
      </div>

      {selected && (
        <AsyncView query={detailQuery} loadingLabel="Preparing report preview…">
          {(detail) =>
            detail ? (
              <ReportPreview
                detail={detail}
                reference={detail.inspection.referenceNo}
                inspector={selected.inspector}
                generatedAt={selected.createdAt}
                status={selected.status}
              />
            ) : (
              <Card>
                <CardBody>
                  <EmptyState
                    icon="reports"
                    title="Preview not available in this demo"
                    message={
                      selected.type === 'BATCH'
                        ? 'Batch report previews are summarised in Batch Intelligence.'
                        : 'A full worked preview is available for the demonstration inspections (e.g. INS-10482).'
                    }
                  />
                </CardBody>
              </Card>
            )
          }
        </AsyncView>
      )}

      <div className="row" style={{ gap: 6 }}>
        <Icon name="info" size={14} />
        <span style={{ fontSize: 'var(--fs-sm)', color: 'var(--text-faint)' }}>
          Reports are demonstration artefacts. Legal compliance decisions rest with the inspector.
        </span>
      </div>
    </>
  );
}
