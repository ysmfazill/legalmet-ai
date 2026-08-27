import { FIELD_TYPE_LABELS } from '@legalmet/config';

import type { DetectedDeclaration } from '../mock/types';
import { cn } from '../lib/cn';
import { ConfidenceMeter, StatusBadge } from './Badge';

/** A detected declaration row in the intelligence panel; selects its region. */
export function DeclarationField({
  declaration,
  active,
  onClick,
}: {
  declaration: DetectedDeclaration;
  active?: boolean;
  onClick?: () => void;
}) {
  return (
    <button
      type="button"
      className={cn('decl', active && 'is-active')}
      onClick={onClick}
      aria-pressed={active}
    >
      <span className="decl__field">{FIELD_TYPE_LABELS[declaration.field]}</span>
      <span className="decl__value">{declaration.value}</span>
      <span className="decl__meta">
        <StatusBadge status={declaration.status} />
        <ConfidenceMeter value={declaration.confidence} />
      </span>
    </button>
  );
}
