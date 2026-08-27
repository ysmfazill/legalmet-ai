import type { ReactNode } from 'react';

export function PageHeader({
  title,
  lead,
  actions,
  eyebrow,
}: {
  title: ReactNode;
  lead?: ReactNode;
  actions?: ReactNode;
  eyebrow?: ReactNode;
}) {
  return (
    <header className="page__header">
      <div>
        {eyebrow && <div className="eyebrow">{eyebrow}</div>}
        <h1 className="page__heading">{title}</h1>
        {lead && <p className="page__lead">{lead}</p>}
      </div>
      {actions && <div className="page__actions">{actions}</div>}
    </header>
  );
}
