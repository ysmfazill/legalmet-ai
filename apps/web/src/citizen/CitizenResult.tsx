import { Link, useNavigate } from 'react-router-dom';

import { Icon } from '../components/Icon';
import type { CitizenDetectedField, CitizenScanResult } from '@legalmet/types';
import { useCitizenSession } from './session';
import { cn } from '../lib/cn';

/**
 * SCAN RESULT (Checkpoint 5) — the real backend outcome, honestly rendered.
 *
 * Outcome states and their fixed language contract (never "violation
 * confirmed" — official determination belongs to the department):
 *   NO_OBVIOUS_ISSUE   → "No obvious issue detected" + screening disclaimer
 *   POSSIBLE_ISSUE     → "Possible issue detected" + WHY + evidence + report CTA
 *   REVIEW_REQUIRED    → "More verification needed" + scan again
 *   INSUFFICIENT_EVIDENCE → "Insufficient evidence" + capture more evidence
 *   IMAGE_UNREADABLE   → quality gate failed + retake CTA (never silently pass)
 */
export function CitizenResultPage() {
  const { scan } = useCitizenSession();
  const navigate = useNavigate();

  if (!scan) {
    return (
      <div className="citizen-page">
        <div className="citizen-page__topbar">
          <Link to="/citizen/scan" className="btn btn--ghost btn--sm">
            <Icon name="chevronLeft" size={15} />
            Back
          </Link>
          <span className="citizen-step__label">Result</span>
        </div>
        <div className="citizen-empty">
          <span className="citizen__scan-icon" aria-hidden>
            <Icon name="camera" size={24} />
          </span>
          <h1>No scan yet</h1>
          <p className="cell-muted">Scan a package first — the result will appear here.</p>
          <Link to="/citizen/scan" className="btn btn--primary">
            <Icon name="camera" size={16} />
            Scan product
          </Link>
        </div>
      </div>
    );
  }

  const detected = scan.detectedFields.filter((f) => f.status !== 'NOT_EXTRACTED');
  const readable = scan.quality.readable;

  return (
    <div className="citizen-page">
      <div className="citizen-page__topbar">
        <Link to="/citizen" className="btn btn--ghost btn--sm">
          <Icon name="chevronLeft" size={15} />
          Home
        </Link>
        <span className="citizen-step__label">Scan result</span>
        <span className="citizen-step__count" aria-hidden>2 / 2</span>
      </div>

      <OutcomeCard scan={scan} />

      {readable && detected.length > 0 && (
        <section className="citizen-section" aria-label="Detected information">
          <h2 className="citizen-section__title">Detected information</h2>
          <p className="cell-muted" style={{ marginBottom: 'var(--space-3)' }}>
            Read from your photo by the system. Check it against the package.
          </p>
          <ul className="citizen-fields">
            {detected.map((f) => (
              <DetectedRow key={`${f.fieldType}-${f.rawText}`} field={f} />
            ))}
          </ul>
        </section>
      )}

      <div className="citizen-actions">
        {scan.outcome === 'IMAGE_UNREADABLE' ? (
          <Link to="/citizen/scan" className="btn btn--primary">
            <Icon name="camera" size={16} />
            Retake photo
          </Link>
        ) : scan.outcome === 'POSSIBLE_ISSUE' ? (
          <>
            <button
              type="button"
              className="btn btn--primary"
              onClick={() => navigate('/citizen/report')}
            >
              <Icon name="complaints" size={16} />
              Report this issue
            </button>
            <Link to="/citizen/scan" className="btn btn--ghost">
              Scan another
            </Link>
          </>
        ) : scan.outcome === 'NO_OBVIOUS_ISSUE' ? (
          <>
            <Link to="/citizen" className="btn btn--primary">
              <Icon name="check" size={16} />
              Done
            </Link>
            <Link to="/citizen/scan" className="btn btn--ghost">
              Scan another
            </Link>
          </>
        ) : (
          <>
            <Link to="/citizen/scan" className="btn btn--primary">
              <Icon name="camera" size={16} />
              Scan again
            </Link>
            <Link to="/citizen/help" className="btn btn--ghost">
              Help
            </Link>
          </>
        )}
      </div>

      <p className="citizen-footnote">
        Scan reference {scan.reference} · This scan is an automated screening
        result and does not constitute an official Legal Metrology determination.
      </p>
    </div>
  );
}

