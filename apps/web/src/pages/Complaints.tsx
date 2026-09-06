import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';

import type { ComplaintStats, ComplaintSummary } from '@legalmet/types';

import { api } from '../api/client';
import { Badge } from '../components/Badge';
import { Card, CardBody } from '../components/Card';
import { Column, DataTable } from '../components/DataTable';
import { Icon } from '../components/Icon';
import { MetricCard } from '../components/MetricCard';
import { PageHeader } from '../components/PageHeader';
import { SearchBar, SelectField } from '../components/inputs';
import { AsyncView, EmptyState } from '../components/states';
import { useAsync } from '../data/useAsync';
import { formatDateTime } from '../lib/format';
import {
  COMPLAINT_RISK_META,
  COMPLAINT_STATUS_META,
} from '../lib/complaintStatus';
import type { CitizenReportStatus } from '@legalmet/types';

/**
 * COMPLAINT INTAKE (UI-03, extended UI-04) — the department queue, backed by
 * the REAL complaint API. Every number is a COUNT(*) from the database and
 * every filter (status / risk / assigned / inspection link / evidence band /
 * stale / location / search) is applied by the backend — this page never
 * filters or fabricates data client-side. If the database is empty it says so
 * honestly.
 *
 * UI-04: filters are mirrored in the URL (?status=…&risk=…), so dashboard
 * cards and "needs attention" items can deep-link straight into a filtered
 * queue.
 */

const STATUS_OPTIONS = (Object.keys(COMPLAINT_STATUS_META) as CitizenReportStatus[]).map(
  (s) => ({ value: s, label: COMPLAINT_STATUS_META[s].label }),
);

const RISK_OPTIONS = [
  { value: '', label: 'All risk levels' },
  { value: 'HIGH', label: 'High' },
  { value: 'MEDIUM', label: 'Medium' },
  { value: 'LOW', label: 'Low' },
];

const ASSIGNED_OPTIONS = [
  { value: '', label: 'Any assignment' },
  { value: 'UNASSIGNED', label: 'Unassigned' },
  { value: 'ASSIGNED', label: 'Assigned' },
];

const EVIDENCE_OPTIONS = [
  { value: '', label: 'Any evidence' },
  { value: 'COMPLETE', label: 'Complete (≥80)' },
  { value: 'PARTIAL', label: 'Partial (50–79)' },
  { value: 'MINIMAL', label: 'Minimal (<50)' },
];

const INSPECTION_OPTIONS = [
  { value: '', label: 'Any inspection link' },
  { value: 'LINKED', label: 'Converted to inspection' },
  { value: 'UNLINKED', label: 'Not converted' },
];

/** Debounce free-text filters so typing does not spam the API. */
function useDebounced<T>(value: T, ms = 350): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return debounced;
}

function StatusBadge({ status }: { status: CitizenReportStatus }) {
  const meta = COMPLAINT_STATUS_META[status];
  return (
    <Badge tone={meta.tone} dot title={meta.hint}>
      {meta.label}
    </Badge>
  );
}

/** SYSTEM screening vs OFFICIAL decision — deliberately two distinct badges. */
function RiskBadges({ complaint }: { complaint: ComplaintSummary }) {
  return (
    <span className="row" style={{ gap: 4, flexWrap: 'nowrap' }}>
      {complaint.screeningRisk && (
        <Badge
          tone={COMPLAINT_RISK_META[complaint.screeningRisk]?.tone}
          outline
          title="SYSTEM SCREENING — deterministic rule over the scan's detected declarations. Not an official decision."
        >
          {COMPLAINT_RISK_META[complaint.screeningRisk]?.label ?? complaint.screeningRisk}
        </Badge>
      )}
      {complaint.officialPriority && (
        <Badge
          tone={COMPLAINT_RISK_META[complaint.officialPriority]?.tone}
          dot
          title="OFFICIAL PRIORITY DECISION — set by the department."
        >
          {complaint.officialPriority}
        </Badge>
      )}
    </span>
  );
}

