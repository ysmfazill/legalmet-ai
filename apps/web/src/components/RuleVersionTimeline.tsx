import type { Tone } from '@legalmet/config';
import type { RegulationVersion, RegulationVersionStatus } from '@legalmet/types';

import { Badge } from './Badge';
import { Icon } from './Icon';

const VERSION_STATUS: Record<RegulationVersionStatus, { label: string; tone: Tone }> = {
  DRAFT: { label: 'Draft', tone: 'info' },
  ACTIVE: { label: 'Active', tone: 'positive' },
  SUPERSEDED: { label: 'Superseded', tone: 'neutral' },
  REPEALED: { label: 'Repealed', tone: 'critical' },
};

/**
 * Version-aware rule engine, made visible: the amendment lineage of a
 * regulation. The ACTIVE version is highlighted as the one findings resolve
 * against — proving inspections are pinned to a specific rule version.
 */
export function RuleVersionTimeline({ versions }: { versions: RegulationVersion[] }) {
  const ordered = [...versions].sort((a, b) =>
    (a.effectiveFrom ?? '').localeCompare(b.effectiveFrom ?? ''),
  );
  return (
    <div className="vtimeline">
      {ordered.map((v, i) => {
        const meta = VERSION_STATUS[v.status];
        return (
          <div key={v.id} className="row" style={{ gap: 'var(--space-2)' }}>
            <div className={`vtimeline__node${v.status === 'ACTIVE' ? ' is-current' : ''}`}>
              <div className="row row--between" style={{ gap: 'var(--space-3)' }}>
                <strong>{v.versionLabel}</strong>
                <Badge tone={meta.tone}>{meta.label}</Badge>
              </div>
              <div style={{ fontSize: 'var(--fs-xs)', color: 'var(--text-faint)', marginTop: 4 }}>
                {v.effectiveFrom ?? '—'} → {v.effectiveUntil ?? 'present'}
              </div>
            </div>
            {i < ordered.length - 1 && (
              <span className="chain__arrow" aria-hidden>
                <Icon name="chevronRight" size={14} />
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}
