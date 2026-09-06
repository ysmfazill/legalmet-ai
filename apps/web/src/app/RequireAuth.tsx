import { Navigate, useLocation } from 'react-router-dom';
import type { ReactNode } from 'react';

import { useApp } from './AppContext';
import { LoadingState } from '../components/states';

/**
 * Route guard for the staff workspace. Anonymous visitors (including anyone
 * coming from Citizen Mode) are sent back to the public entry page — never to
 * a staff screen. This is UX routing only: real security is the backend's
 * per-endpoint JWT + role checks, which reject unauthenticated/under-privileged
 * calls regardless of what the frontend renders.
 */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { auth } = useApp();
  const location = useLocation();

  if (auth.kind === 'authenticating') {
    return <LoadingState label="Restoring session…" />;
  }
  if (auth.kind === 'anonymous') {
    return <Navigate to="/" replace state={{ from: location.pathname }} />;
  }
  return <>{children}</>;
}
