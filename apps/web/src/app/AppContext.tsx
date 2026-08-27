/* eslint-disable react-refresh/only-export-components */
import { createContext, useContext, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';

import type { HealthResponse, User } from '@legalmet/types';

import { api, ApiClientError } from '../api/client';
import { currentUser } from '../mock/fixtures';

export type Connection =
  | { kind: 'checking' }
  | { kind: 'online'; health: HealthResponse }
  | { kind: 'offline'; message: string };

/**
 * Real backend session. In dev the SPA silently signs in as the seeded
 * inspector so authenticated package intake works without a login screen.
 * When that fails (backend down, seed missing) we fall back to `anonymous`
 * and the demo, mock-backed screens keep working unchanged.
 */
export type Auth =
  | { kind: 'authenticating' }
  | { kind: 'authenticated'; user: User }
  | { kind: 'anonymous'; message: string };

const DEMO_EMAIL = import.meta.env.VITE_DEMO_EMAIL ?? 'inspector@legalmet.local';
const DEMO_PASSWORD = import.meta.env.VITE_DEMO_PASSWORD ?? 'changeme-inspector';

interface AppContextValue {
  /** The active user: the real authenticated inspector, or the DEMO fixture. */
  user: User;
  /** Real backend auth state — gates real (non-demo) package intake. */
  auth: Auth;
  /** True once a real JWT session is established. */
  isLive: boolean;
  /** Live backend connectivity (real `/health` probe). */
  connection: Connection;
  navOpen: boolean;
  setNavOpen: (open: boolean) => void;
}

const AppContext = createContext<AppContextValue | null>(null);

export function AppProvider({ children }: { children: ReactNode }) {
  const [connection, setConnection] = useState<Connection>({ kind: 'checking' });
  const [auth, setAuth] = useState<Auth>({ kind: 'authenticating' });
  const [navOpen, setNavOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api.health().then(
      (health) => {
        if (!cancelled) setConnection({ kind: 'online', health });
      },
      (error: unknown) => {
        if (cancelled) return;
        setConnection({
          kind: 'offline',
          message: error instanceof ApiClientError ? error.message : 'Backend offline',
        });
      },
    );
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    api.login(DEMO_EMAIL, DEMO_PASSWORD).then(
      (result) => {
        if (!cancelled) setAuth({ kind: 'authenticated', user: result.user });
      },
      (error: unknown) => {
        if (cancelled) return;
        const message =
          error instanceof ApiClientError
            ? error.message
            : 'Dev sign-in unavailable — real intake is disabled.';
        setAuth({ kind: 'anonymous', message });
      },
    );
    return () => {
      cancelled = true;
    };
  }, []);

  const value = useMemo<AppContextValue>(
    () => ({
      user: auth.kind === 'authenticated' ? auth.user : currentUser,
      auth,
      isLive: auth.kind === 'authenticated',
      connection,
      navOpen,
      setNavOpen,
    }),
    [auth, connection, navOpen],
  );

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp(): AppContextValue {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error('useApp must be used within an AppProvider');
  return ctx;
}
