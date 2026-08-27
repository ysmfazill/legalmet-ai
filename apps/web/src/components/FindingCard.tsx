import { COMPLIANCE_STATUS_META, FIELD_TYPE_LABELS } from '@legalmet/config';

import type { FindingView } from '../mock/types';
import { cn } from '../lib/cn';
import { ConfidenceMeter, RiskBadge, StatusBadge, Tag } from './Badge';
import { Icon } from './Icon';

/**
 * A single compliance finding. Clickable → opens the WHY / Evidence drawer.
 * The left border colour encodes the compliance tone.
 */
export function FindingCard({
  finding,
  onOpen,
  active,
}: {
  finding: FindingView;
  onOpen?: (finding: FindingView) => void;
  active?: boolean;
}) {
  const tone = COMPLIANCE_STATUS_META[finding.status].tone;
  return (
    <button
      type="button"
      className={cn('finding', `finding--${tone}`)}
      onClick={onOpen ? () => onOpen(finding) : undefined}
      aria-pressed={active}
    >
      <div className="row row--between">
        <span className="finding__title">{finding.title}</span>
        <StatusBadge status={finding.status} />
      </div>
      <p
        className="finding__rationale"
        style={{
          display: '-webkit-box',
          WebkitLineClamp: 2,
          WebkitBoxOrient: 'vertical',
          overflow: 'hidden',
        }}
      >
        {finding.rationale}
      </p>
      <div className="row row--wrap" style={{ gap: 'var(--space-2)' }}>
        {finding.fieldType && <Tag>{FIELD_TYPE_LABELS[finding.fieldType]}</Tag>}
        {finding.rule && <Tag>{finding.rule.code}</Tag>}
        <RiskBadge risk={finding.risk} />
        <ConfidenceMeter value={finding.confidence} />
        <span className="spacer" />
        <span className="row" style={{ gap: 4, color: 'var(--accent-strong)', fontSize: 'var(--fs-sm)', fontWeight: 600 }}>
          Why flagged
          <Icon name="arrowRight" size={13} />
        </span>
      </div>
    </button>
  );
}
