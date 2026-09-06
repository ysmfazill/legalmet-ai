// @vitest-environment jsdom
//
// Entry-flow tests — the public front door, the staff login pages, and the
// staff-route guard. The api client is mocked at the module boundary; the
// routing, guard, context and pages are the real implementations.

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { MemoryRouter, Route, Routes } from 'react-router-dom';

import type { AuthTokenResponse, User } from '@legalmet/types';

const meMock = vi.fn<() => Promise<User>>();
const loginMock = vi.fn<(email: string, password: string) => Promise<AuthTokenResponse>>();
const healthMock = vi.fn<() => Promise<unknown>>();
const logoutMock = vi.fn();
const getTokenMock = vi.fn<() => string | null>();

vi.mock('../api/client', () => ({
  api: {
    health: (...a: unknown[]) => healthMock(...(a as [])),
    me: () => meMock(),
    login: (e: string, p: string) => loginMock(e, p),
    logout: () => logoutMock(),
  },
  ApiClientError: class ApiClientError extends Error {},
  getToken: () => getTokenMock(),
}));

import { AppProvider } from './AppContext';
import { EntryPage } from './EntryPage';
import { LoginPage } from './LoginPage';
import { RequireAuth } from './RequireAuth';
import { AppShell } from './AppShell';
import { CitizenLayout } from '../citizen/CitizenLayout';
import { CitizenHomePage } from '../citizen/CitizenHome';

const USER: User = {
  id: 'u1',
  email: 'inspector@legalmet.local',
  fullName: 'Demo Inspector',
  role: 'INSPECTOR',
  isActive: true,
  createdAt: '2026-01-01T00:00:00Z',
};

const TOKEN_RESPONSE: AuthTokenResponse = {
  accessToken: 'jwt-token',
  tokenType: 'bearer',
  expiresIn: 3600,
  user: USER,
};

