import type { ReactNode } from 'react';

import type { AsyncState } from '../data/useAsync';
import { cn } from '../lib/cn';
import { Icon } from './Icon';
import type { IconName } from './Icon';

export function Spinner({ size = 20 }: { size?: number }) {
  return <span className="spinner" style={{ width: size, height: size }} aria-hidden />;
}

export function Skeleton({
  width,
  height = 14,
  radius,
  className,
}: {
  width?: number | string;
  height?: number | string;
  radius?: number;
  className?: string;
}) {
  return (
    <span
      className={cn('skeleton', className)}
      style={{ display: 'block', width: width ?? '100%', height, borderRadius: radius }}
      aria-hidden
    />
  );
}

export function LoadingState({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className="state" role="status" aria-live="polite">
      <Spinner size={26} />
      <p className="state__msg">{label}</p>
    </div>
  );
}

export function EmptyState({
  icon = 'inspections',
  title,
  message,
  action,
}: {
  icon?: IconName;
  title: string;
  message?: string;
  action?: ReactNode;
}) {
  return (
    <div className="state">
      <span className="state__icon">
        <Icon name={icon} size={22} />
      </span>
      <p className="state__title">{title}</p>
      {message && <p className="state__msg">{message}</p>}
      {action}
    </div>
  );
}

export function ErrorState({
  error,
  onRetry,
  title = 'Something went wrong',
}: {
  error?: Error | string;
  onRetry?: () => void;
  title?: string;
}) {
  const message = typeof error === 'string' ? error : (error?.message ?? 'Unexpected error.');
  return (
    <div className="state state--error" role="alert">
      <span className="state__icon">
        <Icon name="alert" size={22} />
      </span>
      <p className="state__title">{title}</p>
      <p className="state__msg">{message}</p>
      {onRetry && (
        <button type="button" className="btn btn--subtle" onClick={onRetry}>
          <Icon name="reset" size={15} />
          Retry
        </button>
      )}
    </div>
  );
}

/**
 * Exhaustively render an async query's loading / error / success states.
 * Empty-data handling is left to the success renderer (data-shape specific).
 */
export function AsyncView<T>({
  query,
  loadingLabel,
  children,
}: {
  query: AsyncState<T> & { reload: () => void };
  loadingLabel?: string;
  children: (data: T) => ReactNode;
}) {
  if (query.status === 'loading') return <LoadingState label={loadingLabel} />;
  if (query.status === 'error') return <ErrorState error={query.error} onRetry={query.reload} />;
  return <>{children(query.data)}</>;
}
