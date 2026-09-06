import { Link } from 'react-router-dom';

import { Icon } from '../components/Icon';

/**
 * HELP (Checkpoint 11) — plain words for someone who has never heard of
 * Legal Metrology. The one non-negotiable line: METRASIGHT screens
 * automatically; the authorized department or inspector makes the official
 * determination.
 */
const FAQS = [
  {
    q: 'What can I scan?',
    a: 'Any pre-packaged product you bought — food, drink, cosmetics, household items. Photograph the label side that shows the price, weight, dates and maker details.',
  },
  {
    q: 'What does "possible issue" mean?',
    a: 'The system could not read something the rules expect on a package — for example the MRP or the expiry date. It does NOT mean the product is illegal. Only the Legal Metrology department can decide that.',
  },
  {
    q: 'Does METRASIGHT make an official legal decision?',
    a: 'No. METRASIGHT provides automated screening and evidence support. Official determination is made by the authorized department or inspector.',
  },
  {
    q: 'How do I report an issue?',
    a: 'Scan the package, review what the system found, then submit a short report. Your photo, the readings and a reference number go with it. Keep the package and the bill if you can.',
  },
  {
    q: 'What happens after I submit?',
    a: 'Your report goes to the Legal Metrology department with the scan evidence. An officer reviews it and may inspect the shop. Your reference number lets you ask about the status.',
  },
];

export function CitizenHelpPage() {
  return (
    <div className="citizen-page">
      <div className="citizen-page__topbar">
        <Link to="/citizen" className="btn btn--ghost btn--sm">
          <Icon name="chevronLeft" size={15} />
          Home
        </Link>
        <span className="citizen-step__label">Help</span>
      </div>

      <h1 className="citizen-page__title">Help</h1>
      <p className="citizen-page__lead">Common questions, in plain words.</p>

      <div className="citizen-faqs">
        {FAQS.map((f) => (
          <details key={f.q} className="citizen-faq">
            <summary>{f.q}</summary>
            <p>{f.a}</p>
          </details>
        ))}
      </div>

      <div className="citizen-attached" role="note">
        <Icon name="shield" size={15} />
        <span>
          METRASIGHT provides automated screening and evidence support. Official
          determination is made by the authorized department or inspector.
        </span>
      </div>

      <Link to="/citizen/scan" className="btn btn--primary btn--lg" style={{ marginTop: 'var(--space-4)' }}>
        <Icon name="camera" size={18} />
        Scan a product
      </Link>
    </div>
  );
}