/** Evidence photo + the deterministic completeness score (evidence, not guilt). */
function EvidenceCell({ complaint }: { complaint: ComplaintSummary }) {  const score = complaint.evidenceCompleteness;
  return (
    <span className="row" style={{ gap: 6, flexWrap: 'nowrap' }} title="Evidence completeness — how complete the recorded evidence is (photo, OCR extraction, descriptions, follow-ups). Not a violation likelihood.">
      {complaint.hasImageEvidence ? (
        <Badge tone="positive" outline>
          <Icon name="image" size={11} /> Photo
        </Badge>
      ) : (
        <Badge tone="neutral" outline>
          <Icon name="info" size={11} /> No photo
        </Badge>
      )}
      {typeof score === 'number' && (
        <span className="cell-mono" style={{ fontSize: 'var(--fs-xs)' }}>
          {score}%
        </span>
      )}
    </span>
  );
}

/**
 * UI-05 — the REAL complaint → inspection relationship (never a client-side
 * guess): no link means "not converted"; a link shows the inspection's own
 * lifecycle, bucketed for the department view. "Assigned" reflects the
 * recorded inspector; "In progress" the analysis/review stages.
 */
function InspectionCell({ complaint }: { complaint: ComplaintSummary }) {
  if (!complaint.inspectionId || !complaint.inspectionReference) {
    return (
      <Badge tone="neutral" outline title="No inspection has been created from this complaint">
        Not converted
      </Badge>
    );
  }
  const s = complaint.inspectionStatus;
  let label = 'Inspection created';
  let tone: 'info' | 'warning' | 'positive' = 'info';
  if (s === 'COMPLETED' || s === 'ARCHIVED') {
    label = 'Completed';
    tone = 'positive';
  } else if (s === 'ANALYZING' || s === 'ANALYZED' || s === 'UNDER_REVIEW') {
    label = 'In progress';
    tone = 'warning';
  } else if (complaint.assignedInspectorName) {
    label = 'Assigned';
  }
  return (
    <span className="row" style={{ gap: 6, flexWrap: 'nowrap' }}>
      <span className="cell-mono" style={{ fontSize: 'var(--fs-xs)' }} title={complaint.inspectionReference}>
        {complaint.inspectionReference}
      </span>
      <Badge tone={tone} outline>{label}</Badge>
    </span>
  );
}

function kpis(stats: ComplaintStats) {
  return [
    { label: 'Total complaints', value: stats.total, icon: 'complaints' as const, foot: 'all statuses, real database count' },
    { label: 'New (submitted)', value: stats.submitted, icon: 'clock' as const, foot: 'awaiting first review' },
    { label: 'Needs review', value: stats.underReview + stats.requestInformation, icon: 'review' as const, foot: 'under review or awaiting citizen info' },
    { label: 'Unassigned open', value: stats.unassignedOpen, icon: 'alert' as const, foot: 'open complaints with no inspector' },
    { label: 'Inspection pending', value: stats.inspectionPending, icon: 'inspections' as const, foot: 'inspection created, not completed' },
  ];
}

