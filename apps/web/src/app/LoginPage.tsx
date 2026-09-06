import { useState } from 'react';
import { Link, Navigate, useNavigate } from 'react-router-dom';

import { Icon } from '../components/Icon';
import { useApp } from './AppContext';

export type LoginMode = 'inspector' | 'department';

const MODE_META: Record<
  LoginMode,
  { title: string; blurb: string; destination: string; demoEmail: string; demoPassword: string }
> = {
  inspector: {
    title: 'Inspector Login',
    blurb: 'Authorized inspection personnel — verify complaints, inspect packages, review evidence, decide.',
    destination: '/inspector',
    demoEmail: 'inspector@legalmet.local',
    demoPassword: 'changeme-inspector',
  },
  department: {
    title: 'Department Login',
    blurb: 'Authorized department personnel — review complaints, prioritize cases, assign inspections.',
    destination: '/department',
    demoEmail: 'admin@legalmet.local',
    demoPassword: 'changeme-admin',
  },
};

/**
 * Staff login page (`/login/inspector` · `/login/department`).
 *
 * Real credentials only — POST /auth/login through the app context; nothing is
 * auto-filled or invented. After a successful sign-in the user lands on the
 * mode's workspace. Backend RBAC governs what each role may actually do; the
 * two pages differ only in destination, never in authentication strength.
 */
export function LoginPage({ mode }: { mode: LoginMode }) {
  const meta = MODE_META[mode];
  const { auth, login } = useApp();
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Already signed in (e.g. followed the link from the entry page mid-session)
  // — go straight to the workspace.
  if (auth.kind === 'authenticated') {
    return <Navigate to={meta.destination} replace />;
  }

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (busy) return;
    setError(null);
    setBusy(true);
    try {
      await login(email.trim(), password);
      navigate(meta.destination, { replace: true });
    } catch (err) {
      setError(
        err instanceof Error && err.message
          ? err.message
          : 'Sign-in failed. Check your credentials and try again.',
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="entry">
      <header className="entry__header">
        <span className="entry__logo" aria-hidden>
          <Icon name="scale" size={28} />
        </span>
        <div>
          <h1 className="entry__wordmark">METRASIGHT</h1>
          <p className="entry__tagline">Fair Measures. Trusted Markets.</p>
        </div>
      </header>

      <main className="entry__main entry__main--narrow">
        <section className="login-card">
          <h2 className="login-card__title">{meta.title}</h2>
          <p className="login-card__blurb">{meta.blurb}</p>

          <form className="login-card__form" onSubmit={submit} noValidate>
            <label className="field">
              <span className="field__label">Email</span>
              <input
                type="email"
                name="email"
                autoComplete="username"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="name@department.gov.in"
                disabled={busy}
              />
            </label>
            <label className="field">
              <span className="field__label">Password</span>
              <input
                type="password"
                name="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                disabled={busy}
              />
            </label>

            {error && (
              <p className="login-card__error" role="alert">
                {error}
              </p>
            )}

            <button type="submit" className="btn btn--primary btn--block" disabled={busy}>
              {busy ? 'Signing in…' : 'Sign in'}
            </button>
          </form>

          <p className="login-card__demo-hint">
            Demo build credentials: <code>{meta.demoEmail}</code> /{' '}
            <code>{meta.demoPassword}</code>
          </p>

          <Link to="/" className="login-card__back">
            Back to entry
          </Link>
        </section>
      </main>
    </div>
  );
}
