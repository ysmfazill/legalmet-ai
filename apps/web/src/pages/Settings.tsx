import { useState } from 'react';

import {
  APP_NAME,
  APP_TAGLINE,
  DEMO_DATA_LABEL,
  DEMO_DATA_NOTICE,
  PROBLEM_STATEMENT,
} from '@legalmet/config';
import type { Tone } from '@legalmet/config';

import { useApp } from '../app/AppContext';
import { Badge, RoleBadge } from '../components/Badge';
import { Card, CardBody, CardHead, SectionCard } from '../components/Card';
import { Icon } from '../components/Icon';
import { PageHeader } from '../components/PageHeader';

interface Pref {
  id: string;
  label: string;
  description: string;
}

const PREFERENCES: Pref[] = [
  { id: 'compact', label: 'Compact tables', description: 'Denser rows in inspection and queue tables.' },
  { id: 'contrast', label: 'High-contrast regions', description: 'Stronger overlay colours in the evidence viewer.' },
  { id: 'confirmReview', label: 'Confirm before recording a decision', description: 'Ask for confirmation on every inspector decision.' },
];

function initials(name: string): string {
  return name
    .replace(/^Dr\.?\s+/i, '')
    .split(/\s+/)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase() ?? '')
    .join('');
}

export function SettingsPage() {
  const { user, connection } = useApp();
  const [prefs, setPrefs] = useState<Record<string, boolean>>({ compact: false, contrast: true, confirmReview: false });

  const conn: { label: string; tone: Tone } =
    connection.kind === 'online'
      ? { label: 'Online', tone: 'positive' }
      : connection.kind === 'offline'
        ? { label: 'Offline', tone: 'critical' }
        : { label: 'Checking…', tone: 'info' };

  return (
    <div className="page">
      <PageHeader eyebrow="Configuration" title="Settings" lead="Your profile, workspace preferences and system information." />

      <div className="grid grid--2">
        <Card>
          <CardHead eyebrow="Account" title="Profile" />
          <CardBody>
            <div className="row" style={{ gap: 'var(--space-3)' }}>
              <span className="avatar" style={{ width: 46, height: 46 }}>
                {initials(user.fullName)}
              </span>
              <div>
                <div className="cell-strong">{user.fullName}</div>
                <div className="cell-muted" style={{ fontSize: 'var(--fs-sm)' }}>
                  {user.email}
                </div>
              </div>
              <span className="spacer" />
              <RoleBadge role={user.role} />
            </div>
          </CardBody>
        </Card>

        <Card>
          <CardHead eyebrow="System" title="Backend connection" actions={<Badge tone={conn.tone} dot>{conn.label}</Badge>} />
          <CardBody>
            <dl className="kv">
              <dt>Status</dt>
              <dd>{conn.label}</dd>
              {connection.kind === 'online' && (
                <>
                  <dt>Service</dt>
                  <dd>{connection.health.service}</dd>
                  <dt>Version</dt>
                  <dd>{connection.health.version}</dd>
                  <dt>Environment</dt>
                  <dd>{connection.health.environment}</dd>
                </>
              )}
              {connection.kind === 'offline' && (
                <>
                  <dt>Detail</dt>
                  <dd>{connection.message}</dd>
                </>
              )}
            </dl>
          </CardBody>
        </Card>
      </div>

      <SectionCard eyebrow="Workspace" title="Preferences" subtitle="Demonstration toggles — not persisted between sessions.">
        <div className="detail-list">
          {PREFERENCES.map((p) => (
            <label key={p.id} className="detail-list__row" style={{ cursor: 'pointer', alignItems: 'center' }}>
              <span className="detail-list__key" style={{ textAlign: 'left' }}>
                <span className="cell-strong" style={{ color: 'var(--text)' }}>
                  {p.label}
                </span>
                <span style={{ display: 'block', fontSize: 'var(--fs-sm)' }}>{p.description}</span>
              </span>
              <input
                type="checkbox"
                checked={prefs[p.id] ?? false}
                onChange={(e) => setPrefs((prev) => ({ ...prev, [p.id]: e.target.checked }))}
                aria-label={p.label}
              />
            </label>
          ))}
        </div>
      </SectionCard>

      <SectionCard eyebrow="About" title="About this system">
        <dl className="kv">
          <dt>Application</dt>
          <dd>{APP_NAME}</dd>
          <dt>Purpose</dt>
          <dd>{APP_TAGLINE}</dd>
          <dt>Problem statement</dt>
          <dd>
            {PROBLEM_STATEMENT.id} — {PROBLEM_STATEMENT.title}
          </dd>
          <dt>Ministry</dt>
          <dd>{PROBLEM_STATEMENT.ministry}</dd>
          <dt>Category / theme</dt>
          <dd>
            {PROBLEM_STATEMENT.category} · {PROBLEM_STATEMENT.theme}
          </dd>
        </dl>
        <div className="demo-note" style={{ marginTop: 'var(--space-4)' }}>
          <Icon name="alert" size={15} />
          <span>
            <strong>{DEMO_DATA_LABEL}.</strong> {DEMO_DATA_NOTICE}
          </span>
        </div>
      </SectionCard>
    </div>
  );
}
