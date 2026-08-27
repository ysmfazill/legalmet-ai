import type { ReactNode } from 'react';

import { useEscapeKey } from '../data/useEscapeKey';
import { cn } from '../lib/cn';
import { Icon } from './Icon';

export function Drawer({
  title,
  subtitle,
  onClose,
  children,
  footer,
  wide,
  labelId = 'drawer-title',
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
  wide?: boolean;
  labelId?: string;
}) {
  useEscapeKey(true, onClose);
  return (
    <>
      <div className="overlay" onClick={onClose} aria-hidden />
      <aside
        className={cn('drawer', wide && 'drawer--wide')}
        role="dialog"
        aria-modal="true"
        aria-labelledby={labelId}
      >
        <header className="drawer__head">
          <div>
            <h2 id={labelId} className="card__title">
              {title}
            </h2>
            {subtitle && <p className="card__subtitle">{subtitle}</p>}
          </div>
          <button type="button" className="icon-btn" onClick={onClose} aria-label="Close panel">
            <Icon name="close" size={18} />
          </button>
        </header>
        <div className="drawer__body">{children}</div>
        {footer && <footer className="drawer__foot">{footer}</footer>}
      </aside>
    </>
  );
}
