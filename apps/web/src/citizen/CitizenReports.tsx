import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';

import { Icon } from '../components/Icon';
import { useCitizenSession } from './session';
import { formatDateTime } from '../lib/format';
import {
  COMPLAINT_STATUS_META,
  matchesCitizenFilter,
  type CitizenFilterId,
} from '../lib/complaintStatus';

/**
 * MY REPORTS — complaints submitted from THIS device.
 *
 * Honesty contract: the backend deliberately offers no anonymous listing
 * (complaints are reachable only by their unguessable UUID — no enumeration by
 * strangers). So this list is the record of submissions made from this
 * browser, kept in local storage, and labelled exactly that way. Each entry's
 * status is re-read from the real backend on every visit (live refresh);
 * until the department acts, the honest state is "Waiting for official review".
 */
const FILTER_TABS: { id: CitizenFilterId; label: string }[] = [
  { id: 'ALL', label: 'All' },
  { id: 'SUBMITTED', label: 'Submitted' },
  { id: 'UNDER_REVIEW', label: 'Under Review' },
  { id: 'ACCEPTED', label: 'Accepted' },
  { id: 'COMPLETED', label: 'Completed' },
  { id: 'CLOSED', label: 'Closed' },
];

export function CitizenReportsPage() {
  const { myReports, refreshReport } = useCitizenSession();
  const [filter, setFilter] = useState<CitizenFilterId>('ALL');

  // Live refresh: re-read every stored complaint from the backend so the
  // status shown is the department's actual latest state.
  useEffect(() => {
    for (const r of myReports) {
      refreshReport(r.id).catch(() => {
        // Backend unreachable — the stored snapshot stays, clearly a snapshot.
      });
    }
    // myReports identity changes as refreshes land; refresh once per visit.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const visible = useMemo(
    () => myReports.filter((r) => matchesCitizenFilter(r.status, filter)),
    [myReports, filter],
  );

  return (
    <div className="citizen-page">
      <div className="citizen-page__topbar">
        <Link to="/citizen" className="btn btn--ghost btn--sm">
          <Icon name="chevronLeft" size={15} />
          Home
        </Link>
        <span className="citizen-step__label">My complaints</span>
      </div>

      <h1 className="citizen-page__title">My complaints</h1>
      <p className="citizen-page__lead">
        Complaints you submitted from this device. Your complaint ID lets the
        department find your case — keep it.
      </p>

      {myReports.length === 0 ? (
        <div className="citizen-empty">
          <span className="citizen__scan-icon" aria-hidden>
            <Icon name="inspections" size={24} />
          </span>
          <h2>No complaints yet</h2>
          <p className="cell-muted">
            When you submit a suspected issue, its complaint ID appears here.
          </p>
          <Link to="/citizen/scan" className="btn btn--primary">
            <Icon name="camera" size={16} />
            Scan a product
          </Link>
        </div>
      ) : (
        <>
          <p className="citizen-footnote" style={{ marginBottom: 'var(--space-4)' }}>
            <Icon name="info" size={13} /> Kept on this device only — clearing browser
            data removes the list (the department keeps its own records). Statuses
            refresh from the department each visit.
          </p>

          <div className="citizen-filters" role="tablist" aria-label="Filter complaints by status">
            {FILTER_TABS.map((tab) => {
              const active = filter === tab.id;
              return (
                <button
                  key={tab.id}
                  type="button"
                  role="tab"
                  aria-selected={active}
                  className={`btn btn--sm ${active ? 'btn--primary' : 'btn--ghost'}`}
                  onClick={() => setFilter(tab.id)}
                >
                  {tab.label}
                </button>
              );
            })}
          </div>

          {visible.length === 0 ? (
            <p className="citizen-footnote" style={{ marginTop: 'var(--space-4)' }}>
              No complaints in this state.
            </p>
          ) : (
            <ul className="citizen-reports">
              {visible.map((r) => {
                const meta = COMPLAINT_STATUS_META[r.status] ?? COMPLAINT_STATUS_META.SUBMITTED;
                return (
                  <li key={r.id} className="citizen-reports__row">
                    <div className="citizen-reports__main">
                      <span className="citizen-reports__ref">{r.reference}</span>
                      <span className="citizen-reports__product">{r.product}</span>
                      <span className="citizen-reports__date">{formatDateTime(r.createdAt)}</span>
                    </div>
                    <div className="citizen-reports__status">
                      <span className={`citizen-status citizen-status--${meta.tone}`}>
                        {meta.label}
                      </span>
                      <span className="citizen-reports__hint">{meta.hint}</span>
                      <Link
                        to={`/citizen/reports/${r.id}`}
                        className="btn btn--ghost btn--sm citizen-reports__open"
                      >
                        View complaint
                        <Icon name="arrowRight" size={13} />
                      </Link>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </>
      )}
    </div>
  );
}
