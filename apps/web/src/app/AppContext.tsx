/* eslint-disable react-refresh/only-export-components */
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';

import type { HealthResponse, User } from '@legalmet/types';

import { api, ApiClientError, getToken } from '../api/client';
import { currentUser } from '../mock/fixtures';

export type Connection =
  | { kind: 'checking' }
  | { kind: 'online'; health: HealthResponse }
  | { kind: 'offline'; message: string };

/**
 * Real backend session. Staff (Inspector / Department) MUST authenticate
 * through the login pages — there is no silent sign-in. A previously stored
 * JWT is restored on load via GET /auth/me; when no token exists (or it is
 * rejected) the app is `anonymous`: Citizen Mode still works (it is public
 * by design) and every staff route redirects to the entry page.
 *
 * `user` still falls back to the DEMO fixture when anonymous so the
 * mock-backed demo screens keep rendering unchanged — it grants nothing
 * (the backend rejects unauthenticated staff API calls with 401).
 */
export type Auth =
  | { kind: 'authenticating' }
  | { kind: 'authenticated'; user: User }
  | { kind: 'anonymous'; message: string };

interface AppContextValue {
  /** The active user: the real authenticated staff user, or the DEMO fixture. */
  user: User;
  /** Real backend auth state — gates every staff route. */
  auth: Auth;
  /** True once a real JWT session is established. */
  isLive: boolean;
  /** Live backend connectivity (real `/health` probe). */
  connection: Connection;
  navOpen: boolean;
  setNavOpen: (open: boolean) => void;
  /** Sign in with real credentials (POST /auth/login). Throws on failure. */
  login: (email: string, password: string) => Promise<User>;
  /** Drop the stored token and return to the public entry page. */
  logout: () => void;
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

  // Session restore: only a previously stored token is honoured. No token →
  // anonymous immediately (no credentials are ever invented or auto-tried).
  useEffect(() => {
    let cancelled = false;
    if (!getToken()) {
      setAuth({ kind: 'anonymous', message: 'Not signed in.' });
      return;
    }
    api.me().then(
      (user) => {
        if (!cancelled) setAuth({ kind: 'authenticated', user });
      },
      () => {
        if (cancelled) return;
        api.logout(); // stale/rejected token — drop it
        setAuth({ kind: 'anonymous', message: 'Session expired — sign in again.' });
      },
    );
    return () => {
      cancelled = true;
    };
  }, []);

  const login = useCallback(async (email: string, password: string): Promise<User> => {
    const result = await api.login(email, password);
    setAuth({ kind: 'authenticated', user: result.user });
    return result.user;
  }, []);

  const logout = useCallback(() => {
    api.logout();
    setAuth({ kind: 'anonymous', message: 'Signed out.' });
    setNavOpen(false);
  }, []);

  const value = useMemo<AppContextValue>(
    () => ({
      user: auth.kind === 'authenticated' ? auth.user : currentUser,
      auth,
      isLive: auth.kind === 'authenticated',
      connection,
      navOpen,
      setNavOpen,
      login,
      logout,
    }),
    [auth, connection, navOpen, login, logout],
  );

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp(): AppContextValue {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error('useApp must be used within an AppProvider');
  return ctx;
}
