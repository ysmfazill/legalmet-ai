import type { AuditEvent, Json } from '@legalmet/types';

import { formatDateTime, humanizeEnum } from '../lib/format';
import { Tag } from './Badge';

/** Extract a few primitive payload entries to render as compact tags. */
function payloadTags(payload?: Json): { key: string; value: string }[] {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) return [];
  return Object.entries(payload)
    .filter(([, v]) => v !== null && typeof v !== 'object')
    .slice(0, 4)
    .map(([key, v]) => ({ key, value: String(v) }));
}

/**
 * Append-only audit trail. Every lifecycle event — creation, analysis,
 * finding, human review — is shown with actor and time, evidencing that the
 * system records who did what and when (system actions are labelled System).
 */
export function AuditTimeline({
  events,
  resolveActor = (id) => (id ? id : 'System'),
}: {
  events: AuditEvent[];
  resolveActor?: (id?: string | null) => string;
}) {
  return (
    <div className="timeline">
      {events.map((ev) => {
        const tags = payloadTags(ev.payload);
        return (
          <div key={ev.id} className="timeline__item">
            <span className="timeline__dot" aria-hidden />
            <div className="row row--between row--wrap">
              <strong>{humanizeEnum(String(ev.eventType))}</strong>
              <span style={{ fontSize: 'var(--fs-sm)', color: 'var(--text-faint)' }}>
                {formatDateTime(ev.createdAt)}
              </span>
            </div>
            <div style={{ fontSize: 'var(--fs-sm)', color: 'var(--text-muted)', marginTop: 2 }}>
              {ev.entityType}
              {ev.entityId ? ` · ${ev.entityId}` : ''} · by {resolveActor(ev.actorId)}
            </div>
            {tags.length > 0 && (
              <div className="row row--wrap" style={{ gap: 6, marginTop: 6 }}>
                {tags.map((t) => (
                  <Tag key={t.key}>
                    {t.key}: {t.value}
                  </Tag>
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
