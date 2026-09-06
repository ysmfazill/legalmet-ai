import { Link } from 'react-router-dom';

import { Icon } from '../components/Icon';

/**
 * PUBLIC ENTRY PAGE (`/`) — the single front door to METRASIGHT.
 *
 * Three access modes, one honest split:
 *  - CITIZEN   — anonymous, no account, straight into Citizen Mode.
 *  - INSPECTOR — real staff authentication, lands on the Inspector Workspace.
 *  - DEPARTMENT — real staff authentication, lands on the Department Command
 *    Center.
 *
 * No credentials are ever created or implied here; the citizen path asks for
 * nothing, and both staff paths hand over to the real login flow.
 */
export function EntryPage() {
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

      <main className="entry__main">
        <h2 className="entry__question">How are you accessing METRASIGHT?</h2>

        <div className="entry__cards">
          {/* CITIZEN — the prominent public entry: no account, no forms. */}
          <section className="entry-card entry-card--citizen">
            <span className="entry-card__icon" aria-hidden>
              <Icon name="citizen" size={26} />
            </span>
            <h3 className="entry-card__title">Citizen</h3>
            <p className="entry-card__desc">
              Scan a package, identify suspected issues, and report them.
            </p>
            <Link to="/citizen" className="btn btn--primary entry-card__cta">
              Continue as Citizen
              <Icon name="arrowRight" size={16} />
            </Link>
            <span className="entry-card__footnote">No account required</span>
          </section>

          <section className="entry-card">
            <span className="entry-card__icon" aria-hidden>
              <Icon name="inspections" size={26} />
            </span>
            <h3 className="entry-card__title">Inspector</h3>
            <p className="entry-card__desc">
              Verify complaints, inspect packages, review evidence, and make decisions.
            </p>
            <Link to="/login/inspector" className="btn btn--outline entry-card__cta">
              Inspector Login
              <Icon name="arrowRight" size={16} />
            </Link>
            <span className="entry-card__footnote">Authorized personnel</span>
          </section>

          <section className="entry-card">
            <span className="entry-card__icon" aria-hidden>
              <Icon name="department" size={26} />
            </span>
            <h3 className="entry-card__title">Department</h3>
            <p className="entry-card__desc">
              Review complaints, prioritize cases, assign inspections, and monitor operations.
            </p>
            <Link to="/login/department" className="btn btn--outline entry-card__cta">
              Department Login
              <Icon name="arrowRight" size={16} />
            </Link>
            <span className="entry-card__footnote">Authorized personnel</span>
          </section>
        </div>

        <p className="entry__note">
          AI-assisted decision support. Evidence supports, rules govern — the
          authorized inspector decides.
        </p>
      </main>
    </div>
  );
}
