import { Link, NavLink } from 'react-router-dom';

import { Icon } from '../components/Icon';

/**
 * CITIZEN HOME (Checkpoint 1) — mobile-first consumer entry.
 *
 * Deliberately does NOT look like the inspector dashboard: no sidebar chrome
 * (the shell nav is hidden on citizen routes), no metrics, no regulatory
 * vocabulary. One hero action: SCAN PRODUCT.
 */
const NAV_CARDS = [
  {
    to: '/citizen/reports',
    icon: 'inspections' as const,
    title: 'My reports',
    desc: 'Reports you submitted from this device and their status.',
  },
  {
    to: '/citizen/help',
    icon: 'info' as const,
    title: 'Help',
    desc: 'What to scan, what "possible issue" means, what happens next.',
  },
];

export function CitizenHomePage() {
  return (
    <div className="citizen-page">
      <header className="citizen-page__header">
        <span className="citizen-brand" aria-hidden>
          <Icon name="shield" size={18} />
        </span>
        <div>
          <div className="citizen-brand__name">METRASIGHT</div>
          <div className="citizen-brand__sub">Package Compliance Check</div>
        </div>
      </header>

      <section className="citizen-hero">
        <div className="citizen-hero__scan-icon" aria-hidden>
          <Icon name="camera" size={30} />
        </div>
        <h1 className="citizen-hero__title">Check your package</h1>
        <p className="citizen-hero__lead">
          Scan a packaged product to identify possible declaration or labeling issues.
        </p>
        <Link to="/citizen/scan" className="btn btn--primary btn--lg citizen-hero__cta">
          <Icon name="camera" size={18} />
          Scan product
        </Link>
        <p className="citizen-hero__note">
          Free · No account needed · Your photo stays attached to your report
        </p>
      </section>

      <nav className="citizen-page__nav" aria-label="Citizen sections">
        {NAV_CARDS.map((card) => (
          <NavLink key={card.to} to={card.to} className="citizen__nav-card">
            <span className="citizen__scan-icon" style={{ width: 44, height: 44 }} aria-hidden>
              <Icon name={card.icon} size={20} />
            </span>
            <span>
              <span className="citizen__nav-title">{card.title}</span>
              <span className="citizen-hero__note" style={{ marginTop: 2 }}>{card.desc}</span>
            </span>
            <Icon name="arrowRight" size={16} />
          </NavLink>
        ))}
      </nav>

      <p className="citizen-footnote">
        METRASIGHT provides automated screening and evidence support. Official
        determination is made by the authorized Legal Metrology department.
      </p>
    </div>
  );
}
