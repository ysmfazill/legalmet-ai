import type { Tone } from '@legalmet/config';
import { cn } from '../lib/cn';
import { Icon } from './Icon';
import type { IconName } from './Icon';

export interface ActionOption {
  id: string;
  label: string;
  tone?: Tone;
  icon?: IconName;
}

/** A single-select group of actions (e.g. the inspector's review decision). */
export function ActionBar({
  options,
  selected,
  onSelect,
  ariaLabel,
}: {
  options: ActionOption[];
  selected?: string | null;
  onSelect: (id: string) => void;
  ariaLabel?: string;
}) {
  return (
    <div className="row row--wrap" role="group" aria-label={ariaLabel}>
      {options.map((o) => (
        <button
          key={o.id}
          type="button"
          className={cn('btn', 'btn--sm', selected === o.id && 'btn--primary')}
          aria-pressed={selected === o.id}
          onClick={() => onSelect(o.id)}
        >
          {o.icon && <Icon name={o.icon} size={14} />}
          {o.label}
        </button>
      ))}
    </div>
  );
}
