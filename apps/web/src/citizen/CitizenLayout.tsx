import { Link, Outlet } from 'react-router-dom';

import { Icon } from '../components/Icon';
import { CitizenSessionProvider } from './session';

/**
 * Citizen shell — a deliberately separate layout from the inspector
 * AppShell: no sidebar, no top bar chrome, no role context. The consumer
 * experience is a centered, width-constrained column (max ~560px) that
 * works identically on a phone and a desktop browser.
 *
 * Security note: citizen routes render no department data at all. The
 * inspector app lives under its own shell with its own routing; this tree
 * simply never mounts the components that would call authenticated APIs.
 */
export function CitizenLayout() {
  return (
    <CitizenSessionProvider>
      <div className="citizen-root">
        <Link to="/inspections" className="citizen-root__staff-link">
          Inspector sign-in
          <Icon name="arrowRight" size={12} />
        </Link>
        <Outlet />
      </div>
    </CitizenSessionProvider>
  );
}