function OutcomeCard({ scan }: { scan: CitizenScanResult }) {
  if (scan.outcome === 'NO_OBVIOUS_ISSUE') {
    return (
      <section className={cn('citizen-outcome', 'citizen-outcome--positive')} aria-live="polite">
        <span className="citizen__outcome-icon citizen__outcome-icon--positive" aria-hidden>
          <Icon name="check" size={22} />
        </span>
        <div>
          <h1 className="citizen__outcome-title">No obvious issue detected</h1>
          <p>We did not identify an obvious declaration issue from this image.</p>
          {scan.outcomeRationale && <p className="cell-muted">{scan.outcomeRationale}</p>}
        </div>
      </section>
    );
  }

  if (scan.outcome === 'POSSIBLE_ISSUE') {
    return (
      <section className={cn('citizen-outcome', 'citizen-outcome--warning')} aria-live="polite">
        <span className="citizen__outcome-icon citizen__outcome-icon--warning" aria-hidden>
          <Icon name="alert" size={22} />
        </span>
        <div className="stack stack--sm">
          <h1 className="citizen__outcome-title">Possible issue detected</h1>
          <p>{scan.outcomeRationale ?? 'The package information appears inconsistent with the expected declaration.'}</p>

          <details className="citizen-why">
            <summary>Why?</summary>
            <p className="cell-muted">
              The expected declarations could not all be read from the label. This can mean
              they are missing — or that the photo does not show them.
            </p>
          </details>

          <details className="citizen-why">
            <summary>View evidence</summary>
            <ul className="citizen-evidence">
              <li>
                <Icon name="image" size={14} />
                Package photo ({scan.filename})
              </li>
              <li>
                <Icon name="check" size={14} />
                {scan.detectedFields.length} declarations read from the image
              </li>
              {scan.ocrModel && (
                <li>
                  <Icon name="shield" size={14} />
                  Read by {scan.ocrModel}
                </li>
              )}
            </ul>
            {scan.imageUrl && (
              <img
                className="citizen-evidence__img"
                src={scan.imageUrl}
                alt="The package photo you submitted"
              />
            )}
          </details>

          <p className="citizen-footnote" style={{ margin: 0 }}>
            This is not a confirmed violation. Only the Legal Metrology department
            can determine that.
          </p>
        </div>
      </section>
    );
  }

  if (scan.outcome === 'IMAGE_UNREADABLE') {
    return (
      <section className={cn('citizen-outcome', 'citizen-outcome--warning')} aria-live="polite">
        <span className="citizen__outcome-icon citizen__outcome-icon--warning" aria-hidden>
          <Icon name="camera" size={22} />
        </span>
        <div>
          <h1 className="citizen__outcome-title">Photo needs improvement</h1>
          <p>
            {scan.outcomeRationale ??
              'The text is too blurry to read reliably. Please retake the photo.'}
          </p>
          {scan.quality.grade && (
            <p className="cell-muted">Image quality: {scan.quality.grade.toLowerCase()}.</p>
          )}
        </div>
      </section>
    );
  }

  // REVIEW_REQUIRED + INSUFFICIENT_EVIDENCE
  return (
    <section className={cn('citizen-outcome', 'citizen-outcome--info')} aria-live="polite">
      <span className="citizen__outcome-icon citizen__outcome-icon--info" aria-hidden>
        <Icon name="eye" size={22} />
      </span>
      <div>
        <h1 className="citizen__outcome-title">
          {scan.outcome === 'REVIEW_REQUIRED' ? 'More verification needed' : 'Insufficient evidence'}
        </h1>
        <p>
          {scan.outcomeRationale ??
            "We couldn't establish the result reliably from the available information."}
        </p>
        <ul className="citizen-tips" style={{ marginTop: 'var(--space-3)' }}>
          <li><Icon name="alert" size={13} />The photo may be unclear</li>
          <li><Icon name="alert" size={13} />Some label information may be missing</li>
          <li><Icon name="alert" size={13} />A closer photo usually helps</li>
        </ul>
      </div>
    </section>
  );
}

function DetectedRow({ field }: { field: CitizenDetectedField }) {
  const value = field.normalizedValue ?? field.rawText;
  const lowConfidence = field.status === 'REVIEW_REQUIRED';
  return (
    <li className={cn('citizen-fields__row', lowConfidence && 'citizen-fields__row--low')}>
      <span className="citizen-fields__label">{field.label}</span>
      <span className="citizen-fields__value">
        {value}
        {lowConfidence && (
          <span className="citizen-fields__flag" title="The reading was not confident — verify on the package">
            unclear reading
          </span>
        )}
      </span>
    </li>
  );
}
