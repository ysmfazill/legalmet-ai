import { useLocation } from 'react-router-dom';

import { Icon } from '../components/Icon';
import { initials } from '../lib/user';
import { cn } from '../lib/cn';
import { useApp } from './AppContext';
import { GlobalSearch } from './GlobalSearch';
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
 * TOP BAR — page title + breadcrumb, the UI-09 global search, backend
 * connection status, notifications and the current inspector. On tablet/mobile
 * it exposes the hamburger that opens the off-canvas sidebar.
 *
 * The notification bell is informational only: with no real notification feed
 * yet it renders no count (a mock count would misrepresent demo data as live).
 */
export function TopBar() {
  const { user, navOpen, setNavOpen } = useApp();
  const location = useLocation();
  const page = resolvePage(location.pathname);

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

      {/* UI-09: command-style global search over every record category. */}
      <GlobalSearch />

      <div className="topbar__actions">
        <ConnectionPill />
        <button
          type="button"
          className="icon-btn"
          aria-label="Notifications"
          title="No new notifications — a real notification feed arrives with live review assignment"
        >
          <Icon name="bell" size={18} />
        </button>
        <span className="avatar" title={`${user.fullName} · signed in`} aria-hidden>
          {initials(user.fullName)}
        </span>
      </div>
    </header>
  );
}
