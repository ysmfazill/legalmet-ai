/**
 * Report audit trail card (UI-08 §17).
 *
 * GET /reports/:id/audit — the report's slice of the shared append-only
 * audit trail: REPORT_CREATED / GENERATED / REVIEWED / FINALIZED /
 * EXPORTED_PDF / EXPORTED_DOCX / AMENDED, each with actor, role and
 * timestamp. Read-only for every role; ordinary users cannot edit audit
 * events (there is no write path, frontend or backend).
 */
import { Badge } from '../components/Badge';
import { Card, CardBody, CardHead } from '../components/Card';
import { Icon } from '../components/Icon';
import { AsyncView } from '../components/states';
import { DataTable, type Column } from '../components/DataTable';
import { useAsync } from '../data/useAsync';
import { formatDateTime, humanizeEnum } from '../lib/format';
import { api } from '../api/client';
import type { ReportAuditEvent } from '@legalmet/types';

const EVENT_TONE: Record<string, 'positive' | 'info' | 'warning' | 'neutral'> = {
  REPORT_CREATED: 'neutral',
  REPORT_GENERATED: 'info',
  REPORT_REVIEWED: 'info',
  REPORT_FINALIZED: 'positive',
  REPORT_EXPORTED_PDF: 'positive',
  REPORT_EXPORTED_DOCX: 'positive',
  REPORT_AMENDED: 'warning',
};

export function ReportAuditCard({ reportId }: { reportId: string }) {
  const auditQuery = useAsync(() => api.getReportAudit(reportId), [reportId]);

  return (
    <Card>
      <CardHead
        eyebrow="Traceability"
        title="Audit trail"
        subtitle="Append-only lifecycle events — who did what, and when"
      />
      <CardBody flush>
        <AsyncView query={auditQuery} loadingLabel="Loading audit events…">
          {(audit) =>
            audit.events.length > 0 ? (
              <DataTable
                columns={columns}
                rows={audit.events}
                getRowId={(e) => e.id}
                ariaLabel="Report audit events"
              />
            ) : (
              <div className="stack stack--sm" style={{ padding: 'var(--space-4)' }}>
                <Icon name="audit" size={18} />
                <p style={{ margin: 0, color: 'var(--text-muted)' }}>No audit events yet.</p>
              </div>
            )
          }
        </AsyncView>
      </CardBody>
    </Card>
  );
}

const columns: Column<ReportAuditEvent>[] = [
  {
    key: 'event',
    header: 'Event',
    render: (e) => (
      <Badge tone={EVENT_TONE[e.eventType] ?? 'neutral'}>{humanizeEnum(e.eventType)}</Badge>
    ),
  },
  {
    key: 'actor',
    header: 'Actor',
    render: (e) => (
      <span>
        {e.actorName ?? 'System'}
        {e.actorRole && (
          <div className="cell-muted" style={{ fontSize: 'var(--fs-sm)' }}>
            {humanizeEnum(e.actorRole)}
          </div>
        )}
      </span>
    ),
  },
  {
    key: 'when',
    header: 'Timestamp',
    align: 'right',
    render: (e) => <span className="cell-muted">{formatDateTime(e.createdAt)}</span>,
  },
];
