import type { FindingCounts, Inspection } from '@legalmet/types';

import { formatRelative } from '../lib/format';
import { inspectorName } from '../mock/fixtures';
import { Badge } from './Badge';
import { InspectionStatusBadge } from './Badge';
import { DataTable } from './DataTable';
import type { Column } from './DataTable';

/** Compact per-inspection finding summary (compliant / review / violation). */
export function FindingCountPills({ counts }: { counts?: FindingCounts }) {
  if (!counts || counts.total === 0) return <span className="cell-muted">—</span>;
  const pills: { tone: string; value: number; label: string }[] = [
    { tone: 'positive', value: counts.compliant, label: 'compliant' },
    { tone: 'warning', value: counts.reviewRequired, label: 'review required' },
    { tone: 'critical', value: counts.potentialViolation, label: 'potential violations' },
  ].filter((p) => p.value > 0);
  if (pills.length === 0) return <span className="cell-muted">—</span>;
  return (
    <span className="row" style={{ gap: 'var(--space-3)' }}>
      {pills.map((p) => (
        <span
          key={p.label}
          className="row"
          style={{ gap: 5, fontVariantNumeric: 'tabular-nums' }}
          title={`${p.value} ${p.label}`}
        >
          <span
            className="badge__dot"
            style={{ color: `var(--tone-${p.tone})` }}
            aria-hidden
          />
          {p.value}
        </span>
      ))}
    </span>
  );
}

export function InspectionTable({
  inspections,
  onOpen,
}: {
  inspections: Inspection[];
  onOpen: (id: string) => void;
}) {
  const columns: Column<Inspection>[] = [
    {
      key: 'ref',
      header: 'Reference',
      render: (i) => <span className="cell-mono cell-strong">{i.referenceNo}</span>,
    },
    {
      key: 'source',
      header: 'Source',
      render: (i) =>
        i.sourceComplaint ? (
          <span
            className="row"
            style={{ gap: 6, flexWrap: 'nowrap' }}
            title={`Targeted inspection — originated from complaint ${i.sourceComplaint.reference}: ${i.sourceComplaint.issue}`}
          >
            <Badge tone="info" outline>Targeted</Badge>
            <span className="cell-mono" style={{ fontSize: 'var(--fs-xs)' }}>
              {i.sourceComplaint.reference}
            </span>
          </span>
        ) : (
          <span className="cell-muted" title="Created directly by an inspector — not from a citizen complaint">
            Standard intake
          </span>
        ),
    },
    {
      key: 'product',
      header: 'Product',
      render: (i) => (
        <div>
          <div className="cell-strong">{i.product?.name ?? 'Unknown product'}</div>
          <div className="cell-muted" style={{ fontSize: 'var(--fs-sm)' }}>
            {i.product?.category ?? '—'}
          </div>
        </div>
      ),
    },
    { key: 'status', header: 'Status', render: (i) => <InspectionStatusBadge status={i.status} /> },
    { key: 'findings', header: 'Findings', render: (i) => <FindingCountPills counts={i.findingCounts} /> },
    {
      key: 'inspector',
      header: 'Inspector',
      // Live rows carry the API-computed name; demo rows keep the mock lookup.
      render: (i) => (
        <span className="cell-muted">{i.inspectorName ?? inspectorName(i.inspectorId)}</span>
      ),
    },
    {
      key: 'updated',
      header: 'Updated',
      render: (i) => <span className="cell-muted">{formatRelative(i.updatedAt)}</span>,
    },
  ];

  return (
    <DataTable
      columns={columns}
      rows={inspections}
      getRowId={(i) => i.id}
      onRowClick={(i) => onOpen(i.id)}
      ariaLabel="Inspections"
    />
  );
}
