import { Outlet } from 'react-router-dom';

import { cn } from '../lib/cn';
import { useApp } from './AppContext';
import { Sidebar } from './Sidebar';
import { TopBar } from './TopBar';

/**
 * Application shell: fixed left sidebar + a main column (top bar over a
 * scrollable content region). On tablet/mobile the sidebar becomes an
 * off-canvas drawer toggled via `navOpen`, dimmed by a tap-to-close scrim.
 */
export function AppShell() {
  const { navOpen, setNavOpen } = useApp();
  return (
    <div className={cn('app-shell', navOpen && 'is-nav-open')}>
      <Sidebar />
      <div className="main-col">
        <TopBar />
        <main className="content" id="main-content">
          <Outlet />
        </main>
      </div>
      <div className="sidebar__scrim" onClick={() => setNavOpen(false)} aria-hidden />
    </div>
  );
}
