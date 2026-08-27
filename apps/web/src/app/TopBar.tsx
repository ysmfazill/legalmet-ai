import { useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';

import { Icon } from '../components/Icon';
import { SearchBar } from '../components/inputs';
import { cn } from '../lib/cn';
import { reviewQueue } from '../mock/aggregates';
import { useApp } from './AppContext';
import { resolvePage } from './nav';

const CONN_LABEL: Record<string, string> = {
  checking: 'Checking backend…',
  online: 'Backend online',
  offline: 'Backend offline',
};

function ConnectionPill() {
  const { connection } = useApp();
  const kind = connection.kind;
  const detail =
    connection.kind === 'online'
      ? `API ${connection.health.status}`
      : connection.kind === 'offline'
        ? connection.message
        : 'Probing /health';
  return (
    <span
      className={cn('conn', kind === 'online' && 'conn--online', kind === 'offline' && 'conn--offline')}
      title={detail}
    >
      <span className="conn__dot" aria-hidden />
      <span className="hide-sm">{CONN_LABEL[kind]}</span>
    </span>
  );
}

/**
 * TOP BAR — page title + breadcrumb, a global inspection search, backend
 * connection status, notifications and the current inspector. On tablet/mobile
 * it exposes the hamburger that opens the off-canvas sidebar.
 */
export function TopBar() {
  const { user, navOpen, setNavOpen } = useApp();
  const location = useLocation();
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  const page = resolvePage(location.pathname);
  const pendingReviews = reviewQueue.length;

  function submitSearch(e: React.FormEvent) {
    e.preventDefault();
    navigate(query.trim() ? `/inspections?q=${encodeURIComponent(query.trim())}` : '/inspections');
  }

  return (
    <header className="topbar">
      <button
        type="button"
        className="icon-btn topbar__menu"
        aria-label={navOpen ? 'Close navigation' : 'Open navigation'}
        aria-expanded={navOpen}
        onClick={() => setNavOpen(!navOpen)}
      >
        <Icon name={navOpen ? 'close' : 'menu'} size={20} />
      </button>

      <div className="topbar__titles">
        {page.breadcrumb.length > 1 && (
          <nav className="breadcrumb" aria-label="Breadcrumb">
            {page.breadcrumb.map((crumb, i) => (
              <span key={crumb} className="row" style={{ gap: 6 }}>
                {i > 0 && <span className="breadcrumb__sep" aria-hidden>/</span>}
                {crumb}
              </span>
            ))}
          </nav>
        )}
        <div className="topbar__title">{page.title}</div>
      </div>

      <form className="topbar__search" onSubmit={submitSearch} role="search">
        <SearchBar
          value={query}
          onChange={setQuery}
          placeholder="Search inspections, references…"
          ariaLabel="Search inspections"
        />
      </form>

      <div className="topbar__actions">
        <ConnectionPill />
        <button
          type="button"
          className="icon-btn"
          aria-label={pendingReviews > 0 ? `Notifications: ${pendingReviews} awaiting review` : 'Notifications'}
          title={pendingReviews > 0 ? `${pendingReviews} findings awaiting review` : 'No new notifications'}
        >
          <Icon name="bell" size={18} />
          {pendingReviews > 0 && <span className="icon-btn__dot" aria-hidden />}
        </button>
        <span className="avatar" title={`${user.fullName} · signed in`} aria-hidden>
          {(user.fullName.replace(/^Dr\.?\s+/i, '').split(/\s+/).map((p) => p[0]).slice(0, 2).join('') || '–').toUpperCase()}
        </span>
      </div>
    </header>
  );
}
