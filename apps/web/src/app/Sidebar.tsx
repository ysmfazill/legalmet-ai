import { NavLink } from 'react-router-dom';

import { RoleBadge } from '../components/Badge';
import { Icon } from '../components/Icon';
import { cn } from '../lib/cn';
import { reviewQueue } from '../mock/aggregates';
import { useApp } from './AppContext';
import { PRIMARY_NAV, SYSTEM_NAV } from './nav';
import type { NavItem } from './nav';

/** Two-letter initials for the avatar chip. */
function initials(name: string): string {
  const parts = name.replace(/^Dr\.?\s+/i, '').trim().split(/\s+/);
  return ((parts[0]?.[0] ?? '') + (parts[1]?.[0] ?? '')).toUpperCase() || '–';
}

function NavRow({ item, onNavigate }: { item: NavItem; onNavigate: () => void }) {
  const badgeCount = item.badge === 'review' ? reviewQueue.length : 0;
  return (
    <NavLink
      to={item.to}
      end={item.end}
      onClick={onNavigate}
      className={({ isActive }) => cn('nav-item', isActive && 'is-active')}
    >
      <span className="nav-item__icon">
        <Icon name={item.icon} size={18} />
      </span>
      <span>{item.label}</span>
      {badgeCount > 0 && <span className="nav-item__badge">{badgeCount}</span>}
    </NavLink>
  );
}

/**
 * LEFT SIDEBAR — the platform's primary navigation. Carries the wordmark, the
 * "New inspection" call to action, the 10 destinations of the inspection
 * workflow, and the signed-in inspector's identity + role.
 */
export function Sidebar() {
  const { user, setNavOpen } = useApp();
  const close = () => setNavOpen(false);

  return (
    <aside className="sidebar" aria-label="Primary navigation">
      <div className="sidebar__brand">
        <span className="sidebar__logo" aria-hidden>
          <Icon name="scale" size={20} />
        </span>
        <span className="sidebar__wordmark">
          METRASIGHT
          <span>LEGAL METROLOGY INSPECTION INTELLIGENCE</span>
        </span>
      </div>

      <div className="sidebar__cta">
        <NavLink to="/inspections/new" onClick={close} className="btn btn--primary btn--block">
          <Icon name="plus" size={16} />
          New inspection
        </NavLink>
      </div>

      <nav className="sidebar__nav">
        {PRIMARY_NAV.map((item) => (
          <NavRow key={item.to} item={item} onNavigate={close} />
        ))}
        <div className="sidebar__section">System</div>
        {SYSTEM_NAV.map((item) => (
          <NavRow key={item.to} item={item} onNavigate={close} />
        ))}
      </nav>

      <div className="sidebar__user">
        <span className="avatar" aria-hidden>
          {initials(user.fullName)}
        </span>
        <div className="sidebar__user-meta">
          <div className="sidebar__user-name">{user.fullName}</div>
          <RoleBadge role={user.role} />
        </div>
      </div>
    </aside>
  );
}