export function ComplaintsPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  // UI-04: filters start from the URL (deep links from the command center).
  const [status, setStatus] = useState(searchParams.get('status') ?? '');
  const [risk, setRisk] = useState(searchParams.get('risk') ?? '');
  const [assigned, setAssigned] = useState(searchParams.get('assigned') ?? '');
  const [inspection, setInspection] = useState(searchParams.get('inspection') ?? '');
  const [evidence, setEvidence] = useState(searchParams.get('evidence') ?? '');
  const [stale, setStale] = useState(searchParams.get('stale') === 'true');
  const [search, setSearch] = useState(searchParams.get('search') ?? '');
  const [location, setLocation] = useState(searchParams.get('location') ?? '');
  const debouncedSearch = useDebounced(search);
  const debouncedLocation = useDebounced(location);

  const stats = useAsync(() => api.complaintStats(), []);

  // Keep the URL in sync (replace, not history spam) so filtered views are
  // shareable and the dashboard's deep links round-trip cleanly.
  useEffect(() => {
    const next: Record<string, string> = {};
    if (status) next.status = status;
    if (risk) next.risk = risk;
    if (assigned) next.assigned = assigned;
    if (inspection) next.inspection = inspection;
    if (evidence) next.evidence = evidence;
    if (stale) next.stale = 'true';
    if (debouncedSearch.trim()) next.search = debouncedSearch.trim();
    if (debouncedLocation.trim()) next.location = debouncedLocation.trim();
    setSearchParams(next, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status, risk, assigned, inspection, evidence, stale, debouncedSearch, debouncedLocation]);

  const params = useMemo(
    () => ({
      status: status || undefined,
      risk: risk || undefined,
      assigned: (assigned || undefined) as 'ASSIGNED' | 'UNASSIGNED' | undefined,
      inspection: (inspection || undefined) as 'LINKED' | 'UNLINKED' | undefined,
      evidence: (evidence || undefined) as 'COMPLETE' | 'PARTIAL' | 'MINIMAL' | undefined,
      stale: stale || undefined,
      search: debouncedSearch.trim() || undefined,
      location: debouncedLocation.trim() || undefined,
    }),
    [status, risk, assigned, inspection, evidence, stale, debouncedSearch, debouncedLocation],
  );
  const queue = useAsync(() => api.complaintList(params), [params]);

  const openDetail = (c: ComplaintSummary) => navigate(`/complaints/${c.id}`);

  const columns: Column<ComplaintSummary>[] = [
    {
      key: 'reference',
      header: 'Complaint ID',
      render: (c) => <span className="cell-mono">{c.reference}</span>,
    },
    { key: 'product', header: 'Product', render: (c) => <span className="cell-strong">{c.product}</span> },
    { key: 'location', header: 'Location', render: (c) => c.location ?? '—' },
    { key: 'issue', header: 'Issue', render: (c) => <span title={c.issue}>{c.issue}</span> },
    { key: 'evidence', header: 'Evidence', render: (c) => <EvidenceCell complaint={c} /> },
    { key: 'risk', header: 'Risk', render: (c) => <RiskBadges complaint={c} /> },
    { key: 'submitted', header: 'Submitted', render: (c) => formatDateTime(c.createdAt) },
    { key: 'status', header: 'Status', render: (c) => <StatusBadge status={c.status} /> },
    { key: 'inspection', header: 'Inspection', render: (c) => <InspectionCell complaint={c} /> },
    {
      key: 'action',
      header: 'Action',
      align: 'right',
      render: (c) => (
        <button
          type="button"
          className="btn btn--subtle btn--sm"
          onClick={(e) => {
            e.stopPropagation();
            openDetail(c);
          }}
        >
          Review
          <Icon name="arrowRight" size={13} />
        </button>
      ),
    },
  ];

  return (
    <div className="page">
      <PageHeader
        eyebrow="Department"
        title="Complaint Intake"
        lead="Citizen complaints on packaged commodities. Every count and filter below comes from the live database — screening risk is a deterministic system signal, never an official determination."
      />

      <AsyncView query={stats} loadingLabel="Loading complaint statistics…">
        {(data) => (
          <div className="grid grid--metrics">
            {kpis(data).map((k) => (
              <MetricCard key={k.label} label={k.label} value={k.value} icon={k.icon} hint={k.foot} />
            ))}
          </div>
        )}
      </AsyncView>

      <Card>
        <div className="filter-bar">
          <div style={{ width: 190 }}>
            <SelectField
              label="Status"
              value={status}
              onChange={setStatus}
              aria-label="Filter by status"
              options={[{ value: '', label: 'All statuses' }, ...STATUS_OPTIONS]}
            />
          </div>
          <div style={{ width: 150 }}>
            <SelectField
              label="Risk"
              value={risk}
              onChange={setRisk}
              aria-label="Filter by risk"
              options={RISK_OPTIONS}
            />
          </div>
          <div style={{ width: 160 }}>
            <SelectField
              label="Assignment"
              value={assigned}
              onChange={setAssigned}
              aria-label="Filter by assignment"
              options={ASSIGNED_OPTIONS}
            />
          </div>
          <div style={{ width: 190 }}>
            <SelectField
              label="Inspection"
              value={inspection}
              onChange={setInspection}
              aria-label="Filter by inspection link"
              options={INSPECTION_OPTIONS}
            />
          </div>
          <div style={{ width: 180 }}>
            <SelectField
              label="Evidence"
              value={evidence}
              onChange={setEvidence}
              aria-label="Filter by evidence completeness band"
              options={EVIDENCE_OPTIONS}
            />
          </div>
          <div style={{ width: 180 }}>
            <div className="field">
              <label className="field__label" htmlFor="complaint-location-filter">Location</label>
              <input
                id="complaint-location-filter"
                className="input"
                value={location}
                onChange={(e) => setLocation(e.target.value)}
                placeholder="e.g. Pune"
                maxLength={255}
              />
            </div>
          </div>
          <div className="filter-bar__search">
            <SearchBar
              value={search}
              onChange={setSearch}
              placeholder="Search ID, product, issue…"
              ariaLabel="Search complaints"
            />
          </div>
          <label
            className="row"
            style={{ gap: 6, fontSize: 'var(--fs-sm)', whiteSpace: 'nowrap', cursor: 'pointer' }}
            title="Only open complaints submitted more than 14 days ago"
          >
            <input
              type="checkbox"
              checked={stale}
              onChange={(e) => setStale(e.target.checked)}
            />
            Stale only
          </label>
        </div>

        <CardBody flush>
          <AsyncView query={queue} loadingLabel="Loading complaint queue…">
            {(items) =>
              items.length === 0 ? (
                <div style={{ padding: 'var(--space-6)' }}>
                  <EmptyState
                    icon="complaints"
                    title="No complaints match"
                    message={
                      status || risk || assigned || inspection || evidence || stale || search || location
                        ? 'No complaints match the current filters. Clear them to see the full queue.'
                        : 'No citizen complaints have been submitted yet. The queue will fill as citizens scan and report suspected issues.'
                    }
                  />
                </div>
              ) : (
                <>
                  {/* Desktop: table. Mobile (<860px): cards — same real data. */}
                  <div className="hide-sm">
                    <DataTable
                      columns={columns}
                      rows={items}
                      getRowId={(c) => c.id}
                      onRowClick={openDetail}
                      ariaLabel="Complaint intake queue"
                    />
                  </div>
                  <ul className="complaint-cards show-sm">
                    {items.map((c) => (
                      <li key={c.id} className="complaint-cards__item" onClick={() => openDetail(c)}>
                        <div className="row row--between row--wrap" style={{ gap: 6 }}>
                          <span className="cell-mono">{c.reference}</span>
                          <StatusBadge status={c.status} />
                        </div>
                        <div className="cell-strong">{c.product}</div>
                        <div className="cell-muted" style={{ fontSize: 'var(--fs-sm)' }}>
                          {c.issue}
                        </div>
                        <div className="cell-muted" style={{ fontSize: 'var(--fs-xs)' }}>
                          {c.location ?? 'No location'} · {formatDateTime(c.createdAt)}
                        </div>
                        <div className="row" style={{ gap: 6, marginTop: 6, flexWrap: 'wrap' }}>
                          <EvidenceCell complaint={c} />
                          <RiskBadges complaint={c} />
                          <InspectionCell complaint={c} />
                        </div>
                      </li>
                    ))}
                  </ul>
                </>
              )
            }
          </AsyncView>
        </CardBody>
      </Card>
    </div>
  );
}
