/**
 * Evidence timeline (UI-06) — the inspection's audit trail in the workspace.
 *
 * Chronological, with REAL server timestamps only (nothing is fabricated):
 * every lifecycle event — intake, perception, evaluation, verification,
 * review, decision — is rendered from the append-only audit table. The trail
 * distinguishes SOURCE EVIDENCE (citizen complaint events, where present)
 * from OFFICIAL INSPECTION EVIDENCE (everything the department recorded).
 *
 * The trail is read-only for every role; it cannot be edited from the UI and
 * the API exposes no write path for it.
 */
import type { AuditEvent } from '@legalmet/types';

import { api } from '../api/client';
import { Card, CardBody, CardHead } from '../components/Card';
import { AuditTimeline } from '../components/AuditTimeline';
import { Icon } from '../components/Icon';
import { useAsync } from '../data/useAsync';

/** Events that belong to the citizen complaint the inspection came from —
 *  source material, not the department's own inspection evidence. */
const SOURCE_EVENT_TYPES = new Set([
  'COMPLAINT_ASSIGNED',
  'COMPLAINT_INSPECTION_CREATED',
  'COMPLAINT_INSPECTION_COMPLETED',
  'COMPLAINT_ACTION_TAKEN',
  'COMPLAINT_CLOSED',
]);

export function EvidenceTimelineCard({
  inspectionId,
}: {
  inspectionId: string;
}) {
  const query = useAsync<AuditEvent[]>(async () => {
    const events = await api.getInspectionAudit(inspectionId);
    // Chronological — oldest first, exactly as it happened.
    return [...events].sort((a, b) => a.createdAt.localeCompare(b.createdAt));
  }, [inspectionId]);

  return (
    <Card>
      <CardHead
        eyebrow="Evidence timeline"
        title="Audit trail"
        subtitle="Chronological, append-only, real timestamps — who did what and when"
        actions={
          query.data ? (
            <span
              className="row"
              style={{ gap: 6, color: 'var(--text-faint)', fontSize: 'var(--fs-sm)' }}
            >
              <Icon name="clock" size={14} />
              {query.data.length} events
            </span>
          ) : undefined
        }
      />
      <CardBody>
        {query.status === 'loading' ? (
          <p className="cell-muted" style={{ margin: 0 }}>
            Loading the audit trail…
          </p>
        ) : query.status === 'error' ? (
          <div className="demo-note demo-note--error" style={{ display: 'flex', gap: 8 }} role="alert">
            <Icon name="alert" size={15} />
            <span>Could not load the audit trail: {query.error.message}</span>
          </div>
        ) : !query.data || query.data.length === 0 ? (
          <p className="cell-muted" style={{ margin: 0 }}>
            No audit events recorded for this inspection yet.
          </p>
        ) : (
          <div className="stack">
            {query.data.some((e) => SOURCE_EVENT_TYPES.has(String(e.eventType))) && (
              <p className="cell-muted" style={{ margin: 0, fontSize: 'var(--fs-xs)' }}>
                Complaint-filed events are the citizen&rsquo;s <strong>source evidence</strong>; every
                other event is the department&rsquo;s <strong>official inspection evidence</strong>.
              </p>
            )}
            <AuditTimeline
              events={query.data}
              resolveActor={(id) => (id ? `${id.slice(0, 8)}…` : 'System')}
            />
          </div>
        )}
      </CardBody>
    </Card>
  );
}
