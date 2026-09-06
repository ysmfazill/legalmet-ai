import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';

import type { CitizenReportDetail } from '@legalmet/types';

import { api, ApiClientError } from '../api/client';
import { Icon } from '../components/Icon';
import { Field } from '../components/inputs';
import { AsyncView, ErrorState } from '../components/states';
import { useAsync } from '../data/useAsync';
import { formatDateTime } from '../lib/format';
import {
  COMPLAINT_STATUS_META,
  complaintEventLabel,
} from '../lib/complaintStatus';
import { useCitizenSession } from './session';

/**
 * COMPLAINT DETAIL (citizen view) — /citizen/reports/:id.
 *
 * Shows the real recorded status, the REAL event timeline (only events the
 * backend actually recorded — never fabricated steps), the pending information
 * request with the respond form, and the linked inspection summary. Legal
 * language contract: "suspected issue" / "requires official verification" —
 * never a violation claim.
 */
export function CitizenReportDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { refreshReport } = useCitizenSession();
  const query = useAsync(() => api.citizenGetReport(id ?? ''), [id]);

  if (!id) return <ErrorState title="No complaint selected" />;

  return (
    <div className="citizen-page">
      <div className="citizen-page__topbar">
        <Link to="/citizen/reports" className="btn btn--ghost btn--sm">
          <Icon name="chevronLeft" size={15} />
          My complaints
        </Link>
        <span className="citizen-step__label">Complaint</span>
      </div>

      <AsyncView query={query} loadingLabel="Loading complaint…">
        {(detail) => (
          <CitizenComplaintView
            key={detail.id}
            detail={detail}
            onUpdated={(updated) => {
              // Keep this-device list in sync after a citizen response.
              refreshReport(detail.id).catch(() => undefined);
              return updated;
            }}
          />
        )}
      </AsyncView>
    </div>
  );
}

function CitizenComplaintView({
  detail,
  onUpdated,
}: {
  detail: CitizenReportDetail;
  onUpdated: (updated: CitizenReportDetail) => CitizenReportDetail;
}) {
  const [current, setCurrent] = useState<CitizenReportDetail>(detail);
  const meta = COMPLAINT_STATUS_META[current.status] ?? COMPLAINT_STATUS_META.SUBMITTED;
  const awaitingReview = current.events.every((e) => e.event === 'SUBMITTED');

  return (
    <>
      <h1 className="citizen-page__title">Complaint {current.reference}</h1>
      <p className="citizen-page__lead">
        Submitted {formatDateTime(current.createdAt)} · Suspected issue: {current.issue}
      </p>

      <div className="citizen-ref" style={{ marginBottom: 'var(--space-4)' }}>
        <span className="citizen-ref__label">Complaint ID</span>
        <span className="citizen-ref__value">{current.reference}</span>
        <span className={`citizen-ref__status citizen-status citizen-status--${meta.tone}`}>
          {meta.label}
        </span>
      </div>

      <p className="citizen-statusnote">
        {awaitingReview
          ? 'Waiting for official review. The department has received your complaint.'
          : meta.hint}
        {current.inspection && (
          <>
            {' '}
            Linked inspection <strong>{current.inspection.referenceNo}</strong> —{' '}
            {current.inspection.status.replace(/_/g, ' ').toLowerCase()}.
          </>
        )}
      </p>

      {current.status === 'REQUEST_INFORMATION' && current.pendingInfoRequest && (
        <RespondPanel
          detail={current}
          onResponded={(updated) => {
            const next = onUpdated(updated);
            setCurrent(next);
          }}
        />
      )}

      <section className="citizen-section" aria-label="Complaint timeline">
        <h2 className="citizen-section__title">What has happened</h2>
        <p className="citizen-footnote">
          Every entry below is a real recorded event. If the department has not
          acted yet, only your submission appears.
        </p>
        <ol className="citizen-timeline">
          {current.events.map((event) => (
            <li key={event.id} className="citizen-timeline__item">
              <span
                className={`citizen-timeline__dot citizen-timeline__dot--${
                  event.actorType === 'CITIZEN' ? 'citizen' : 'department'
                }`}
                aria-hidden
              />
              <div className="citizen-timeline__body">
                <span className="citizen-timeline__label">{complaintEventLabel(event.event)}</span>
                <span className="citizen-timeline__meta">
                  {event.actorType === 'CITIZEN' ? 'You' : (event.actorName ?? 'Department')} ·{' '}
                  {formatDateTime(event.createdAt)}
                </span>
                {event.note && <p className="citizen-timeline__note">{event.note}</p>}
              </div>
            </li>
          ))}
        </ol>
      </section>
    </>
  );
}

const INFO_PRESETS = [
  'Photo of the full back label',
  'Photo of the price/MRP sticker',
  'Batch number and expiry date',
  'Shop name and address',
];

function RespondPanel({
  detail,
  onResponded,
}: {
  detail: CitizenReportDetail;
  onResponded: (updated: CitizenReportDetail) => void;
}) {
  const [message, setMessage] = useState('');
  const [location, setLocation] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const updated = await api.citizenRespond(detail.id, {
        message,
        location: location || undefined,
        file: file ?? undefined,
      });
      onResponded(updated);
    } catch (err) {
      setError(
        err instanceof ApiClientError
          ? err.message
          : 'We could not send your response. Check your connection and try again.',
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="citizen-inforeq" aria-label="Information requested">
      <div className="citizen-inforeq__head">
        <Icon name="info" size={18} />
        <h2>The department needs more information</h2>
      </div>
      <p className="citizen-inforeq__request">{detail.pendingInfoRequest}</p>

      <form className="stack" onSubmit={submit}>
        <Field label="Your response">
          <span className="citizen-field-hint">
            This is added to your complaint — your original report stays unchanged.
          </span>
          <textarea
            className="input"
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            rows={4}
            maxLength={4000}
            required
            placeholder="Describe or provide what was asked for…"
          />
        </Field>

        <div className="stack stack--sm">
          <span className="citizen-field-hint">Quick additions:</span>
          <div className="citizen-chiprow">
            {INFO_PRESETS.map((preset) => (
              <button
                key={preset}
                type="button"
                className="btn btn--ghost btn--sm"
                onClick={() =>
                  setMessage((m) => (m ? `${m}\n${preset}` : `Attaching: ${preset}`))
                }
              >
                {preset}
              </button>
            ))}
          </div>
        </div>

        <Field label="Location (if asked)">
          <input
            className="input"
            value={location}
            onChange={(e) => setLocation(e.target.value)}
            maxLength={255}
            placeholder="e.g. Kothrud, Pune"
          />
        </Field>

        <Field label="Attach a photo (optional)">
          <input
            className="input"
            type="file"
            accept="image/*"
            capture="environment"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
        </Field>

        {error && (
          <div className="citizen-error" role="alert">
            <Icon name="alert" size={16} />
            <div>
              <strong>Response could not be sent.</strong>
              <p>{error}</p>
            </div>
          </div>
        )}

        <button type="submit" className="btn btn--primary btn--lg" disabled={submitting}>
          {submitting ? (
            <>
              <span className="spinner" aria-hidden />
              Sending…
            </>
          ) : (
            <>
              <Icon name="check" size={16} />
              Send response
            </>
          )}
        </button>
      </form>
    </section>
  );
}
