import { useState } from 'react';
import { Link } from 'react-router-dom';

import { Icon } from '../components/Icon';
import { Field } from '../components/inputs';
import { ApiClientError } from '../api/client';
import { useCitizenSession } from './session';
import type { CitizenReportResult } from '@legalmet/types';

/**
 * REPORT A SUSPECTED ISSUE (Checkpoints 7–9).
 *
 * Steps: form → review → submitted. The scan's evidence (scan ID, detected
 * declarations, image, timestamp) is attached automatically — the citizen
 * never re-enters extracted information. Submission is a REAL API call; on
 * failure the page says so and offers retry. It never pretends to succeed.
 */
type Step = 'form' | 'review' | 'submitting' | 'done' | 'error';

const ISSUE_OPTIONS = [
  'MRP missing or unclear',
  'Net quantity / weight issue',
  'Missing expiry or manufacture date',
  'Missing manufacturer details',
  'Missing country of origin',
  'Other suspected issue',
];

export function CitizenReportPage() {
  const { scan, submitReport } = useCitizenSession();
  const [step, setStep] = useState<Step>('form');
  const [error, setError] = useState<string | null>(null);
  const [submitted, setSubmitted] = useState<CitizenReportResult | null>(null);

  const [product, setProduct] = useState('');
  const [shop, setShop] = useState('');
  const [location, setLocation] = useState('');
  const [issue, setIssue] = useState('');
  const [description, setDescription] = useState('');
  const [reporterName, setReporterName] = useState('');
  const [reporterContact, setReporterContact] = useState('');

  if (!scan) {
    return (
      <div className="citizen-page">
        <div className="citizen-page__topbar">
          <Link to="/citizen/scan" className="btn btn--ghost btn--sm">
            <Icon name="chevronLeft" size={15} />
            Back
          </Link>
          <span className="citizen-step__label">Report</span>
        </div>
        <div className="citizen-empty">
          <span className="citizen__scan-icon" aria-hidden>
            <Icon name="complaints" size={24} />
          </span>
          <h1>No scan to report</h1>
          <p className="cell-muted">
            Scan a package first — its photo and readings are attached to your report.
          </p>
          <Link to="/citizen/scan" className="btn btn--primary">
            <Icon name="camera" size={16} />
            Scan product
          </Link>
        </div>
      </div>
    );
  }

  // Prefill the product from the scan the moment the form first appears.
  const detectedName = scan.detectedFields.find(
    (f) => f.fieldType === 'PRODUCT_NAME' || f.fieldType === 'BRAND_NAME',
  );
  const suggestedProduct = detectedName?.normalizedValue ?? detectedName?.rawText ?? '';
  const effectiveProduct = product || suggestedProduct;

  function goToReview() {
    setError(null);
    setStep('review');
  }

  async function onSubmit() {
    setStep('submitting');
    setError(null);
    try {
      const result = await submitReport({
        product: effectiveProduct,
        shop: shop || undefined,
        location: location || undefined,
        issue,
        description: description || undefined,
        reporterName: reporterName || undefined,
        reporterContact: reporterContact || undefined,
      });
      setSubmitted(result);
      setStep('done');
    } catch (err) {
      setError(
        err instanceof ApiClientError
          ? err.message
          : 'We could not reach the reporting service. Check your connection and try again.',
      );
      setStep('error');
    }
  }

  if (step === 'done' && submitted) {
    return (
      <div className="citizen-page">
        <section className="citizen-outcome citizen-outcome--positive" aria-live="polite">
          <span className="citizen__outcome-icon citizen__outcome-icon--positive" aria-hidden>
            <Icon name="check" size={22} />
          </span>
          <div className="stack stack--sm">
            <h1 className="citizen__outcome-title">Complaint submitted</h1>
            <p>Your suspected issue has been submitted for official review.</p>
            <div className="citizen-ref">
              <span className="citizen-ref__label">Complaint ID</span>
              <span className="citizen-ref__value">{submitted.reference}</span>
              <span className="citizen-ref__status">Status: SUBMITTED</span>
            </div>
          </div>
        </section>
        <div className="citizen-actions">
          <Link to={`/citizen/reports/${submitted.id}`} className="btn btn--primary">
            <Icon name="inspections" size={16} />
            View complaint
          </Link>
          <Link to="/citizen" className="btn btn--ghost">
            Back to home
          </Link>
        </div>
        <p className="citizen-footnote">
          Keep the package and your purchase bill if possible — they help the
          inspector verify the issue.
        </p>
      </div>
    );
  }

  return (
    <div className="citizen-page">
      <div className="citizen-page__topbar">
        <Link
          to={step === 'form' ? '/citizen/result' : '/citizen/report'}
          className="btn btn--ghost btn--sm"
          onClick={step === 'review' ? () => setStep('form') : undefined}
        >
          <Icon name="chevronLeft" size={15} />
          {step === 'review' ? 'Edit' : 'Back'}
        </Link>
        <span className="citizen-step__label">Report a suspected issue</span>
      </div>

      {step === 'form' && (
        <form
          className="stack"
          onSubmit={(e) => {
            e.preventDefault();
            goToReview();
          }}
        >
          <p className="citizen-page__lead">
            Your scan indicates a possible issue. You can submit this information to
            Legal Metrology for official review.
          </p>

          <Field label="Product">
            {suggestedProduct && (
              <span className="citizen-field-hint">From your scan: {suggestedProduct}</span>
            )}
            <input
              className="input"
              value={effectiveProduct}
              onChange={(e) => setProduct(e.target.value)}
              required
              maxLength={255}
              placeholder={suggestedProduct || 'e.g. DEMO Wholesome Product'}
            />
          </Field>

          <Field label="Shop / establishment">
            <input
              className="input"
              value={shop}
              onChange={(e) => setShop(e.target.value)}
              maxLength={255}
              placeholder="Where you bought it (optional)"
            />
          </Field>

          <Field label="Location">
            <span className="citizen-field-hint">Area / city — helps route your report</span>
            <input
              className="input"
              value={location}
              onChange={(e) => setLocation(e.target.value)}
              maxLength={255}
              placeholder="e.g. Kothrud, Pune"
            />
          </Field>

          <Field label="Suspected issue">
            <select
              className="input"
              value={issue}
              onChange={(e) => setIssue(e.target.value)}
              required
            >
              <option value="">Choose the issue you noticed…</option>
              {ISSUE_OPTIONS.map((opt) => (
                <option key={opt} value={opt}>
                  {opt}
                </option>
              ))}
            </select>
          </Field>

          <Field label="Additional description">
            <span className="citizen-field-hint">Anything else the inspector should know</span>
            <textarea
              className="input"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              maxLength={4000}
              placeholder="Optional"
            />
          </Field>

          <details className="citizen-why">
            <summary>Your details (optional)</summary>
            <Field label="Name">
              <input
                className="input"
                value={reporterName}
                onChange={(e) => setReporterName(e.target.value)}
                maxLength={128}
              />
            </Field>
            <Field label="Contact (phone or email)">
              <input
                className="input"
                value={reporterContact}
                onChange={(e) => setReporterContact(e.target.value)}
                maxLength={128}
              />
            </Field>
          </details>

          <div className="citizen-attached" role="note">
            <Icon name="shield" size={15} />
            <span>
              Attached automatically from your scan: photo, detected declarations
              ({scan.detectedFields.filter((f) => f.status !== 'NOT_EXTRACTED').length}),
              scan reference {scan.reference} and timestamp.
            </span>
          </div>

          <button type="submit" className="btn btn--primary btn--lg">
            Review report
            <Icon name="arrowRight" size={16} />
          </button>
        </form>
      )}

      {(step === 'review' || step === 'submitting' || step === 'error') && (
        <section className="stack" aria-label="Review your report">
          <h1 className="citizen-page__title">Review your report</h1>

          {step === 'error' && error && (
            <div className="citizen-error" role="alert">
              <Icon name="alert" size={16} />
              <div>
                <strong>Report could not be submitted.</strong>
                <p>{error}</p>
              </div>
            </div>
          )}

          <dl className="citizen-review">
            <div><dt>Product</dt><dd>{effectiveProduct}</dd></div>
            {shop && <div><dt>Shop</dt><dd>{shop}</dd></div>}
            {location && <div><dt>Location</dt><dd>{location}</dd></div>}
            <div><dt>Possible issue</dt><dd>{issue}</dd></div>
            {description && <div><dt>Description</dt><dd>{description}</dd></div>}
            <div>
              <dt>Evidence</dt>
              <dd>
                Photo + {scan.detectedFields.filter((f) => f.status !== 'NOT_EXTRACTED').length}{' '}
                detected declarations · scan {scan.reference}
              </dd>
            </div>
            <div>
              <dt>Detected information</dt>
              <dd>
                {scan.detectedFields
                  .filter((f) => f.status !== 'NOT_EXTRACTED')
                  .slice(0, 6)
                  .map((f) => `${f.label}: ${f.normalizedValue ?? f.rawText}`)
                  .join(' · ') || 'No declarations read'}
              </dd>
            </div>
          </dl>

          <div className="citizen-actions">
            <button
              type="button"
              className="btn btn--primary btn--lg"
              disabled={step === 'submitting'}
              onClick={() => void onSubmit()}
            >
              {step === 'submitting' ? (
                <>
                  <span className="spinner" aria-hidden />
                  Submitting…
                </>
              ) : (
                <>
                  <Icon name="check" size={16} />
                  Submit report
                </>
              )}
            </button>
            <button
              type="button"
              className="btn btn--ghost"
              disabled={step === 'submitting'}
              onClick={() => setStep('form')}
            >
              Edit
            </button>
          </div>
        </section>
      )}
    </div>
  );
}
