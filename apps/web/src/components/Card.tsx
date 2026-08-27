import type { ReactNode } from 'react';

import { cn } from '../lib/cn';

export function Card({ children, className }: { children: ReactNode; className?: string }) {
  return <section className={cn('card', className)}>{children}</section>;
}

export function CardHead({
  title,
  subtitle,
  actions,
  eyebrow,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  eyebrow?: ReactNode;
}) {
  return (
    <header className="card__head">
      <div>
        {eyebrow && <div className="eyebrow">{eyebrow}</div>}
        <h2 className="card__title">{title}</h2>
        {subtitle && <p className="card__subtitle">{subtitle}</p>}
      </div>
      {actions && <div className="row">{actions}</div>}
    </header>
  );
}

export function CardBody({
  children,
  flush,
  className,
}: {
  children: ReactNode;
  flush?: boolean;
  className?: string;
}) {
  return <div className={cn('card__body', flush && 'card__body--flush', className)}>{children}</div>;
}

/** Convenience: header + body in one, the common case. */
export function SectionCard({
  title,
  subtitle,
  eyebrow,
  actions,
  children,
  flush,
  className,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  eyebrow?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  flush?: boolean;
  className?: string;
}) {
  return (
    <Card className={className}>
      <CardHead title={title} subtitle={subtitle} eyebrow={eyebrow} actions={actions} />
      <CardBody flush={flush}>{children}</CardBody>
    </Card>
  );
}