/** Mirror of the production route table (App.tsx) with stub staff pages. */
function renderApp(initial: string) {
  return render(
    <MemoryRouter initialEntries={[initial]}>
      <AppProvider>
        <Routes>
          <Route index element={<EntryPage />} />
          <Route path="login/inspector" element={<LoginPage mode="inspector" />} />
          <Route path="login/department" element={<LoginPage mode="department" />} />
          <Route element={<AppShell />}>
            <Route path="citizen" element={<CitizenLayout />}>
              <Route index element={<CitizenHomePage />} />
            </Route>
          </Route>
          <Route
            element={
              <RequireAuth>
                <AppShell />
              </RequireAuth>
            }
          >
            <Route path="dashboard" element={<div data-testid="staff-dashboard" />} />
            <Route path="inspector" element={<div data-testid="inspector-page" />} />
            <Route path="department" element={<div data-testid="department-page" />} />
          </Route>
        </Routes>
      </AppProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  healthMock.mockResolvedValue({ status: 'ok' });
  getTokenMock.mockReturnValue(null);
  meMock.mockReset();
  loginMock.mockReset();
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('EntryPage (public front door)', () => {
  it('renders the METRASIGHT identity, the access question and all three modes', () => {
    renderApp('/');
    expect(screen.getByText('METRASIGHT')).toBeTruthy();
    expect(screen.getByText('Fair Measures. Trusted Markets.')).toBeTruthy();
    expect(screen.getByText('How are you accessing METRASIGHT?')).toBeTruthy();
    expect(screen.getByRole('link', { name: /Continue as Citizen/i })).toBeTruthy();
    expect(screen.getByRole('link', { name: /Inspector Login/i })).toBeTruthy();
    expect(screen.getByRole('link', { name: /Department Login/i })).toBeTruthy();
    expect(screen.getByText('No account required')).toBeTruthy();
    expect(screen.getAllByText('Authorized personnel')).toHaveLength(2);
  });

  it('Continuing as Citizen goes straight to Citizen Home — no login form anywhere', async () => {
    renderApp('/');
    fireEvent.click(screen.getByRole('link', { name: /Continue as Citizen/i }));
    await waitFor(() => {
      // Citizen Home renders inside its own layout.
      expect(screen.queryByText('How are you accessing METRASIGHT?')).toBeNull();
    });
    expect(screen.queryByLabelText(/password/i)).toBeNull();
    expect(screen.queryByRole('button', { name: /sign in/i })).toBeNull();
  });

  it('Inspector Login and Department Login lead to their login pages', async () => {
    renderApp('/');
    fireEvent.click(screen.getByRole('link', { name: /Inspector Login/i }));
    await waitFor(() => expect(screen.getByText('Inspector Login')).toBeTruthy());

    cleanup();
    renderApp('/');
    fireEvent.click(screen.getByRole('link', { name: /Department Login/i }));
    await waitFor(() => expect(screen.getByText('Department Login')).toBeTruthy());
  });
});

describe('RequireAuth (staff routes)', () => {
  it('redirects an anonymous visitor straight back to the entry page', async () => {
    renderApp('/dashboard');
    await waitFor(() => {
      expect(screen.getByText('How are you accessing METRASIGHT?')).toBeTruthy();
    });
    expect(screen.queryByTestId('staff-dashboard')).toBeNull();
  });

  it('blocks anonymous access to /inspector and /department too', async () => {
    renderApp('/inspector');
    await waitFor(() =>
      expect(screen.getByText('How are you accessing METRASIGHT?')).toBeTruthy(),
    );
    expect(screen.queryByTestId('inspector-page')).toBeNull();

    cleanup();
    renderApp('/department');
    await waitFor(() =>
      expect(screen.getByText('How are you accessing METRASIGHT?')).toBeTruthy(),
    );
    expect(screen.queryByTestId('department-page')).toBeNull();
  });

  it('restores an authenticated session from a stored token (refresh keeps staff in)', async () => {
    getTokenMock.mockReturnValue('stored-jwt');
    meMock.mockResolvedValue(USER);
    renderApp('/dashboard');
    await waitFor(() => expect(screen.getByTestId('staff-dashboard')).toBeTruthy());
  });

  it('drops a rejected token and falls back to the entry page', async () => {
    getTokenMock.mockReturnValue('stale-jwt');
    meMock.mockRejectedValue(new Error('401'));
    renderApp('/dashboard');
    await waitFor(() =>
      expect(screen.getByText('How are you accessing METRASIGHT?')).toBeTruthy(),
    );
    expect(logoutMock).toHaveBeenCalled();
  });
});

describe('LoginPage (staff authentication)', () => {
  it('signs an inspector in with real credentials and lands on the Inspector Workspace', async () => {
    loginMock.mockResolvedValue(TOKEN_RESPONSE);
    renderApp('/login/inspector');

    fireEvent.change(screen.getByLabelText(/email/i), {
      target: { value: 'inspector@legalmet.local' },
    });
    fireEvent.change(screen.getByLabelText(/password/i), {
      target: { value: 'changeme-inspector' },
    });
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }));

    await waitFor(() => expect(screen.getByTestId('inspector-page')).toBeTruthy());
    expect(loginMock).toHaveBeenCalledWith(
      'inspector@legalmet.local',
      'changeme-inspector',
    );
  });

  it('department login lands on the Department Command Center', async () => {
    loginMock.mockResolvedValue({ ...TOKEN_RESPONSE, user: { ...USER, role: 'ADMIN' } });
    renderApp('/login/department');

    fireEvent.change(screen.getByLabelText(/email/i), {
      target: { value: 'admin@legalmet.local' },
    });
    fireEvent.change(screen.getByLabelText(/password/i), {
      target: { value: 'changeme-admin' },
    });
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }));

    await waitFor(() => expect(screen.getByTestId('department-page')).toBeTruthy());
  });

  it('shows the backend rejection honestly and stays on the login page', async () => {
    loginMock.mockRejectedValue(new Error('Invalid credentials'));
    renderApp('/login/inspector');

    fireEvent.change(screen.getByLabelText(/email/i), {
      target: { value: 'inspector@legalmet.local' },
    });
    fireEvent.change(screen.getByLabelText(/password/i), {
      target: { value: 'wrong-password' },
    });
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }));

    await waitFor(() => expect(screen.getByRole('alert')).toBeTruthy());
    expect(screen.getByRole('alert').textContent).toMatch(/invalid credentials/i);
    expect(screen.getByText('Inspector Login')).toBeTruthy(); // still on login
    expect(loginMock).toHaveBeenCalledTimes(1);
  });

  it('never auto-signs-in: visiting the login page anonymous shows the empty form', () => {
    renderApp('/login/inspector');
    expect((screen.getByLabelText(/email/i) as HTMLInputElement).value).toBe('');
    expect((screen.getByLabelText(/password/i) as HTMLInputElement).value).toBe('');
    expect(loginMock).not.toHaveBeenCalled();
  });
});
