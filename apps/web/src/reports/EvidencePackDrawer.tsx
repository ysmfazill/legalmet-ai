/**
 * Evidence Pack drawer (UI-08 §19).
 *
 * GET /reports/:id/evidence-pack — the exportable evidence bundle with stable
 * E-00N identifiers. Provenance is preserved per item: type, label, origin
 * (SOURCE citizen vs OFFICIAL inspection). The drawer is read-only; the
 * bundle backs the PDF/DOCX exports and the audit trail slice.
 */
import { Drawer } from '../components/Drawer';
import { Icon } from '../components/Icon';
import { AsyncView, EmptyState } from '../components/states';
import { DataTable, type Column } from '../components/DataTable';
import { useAsync } from '../data/useAsync';
import { humanizeEnum } from '../lib/format';
import { api } from '../api/client';
import type { ReportEvidenceItem } from '@legalmet/types';

import { EvidenceSourceChip } from './ReportChips';

export function EvidencePackDrawer({
  reportId,
  onClose,
}: {
  reportId: string;
  onClose: () => void;
}) {
  const packQuery = useAsync(() => api.getEvidencePack(reportId), [reportId]);

  return (
    <Drawer
      wide
      title="Evidence Pack"
      subtitle="The complete evidence bundle behind this report — stable E-00N identifiers, provenance preserved"
      onClose={onClose}
    >
      <AsyncView query={packQuery} loadingLabel="Collecting evidence pack…">
        {(pack) => (
          <div className="stack">
            <dl className="kv">
              <dt>Pack ID</dt>
              <dd title={pack.packId}>{pack.packId.slice(0, 13)}…</dd>
              <dt>Inspection ID</dt>
              <dd title={pack.inspectionId}>{pack.inspectionId.slice(0, 13)}…</dd>
              <dt>Report version</dt>
              <dd>v{pack.reportVersion}</dd>
              <dt>Created at</dt>
              <dd>{new Date(pack.createdAt).toLocaleString()}</dd>
              <dt>Evidence count</dt>
              <dd>{pack.evidenceCount} items</dd>
              <dt>Completeness</dt>
              <dd>
                {pack.completeness.requiredTotal - pack.completeness.requiredOpen} /{' '}
                {pack.completeness.requiredTotal} required ·{' '}
                {pack.completeness.recommendedOpen} recommended open
              </dd>
            </dl>

            {pack.items.length > 0 ? (
              <EvidenceItemsTable items={pack.items} />
            ) : (
              <EmptyState
                icon="evidence"
                title="No evidence items"
                message="The evidence manifest is empty — generate the report first."
              />
            )}

            <p style={{ margin: 0, fontSize: 'var(--fs-sm)', color: 'var(--text-faint)' }}>
              <Icon name="info" size={14} />
              {pack.boundaryNote}
            </p>
          </div>
        )}
      </AsyncView>
    </Drawer>
  );
}

function EvidenceItemsTable({ items }: { items: ReportEvidenceItem[] }) {
  const columns: Column<ReportEvidenceItem>[] = [
    {
      key: 'ref',
      header: 'Ref',
      width: '70px',
      render: (i) => <strong>{i.ref}</strong>,
    },
    {
      key: 'type',
      header: 'Type',
      render: (i) => <span>{humanizeEnum(i.evidenceType)}</span>,
    },
    {
      key: 'label',
      header: 'Label',
      render: (i) => <span title={i.label}>{i.label}</span>,
    },
    {
      key: 'origin',
      header: 'Origin',
      render: (i) => {
        const origin = (i.detail as Record<string, unknown> | null)?.['origin'];
        return typeof origin === 'string' ? <EvidenceSourceChip source={origin} /> : <span className="cell-muted">—</span>;
      },
    },
  ];
  return (
    <DataTable
      columns={columns}
      rows={items}
      getRowId={(i) => i.id}
      ariaLabel="Evidence pack items"
    />
  );
}
