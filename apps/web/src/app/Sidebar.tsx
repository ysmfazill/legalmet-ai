import { NavLink } from 'react-router-dom';

import { RoleBadge } from '../components/Badge';
import { Icon } from '../components/Icon';
import { cn } from '../lib/cn';
import { useApp } from './AppContext';
import {
  CITIZEN_NAV,
  PRIMARY_NAV,
  SYSTEM_NAV,
  WORKSPACE_NAV,
  navFor,
} from './nav';
import type { NavItem } from './nav';

/** Two-letter initials for the avatar chip. */
function initials(name: string): string {
  const parts = name.replace(/^Dr\.?\s+/i, '').trim().split(/\s+/);
  return ((parts[0]?.[0] ?? '') + (parts[1]?.[0] ?? '')).toUpperCase() || '–';
}

function NavRow({
  item,
  badgeCount,
  onNavigate,
}: {
  item: NavItem;
  badgeCount?: number;
  onNavigate: () => void;
}) {
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
      {badgeCount !== undefined && badgeCount > 0 && (
        <span className="nav-item__badge">{badgeCount}</span>
      )}
    </NavLink>
  );
}

/**
 * LEFT SIDEBAR — the platform's primary navigation. Carries the wordmark, the
 * "New inspection" call to action, the destinations of the inspection
 * workflow (role-gated to mirror backend RBAC), Citizen Mode, and the
 * signed-in user's identity + role. The review badge only renders from a real
 * session — in demo mode it stays hidden so mock counts never leak as if live.
 */
export function Sidebar() {
  const { user, isLive, setNavOpen } = useApp();
  const close = () => setNavOpen(false);

  const primary = navFor(PRIMARY_NAV, user.role);
  const workspace = navFor(WORKSPACE_NAV, user.role);
  const system = navFor(SYSTEM_NAV, user.role);
  /** Mock counts are demo-only; the live engine queue is surfaced on the
   * Review page itself, so the badge is suppressed unless live. */
  const reviewBadge = 0;
  const canInspect = user.role === 'ADMIN' || user.role === 'INSPECTOR' || user.role === 'SUPERVISOR';

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

      {canInspect && (
        <div className="sidebar__cta">
          <NavLink to="/inspections/new" onClick={close} className="btn btn--primary btn--block">
            <Icon name="plus" size={16} />
            New inspection
          </NavLink>
        </div>
      )}

      <nav className="sidebar__nav">
        {primary.map((item) => (
          <NavRow
            key={item.to}
            item={item}
            badgeCount={isLive && item.badge === 'review' ? reviewBadge : undefined}
            onNavigate={close}
          />
        ))}
        {(workspace.length > 0 || system.length > 0) && (
          <div className="sidebar__section">Workspaces</div>
        )}
        {workspace.map((item) => (
          <NavRow key={item.to} item={item} onNavigate={close} />
        ))}
        {system.map((item) => (
          <NavRow key={item.to} item={item} onNavigate={close} />
        ))}
        <div className="sidebar__section">Public</div>
        {CITIZEN_NAV.map((item) => (
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
