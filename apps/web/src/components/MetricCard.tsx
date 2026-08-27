import { cn } from '../lib/cn';
import { Icon } from './Icon';
import type { IconName } from './Icon';

export interface TrendInfo {
  dir: 'up' | 'down' | 'flat';
  label: string;
  /** Whether the movement is good (green) or bad (red). Defaults to dir-based. */
  good?: boolean;
}

export function MetricCard({
  label,
  value,
  icon,
  trend,
  hint,
}: {
  label: string;
  value: string | number;
  icon?: IconName;
  trend?: TrendInfo;
  hint?: string;
}) {
  return (
    <div className="metric">
      <div className="metric__top">
        <span className="metric__label">{label}</span>
        {icon && (
          <span className="metric__icon" aria-hidden>
            <Icon name={icon} size={17} />
          </span>
        )}
      </div>
      <div className="metric__value">{value}</div>
      <div className="metric__foot">
        {trend && <TrendPill trend={trend} />}
        {hint && <span>{hint}</span>}
      </div>
    </div>
  );
}

function TrendPill({ trend }: { trend: TrendInfo }) {
  const good = trend.good ?? (trend.dir === 'up' ? true : trend.dir === 'down' ? false : undefined);
  const toneClass =
    good === undefined ? 'trend--flat' : good ? 'trend--up' : 'trend--down';
  const iconName: IconName = trend.dir === 'up' ? 'arrowUp' : trend.dir === 'down' ? 'arrowDown' : 'arrowRight';
  return (
    <span className={cn('trend', toneClass)}>
      <Icon name={iconName} size={13} />
      {trend.label}
    </span>
  );
}
