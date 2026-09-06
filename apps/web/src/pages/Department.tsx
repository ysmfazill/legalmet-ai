import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

import type {
  CitizenReportStatus,
  ComplaintTrendPoint,
  DepartmentActivity,
  DepartmentDashboard,
  PriorityComplaint,
} from '@legalmet/types';

import { DistributionBar } from '../components/charts';
import { Badge } from '../components/Badge';
import { SectionCard } from '../components/Card';
import { Icon } from '../components/Icon';
import { PageHeader } from '../components/PageHeader';
import { Segmented } from '../components/Tabs';
import { EmptyState, ErrorState, LoadingState } from '../components/states';
import { useApp } from '../app/AppContext';
import { api } from '../api/client';
import { useAsync } from '../data/useAsync';
import { formatDateTime } from '../lib/format';
import {
  COMPLAINT_RISK_META,
  COMPLAINT_STATUS_META,
} from '../lib/complaintStatus';

/**
 * DEPARTMENT COMMAND CENTER (UI-04) — /department.
 *
 * The supervisory view over the whole METRASIGHT principle:
 *   CITIZEN → REPORT → DEPARTMENT REVIEW → PRIORITIZE → TARGETED INSPECTION
 *   → INSPECTOR VERIFY → DECIDE.
 *
 * Every figure on this page comes from ONE aggregated backend call
 * (GET /department/dashboard) whose numbers are real database COUNT/GROUP BY
 * results — nothing is computed client-side from raw rows and nothing is
 * fabricated. Loading / empty / error states are explicit; the refresh
 * timestamp is the real moment the latest fetch completed.
 *
 * Language contract: priorities here are PRIORITIZATION signals (official
 * decision when set, else deterministic system screening) and evidence
 * completeness measures evidence — neither is ever a legal determination.
 */

const WINDOW_TABS = [
  { id: '7' as const, label: '7 Days' },
  { id: '30' as const, label: '30 Days' },
  { id: '90' as const, label: '90 Days' },
];

/** Audit event → plain-language activity label. */
const ACTIVITY_LABELS: Record<string, string> = {
  COMPLAINT_REVIEW_STARTED: 'Review started',
  COMPLAINT_ACCEPTED: 'Complaint accepted',
  COMPLAINT_REJECTED: 'Complaint rejected',
  COMPLAINT_INFO_REQUESTED: 'Information requested',
  COMPLAINT_ASSIGNED: 'Inspector assigned',
  COMPLAINT_INSPECTION_CREATED: 'Inspection created from complaint',
  COMPLAINT_INSPECTION_COMPLETED: 'Inspection completed',
  COMPLAINT_ACTION_TAKEN: 'Action recorded',
  COMPLAINT_CLOSED: 'Complaint closed',
};

const WRITE_ROLES = ['INSPECTOR', 'SUPERVISOR', 'ADMIN'];

/** KPI card → the filtered queue it opens (same enum, backend filtering). */
function kpiCards(d: DepartmentDashboard) {
  return [
    {
      label: 'Total complaints',
      value: d.kpis.totalComplaints,
      icon: 'complaints' as const,
      hint: 'every citizen report, all statuses',
      to: '/complaints',
    },
    {
      label: 'Pending review',
      value: d.kpis.pendingReview,
      icon: 'clock' as const,
      hint: 'submitted, under review or awaiting citizen info',
      to: '/complaints?status=SUBMITTED,UNDER_REVIEW,REQUEST_INFORMATION',
    },
    {
      label: 'High priority',
      value: d.kpis.highPriority,
      icon: 'alert' as const,
      hint: 'open with effective priority HIGH',
      to: '/complaints?risk=HIGH',
    },
    {
      label: 'Converted to inspection',
      value: d.kpis.convertedToInspection,
      icon: 'inspections' as const,
      hint: 'department decision created a real inspection',
      to: '/complaints?inspection=LINKED',
    },
    {
      label: 'Under investigation',
      value: d.kpis.underInvestigation,
      icon: 'shield' as const,
      hint: 'inspection created, not yet completed',
      to: '/complaints?status=INSPECTION_SCHEDULED',
    },
    {
      label: 'Resolved',
      value: d.kpis.resolved,
      icon: 'check' as const,
      hint: 'action taken or closed',
      to: '/complaints?status=ACTION_TAKEN,CLOSED',
    },
    {
      label: 'Rejected',
      value: d.kpis.rejected,
      icon: 'close' as const,
      hint: 'terminal — with recorded reason',
      to: '/complaints?status=REJECTED',
    },
    {
      label: 'Unassigned open',
      value: d.kpis.unassignedOpen,
      icon: 'user' as const,
      hint: 'open complaints with no inspector yet',
      to: '/complaints?assigned=UNASSIGNED',
    },
  ];
}

export function DepartmentPage() {
  const { user } = useApp();
  const [windowDays, setWindowDays] = useState<'7' | '30' | '90'>('30');
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const days = Number(windowDays) as 7 | 30 | 90;
  const query = useAsync(() => api.departmentDashboard(days), [days]);

  // The refresh timestamp is REAL: the moment the latest fetch completed.
  useEffect(() => {
    if (query.status === 'success') setLastUpdated(new Date());
  }, [query.status, query.data]);

  const canAct = WRITE_ROLES.includes(user.role);

  return (
    <div className="page">
      <PageHeader
        eyebrow="Department"
        title="Department Command Center"
        lead="Legal Metrology Operations — citizen reports, department review, prioritized inspections and decisions. Every figure is a live database count; nothing on this page is simulated."
        actions={
          <>
            <Segmented
              options={WINDOW_TABS}
              active={windowDays}
              onChange={setWindowDays}
              ariaLabel="Complaint trend window"
            />
            <button
              type="button"
              className="btn btn--subtle"
              onClick={() => query.reload()}
              disabled={query.status === 'loading'}
              title="Reload all dashboard data from the live database"
            >
              <Icon name="reset" size={15} />
              Refresh
            </button>
          </>
        }
      />

      {/* Real dates only: today, when the server generated this payload, and
          when this browser last completed a refresh. */}
      <div className="dept-meta" role="status" aria-live="polite">
        <span>
          <Icon name="clock" size={13} />
          {new Date().toLocaleDateString(undefined, {
            weekday: 'long',
            day: 'numeric',
            month: 'long',
            year: 'numeric',
          })}
        </span>
        {query.status === 'success' && (
          <>
            <span title="When the backend generated this payload">
              Server data: {formatDateTime(query.data.generatedAt)}
            </span>
            <span title="When this browser last completed a refresh">
              Last updated: {lastUpdated ? lastUpdated.toLocaleTimeString() : '—'}
            </span>
          </>
        )}
      </div>

      {query.status === 'loading' && <LoadingState label="Loading complaints…" />}

      {query.status === 'error' && (
        <ErrorState
          title="Unable to load dashboard"
          error={query.error}
          onRetry={query.reload}
        />
      )}

      {query.status === 'success' && query.data.kpis.totalComplaints === 0 && (
        <>
          <div className="demo-note demo-note--block">
            <Icon name="info" size={15} />
            <span>
              No complaints yet — the department database is empty. Every figure below
              is a real count of zero; nothing is simulated. Complaints will appear
              here as citizens scan packages and report suspected issues.
            </span>
          </div>
          <EmptyState
            icon="complaints"
            title="No complaints yet"
            message="Citizen complaint analytics appear once the first complaint is submitted."
          />
          <QuickActions />
        </>
      )}

      {query.status === 'success' && query.data.kpis.totalComplaints > 0 && (
        <CommandCenter dashboard={query.data} canAct={canAct} />
      )}
    </div>
  );
}

function CommandCenter({ dashboard: d, canAct }: { dashboard: DepartmentDashboard; canAct: boolean }) {
  return (
    <>
      {/* --- KPI cards (all real counts, all clickable into filtered queues) --- */}
      <div className="grid grid--metrics">
        {kpiCards(d).map((k) => (
          <Link key={k.label} to={k.to} className="metric metric--link" title={`Open the queue: ${k.hint}`}>
            <div className="metric__top">
              <span className="metric__label">{k.label}</span>
              <span className="metric__icon" aria-hidden>
                <Icon name={k.icon} size={17} />
              </span>
            </div>
            <div className="metric__value">{k.value}</div>
            <div className="metric__foot">
              <span>{k.hint}</span>
            </div>
          </Link>
        ))}
      </div>

      <div className="grid grid--2">
        {/* --- Complaint trend (real created_at grouping) ------------------- */}
        <SectionCard
          eyebrow="Complaint trend"
          title="Complaints over time"
          subtitle={`${d.windowComplaints} complaint${d.windowComplaints === 1 ? '' : 's'} created in the last ${d.windowDays} days (grouped by submission date)`}
        >
          {d.windowComplaints === 0 ? (
            <div style={{ padding: 'var(--space-4)' }}>
              <EmptyState
                icon="clock"
                title="No historical complaint data available"
                message={`No complaints were submitted in the last ${d.windowDays} days.`}
              />
            </div>
          ) : (
            <TrendChart points={d.trend} />
          )}
        </SectionCard>

        {/* --- Status distribution (UI-03 status model, clickable) ---------- */}
        <SectionCard
          eyebrow="Complaint lifecycle"
          title="Status distribution"
          subtitle="The UI-03 complaint statuses — click one to open the queue filtered by it"
        >
          <ul className="dept-rollup">
            {(Object.keys(COMPLAINT_STATUS_META) as CitizenReportStatus[])
              .filter((s) => (d.statusDistribution[s] ?? 0) > 0)
              .map((s) => (
                <li key={s}>
                  <RollupRow
                    to={`/complaints?status=${s}`}
                    label={COMPLAINT_STATUS_META[s].label}
                    value={d.statusDistribution[s] ?? 0}
                    max={Math.max(...Object.values(d.statusDistribution), 1)}
                    tone={COMPLAINT_STATUS_META[s].tone}
                  />
                </li>
              ))}
          </ul>
        </SectionCard>
      </div>

      <div className="grid grid--2">
        {/* --- Risk radar (triage signals, not legal grading) --------------- */}
        <SectionCard
          eyebrow="Risk indicators"
          title="Risk radar"
          subtitle="Effective priority of OPEN complaints — the official decision when set, otherwise the deterministic system screening. A prioritization signal, never a legal determination."
        >
          <DistributionBar
            segments={[
              { label: 'High priority', value: d.riskDistribution.HIGH ?? 0, tone: 'critical' as const },
              { label: 'Medium priority', value: d.riskDistribution.MEDIUM ?? 0, tone: 'warning' as const },
              { label: 'Low priority', value: d.riskDistribution.LOW ?? 0, tone: 'neutral' as const },
              { label: 'Not yet assessed', value: d.riskDistribution.UNSET ?? 0, tone: 'info' as const },
            ].filter((s) => s.value > 0)}
          />
          <div className="row row--wrap" style={{ gap: 'var(--space-2)', marginTop: 'var(--space-3)' }}>
            <Link to="/complaints?risk=HIGH" className="btn btn--subtle btn--sm">
              View high-priority cases
              <Icon name="arrowRight" size={13} />
            </Link>
          </div>
        </SectionCard>

        {/* --- Evidence completeness (deterministic, explainable) ----------- */}
        <SectionCard
          eyebrow="Evidence"
          title="Evidence completeness"
          subtitle="How complete the recorded evidence of OPEN complaints is — explicitly NOT a probability of violation"
        >
          <div className="row row--between row--wrap" style={{ gap: 'var(--space-3)' }}>
            <div>
              <div className="metric__value">{d.evidence.average}%</div>
              <div className="cell-muted" style={{ fontSize: 'var(--fs-sm)' }}>
                average across {d.evidence.scored} open complaint
                {d.evidence.scored === 1 ? '' : 's'}
              </div>
            </div>
            <Link to="/complaints?evidence=MINIMAL" className="btn btn--subtle btn--sm">
              View minimal-evidence complaints
              <Icon name="arrowRight" size={13} />
            </Link>
          </div>
          <div style={{ marginTop: 'var(--space-3)' }}>
            <DistributionBar
              segments={[
                { label: 'Complete (≥80)', value: d.evidence.complete, tone: 'positive' as const },
                { label: 'Partial (50–79)', value: d.evidence.partial, tone: 'warning' as const },
                { label: 'Minimal (<50)', value: d.evidence.minimal, tone: 'critical' as const },
              ].filter((s) => s.value > 0)}
            />
          </div>
          <details className="dept-explain" style={{ marginTop: 'var(--space-3)' }}>
            <summary className="cell-muted" style={{ fontSize: 'var(--fs-sm)', cursor: 'pointer' }}>
              How this score is calculated (deterministic)
            </summary>
            <ul className="cell-muted" style={{ fontSize: 'var(--fs-sm)', margin: 'var(--space-2) 0 0', paddingLeft: 'var(--space-4)' }}>
              <li>Package photo present — 25</li>
              <li>OCR extraction read declarations — 15</li>
              <li>Product details, citizen description, shop, location — 10 each</li>
              <li>Citizen follow-up response — 10</li>
              <li>Submission timestamp — 10</li>
            </ul>
          </details>
        </SectionCard>
      </div>

      {/* --- UI-07 — Physical verification workload (real SQL counts) ------ */}
      <SectionCard
        eyebrow="Physical verification"
        title="Physical verification & lots"
        subtitle="OCR reads declarations; inspectors measure contents. Every figure below is a live database count of real records — none is a compliance signal."
      >
        <div className="grid grid--metrics">
          <div className="metric" title="Inspections with at least one open REQUIRED measurement task (inspection-level; lot-anchored tasks are counted under lots)">
            <div className="metric__top">
              <span className="metric__label">Inspections requiring verification</span>
              <span className="metric__icon" aria-hidden><Icon name="scale" size={17} /></span>
            </div>
            <div className="metric__value">{d.physicalVerification.inspectionsRequiringVerification}</div>
            <div className="metric__foot"><span>open REQUIRED measurement tasks</span></div>
          </div>
          <div className="metric" title="Total recorded measurement results (append-only rows)">
            <div className="metric__top">
              <span className="metric__label">Measurements completed</span>
              <span className="metric__icon" aria-hidden><Icon name="check" size={17} /></span>
            </div>
            <div className="metric__value">{d.physicalVerification.measurementsCompleted}</div>
            <div className="metric__foot"><span>recorded by inspectors, append-only</span></div>
          </div>
          <div className="metric" title="Lots still IN_PROGRESS (decision not yet submitted)">
            <div className="metric__top">
              <span className="metric__label">Lots under verification</span>
              <span className="metric__icon" aria-hidden><Icon name="package" size={17} /></span>
            </div>
            <div className="metric__value">{d.physicalVerification.lotsUnderVerification}</div>
            <div className="metric__foot"><span>lot result not yet submitted</span></div>
          </div>
          <div className="metric" title="IN_PROGRESS lots with sampled packages still awaiting a measurement">
            <div className="metric__top">
              <span className="metric__label">Lots awaiting measurement</span>
              <span className="metric__icon" aria-hidden><Icon name="clock" size={17} /></span>
            </div>
            <div className="metric__value">{d.physicalVerification.lotsAwaitingMeasurement}</div>
            <div className="metric__foot"><span>sampled packages still unmeasured</span></div>
          </div>
          <div className="metric" title="Lots with a submitted decision (COMPLIANT / NON_COMPLIANT / REQUIRES_REVIEW)">
            <div className="metric__top">
              <span className="metric__label">Completed lot assessments</span>
              <span className="metric__icon" aria-hidden><Icon name="evidence" size={17} /></span>
            </div>
            <div className="metric__value">{d.physicalVerification.lotsCompleted}</div>
            <div className="metric__foot"><span>inspector decisions submitted</span></div>
          </div>
        </div>
      </SectionCard>

      {/* --- Priority complaint queue ---------------------------------------- */}
      <SectionCard
        eyebrow="Priority queue"
        title="Priority complaints"
        subtitle="Open complaints ordered by effective priority (official decision first, else system screening), oldest within each band"
        flush
      >
        {d.priorityQueue.length === 0 ? (
          <div style={{ padding: 'var(--space-5)' }}>
            <EmptyState icon="check" title="No open complaints" message="Nothing is awaiting department action." />
          </div>
        ) : (
          <ul className="stack stack--sm" style={{ padding: 'var(--space-4)' }}>
            {d.priorityQueue.map((c) => (
              <PriorityRow key={c.id} complaint={c} canAct={canAct} />
            ))}
          </ul>
        )}
      </SectionCard>

      <div className="grid grid--2">
        {/* --- Needs attention (all values computed from real data) --------- */}
        <SectionCard
          eyebrow="Signals"
          title="Needs attention"
          subtitle="Actionable states computed from the live complaint records — click through to the filtered queue"
        >
          <ul className="stack stack--sm">
            {d.needsAttention.map((item) => {
              const active = item.count > 0;
              const query = new URLSearchParams(item.filters).toString();
              const inner = (
                <>
                  <span className="row row--between row--wrap" style={{ gap: 'var(--space-2)' }}>
                    <span className="cell-strong">{item.label}</span>
                    <Badge tone={active ? 'warning' : 'neutral'} dot>
                      {item.count}
                    </Badge>
                  </span>
                  <span className="cell-muted" style={{ fontSize: 'var(--fs-sm)' }}>
                    {item.description}
                  </span>
                </>
              );
              return (
                <li key={item.kind}>
                  {active ? (
                    <Link to={`/complaints${query ? `?${query}` : ''}`} className="dept-attention">
                      {inner}
                    </Link>
                  ) : (
                    <div className="dept-attention dept-attention--muted" aria-label={`${item.label}: none`}>
                      {inner}
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        </SectionCard>

        {/* --- Location intelligence ---------------------------------------- */}
        <SectionCard
          eyebrow="Location intelligence"
          title="Complaint locations"
          subtitle="Aggregated from the locations citizens actually reported"
        >
          {d.locations.length === 0 ? (
            <EmptyState
              icon="evidence"
              title="No location data yet"
              message="Location intelligence will appear as complaint location data grows."
            />
          ) : (
            <div className="table-wrap">
              <table className="data-table" style={{ width: '100%' }} aria-label="Complaint locations">
                <thead>
                  <tr>
                    <th scope="col">Area</th>
                    <th scope="col" style={{ textAlign: 'right' }}>Complaints</th>
                    <th scope="col">High priority</th>
                    <th scope="col">Inspections</th>
                  </tr>
                </thead>
                <tbody>
                  {d.locations.map((loc) => (
                    <tr key={loc.area}>
                      <td className="cell-strong">{loc.area}</td>
                      <td className="cell-mono" style={{ textAlign: 'right' }}>{loc.complaints}</td>
                      <td>
                        {loc.highPriority > 0 ? (
                          <Badge tone="critical" outline>
                            {loc.highPriority} HIGH
                          </Badge>
                        ) : (
                          <span className="cell-muted">—</span>
                        )}
                      </td>
                      <td>
                        {loc.inspections > 0 ? (
                          <Badge tone="info" outline>
                            {loc.inspections} linked
                          </Badge>
                        ) : (
                          <span className="cell-muted">—</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </SectionCard>
      </div>

      {/* --- Complaint → Inspection pipeline (the METRASIGHT principle) ------ */}
      <SectionCard
        eyebrow="Pipeline"
        title="Complaint → Inspection pipeline"
        subtitle="Real counts of how far complaints have progressed — CITIZEN reports, DEPARTMENT review and prioritization, INSPECTOR verification and decision"
      >
        <div className="dept-pipeline">
          <PipelineStage
            actor="Citizen"
            verb="Reports"
            label="Citizen reports"
            caption="scan → suspected issue → complaint"
            count={d.pipeline.citizenReports}
          />
          <PipelineStage
            actor="Department"
            verb="Reviews"
            label="Department review"
            caption="review started, info requested or rejected"
            count={d.pipeline.departmentReview}
          />
          <PipelineStage
            actor="Department"
            verb="Prioritizes"
            label="Accepted"
            caption="accepted for further review + assigned"
            count={d.pipeline.accepted}
            sub={d.pipeline.inspectionAssigned}
            subLabel="inspectors assigned"
          />
          <PipelineStage
            actor="Inspector"
            verb="Inspects"
            label="Inspections completed"
            caption="targeted field inspections finished"
            count={d.pipeline.inspectionCompleted}
          />
          <PipelineStage
            actor="Inspector"
            verb="Decides"
            label="Decisions recorded"
            caption="action taken or complaint closed"
            count={d.pipeline.decision}
          />
        </div>
        <p className="cell-muted" style={{ fontSize: 'var(--fs-sm)', marginBottom: 0 }}>
          Each stage counts complaints that actually reached it in the database — this is
          the operating principle of METRASIGHT, not a generic funnel: evidence supports
          every decision, and the final determination always belongs to the authorized
          officer.
        </p>
      </SectionCard>

      <div className="grid grid--2">
        {/* --- Recent activity (real audit events) --------------------------- */}
        <SectionCard
          eyebrow="Audit trail"
          title="Recent department activity"
          subtitle="Real audit events — who acted, on which complaint, when"
        >
          {d.recentActivity.length === 0 ? (
            <EmptyState
              icon="audit"
              title="No department activity yet"
              message="Actions on complaints (review, acceptance, assignment, inspections) are recorded here as they happen."
            />
          ) : (
            <ul className="stack stack--sm">
              {d.recentActivity.slice(0, 8).map((event) => (
                <ActivityRow key={event.id} event={event} />
              ))}
            </ul>
          )}
          <div className="row" style={{ marginTop: 'var(--space-3)' }}>
            <Link to="/audit" className="btn btn--subtle btn--sm">
              Open full audit trail
              <Icon name="arrowRight" size={13} />
            </Link>
          </div>
        </SectionCard>

        <QuickActions />
      </div>
    </>
  );
}

/* -------------------------------------------------------------------------- */
/* Sections                                                                    */
/* -------------------------------------------------------------------------- */

function QuickActions() {
  return (
    <SectionCard
      eyebrow="Shortcuts"
      title="Quick actions"
      subtitle="Straight into the existing workflows — no duplicate pages"
    >
      <div className="stack stack--sm">
        <Link to="/complaints" className="btn btn--primary">
          <Icon name="complaints" size={15} />
          Review complaints
        </Link>
        <Link to="/inspections/new" className="btn btn--subtle">
          <Icon name="plus" size={15} />
          Create inspection
        </Link>
        <Link to="/evidence" className="btn btn--subtle">
          <Icon name="search" size={15} />
          Search product evidence
        </Link>
        <Link to="/complaints?risk=HIGH" className="btn btn--subtle">
          <Icon name="alert" size={15} />
          View high-risk cases
        </Link>
        <Link to="/audit" className="btn btn--subtle">
          <Icon name="audit" size={15} />
          Open audit trail
        </Link>
      </div>
    </SectionCard>
  );
}

function PriorityRow({ complaint, canAct }: { complaint: PriorityComplaint; canAct: boolean }) {
  const priorityMeta = complaint.priority
    ? COMPLAINT_RISK_META[complaint.priority]
    : undefined;
  return (
    <li className="row row--between row--wrap card" style={{ padding: 'var(--space-3) var(--space-4)', gap: 'var(--space-3)' }}>
      <div style={{ minWidth: 0, flex: '1 1 260px' }}>
        <div className="row row--wrap" style={{ gap: 6 }}>
          <Link to={`/complaints/${complaint.id}`} className="cell-mono cell-strong" style={{ textDecoration: 'none' }}>
            {complaint.reference}
          </Link>
          <Badge tone={COMPLAINT_STATUS_META[complaint.status]?.tone} dot>
            {COMPLAINT_STATUS_META[complaint.status]?.label ?? complaint.status}
          </Badge>
          {complaint.priority && (
            <Badge
              tone={priorityMeta?.tone}
              outline
              title={
                complaint.prioritySource === 'OFFICIAL_DECISION'
                  ? 'OFFICIAL PRIORITY DECISION — set by the department.'
                  : 'SYSTEM SCREENING — deterministic rule over the scan evidence. Not an official decision.'
              }
            >
              {complaint.priority} ·{' '}
              {complaint.prioritySource === 'OFFICIAL_DECISION' ? 'official' : 'screening'}
            </Badge>
          )}
        </div>
        <div className="cell-strong" style={{ marginTop: 2 }}>
          {complaint.product}
        </div>
        <div className="cell-muted" style={{ fontSize: 'var(--fs-sm)' }}>
          {complaint.issue} · {complaint.location ?? 'no location'} · submitted{' '}
          {formatDateTime(complaint.createdAt)}
        </div>
      </div>
      <div className="row row--wrap" style={{ gap: 'var(--space-2)', alignItems: 'center' }}>
        <span
          className="cell-mono"
          style={{ fontSize: 'var(--fs-sm)' }}
          title="Evidence completeness — how complete the recorded evidence is. Not a violation likelihood."
        >
          {complaint.evidenceCompleteness}% evidence
        </span>
        <Link to={`/complaints/${complaint.id}`} className="btn btn--subtle btn--sm">
          View complaint
        </Link>
        <Link to={`/complaints/${complaint.id}#evidence`} className="btn btn--ghost btn--sm">
          Review evidence
        </Link>
        {canAct && complaint.status === 'ACCEPTED' && (
          <Link to={`/complaints/${complaint.id}?action=assign`} className="btn btn--subtle btn--sm">
            Assign
          </Link>
        )}
        {canAct && (complaint.status === 'ACCEPTED' || complaint.status === 'ASSIGNED') && (
          <Link to={`/complaints/${complaint.id}?action=inspect`} className="btn btn--primary btn--sm">
            Convert to inspection
          </Link>
        )}
      </div>
    </li>
  );
}

function ActivityRow({ event }: { event: DepartmentActivity }) {
  const label = ACTIVITY_LABELS[event.event] ?? event.event.replace(/_/g, ' ').toLowerCase();
  const body = (
    <>
      <span className="row row--between row--wrap" style={{ gap: 'var(--space-2)' }}>
        <span className="cell-strong">{label}</span>
        <span className="cell-muted" style={{ fontSize: 'var(--fs-xs)' }}>
          {formatDateTime(event.createdAt)}
        </span>
      </span>
      <span className="cell-muted" style={{ fontSize: 'var(--fs-sm)' }}>
        {event.actorName ?? 'Department officer'}
        {event.reference ? (
          <>
            {' · '}
            <span className="cell-mono">{event.reference}</span>
          </>
        ) : null}
      </span>
    </>
  );
  return (
    <li>
      {event.reportId ? (
        <Link to={`/complaints/${event.reportId}`} className="dept-activity">
          {body}
        </Link>
      ) : (
        <div className="dept-activity">{body}</div>
      )}
    </li>
  );
}

/** One clickable rollup row (label + proportional bar + count). */
function RollupRow({
  to,
  label,
  value,
  max,
  tone,
}: {
  to: string;
  label: string;
  value: number;
  max: number;
  tone: string;
}) {
  return (
    <Link to={to} className="dept-rollup__row" title={`${label}: ${value} — open the filtered queue`}>
      <span className="dept-rollup__label">{label}</span>
      <span className="dept-rollup__track">
        <span className={`dept-rollup__fill tone-${tone}`} style={{ width: `${(value / max) * 100}%` }} />
      </span>
      <span className="dept-rollup__value cell-mono">{value}</span>
    </Link>
  );
}

/** Complaints-per-day bar chart — real counts, zero-filled, accessible. */
function TrendChart({ points }: { points: ComplaintTrendPoint[] }) {
  const max = Math.max(...points.map((p) => p.count), 1);
  const busiest = points.reduce((a, b) => (b.count > a.count ? b : a), points[0]);
  return (
    <div className="stack stack--sm">
      <div
        className="dept-trend"
        role="img"
        aria-label={`Complaints created per day over the last ${points.length} days. Busiest day: ${busiest.date} with ${busiest.count} complaint${busiest.count === 1 ? '' : 's'}.`}
      >
        {points.map((p) => (
          <div
            key={p.date}
            className="dept-trend__col"
            title={`${p.date}: ${p.count} complaint${p.count === 1 ? '' : 's'}`}
          >
            <div
              className="dept-trend__bar"
              style={{ height: `${(p.count / max) * 100}%` }}
              data-empty={p.count === 0}
            />
          </div>
        ))}
      </div>
      <div className="row row--between cell-muted" style={{ fontSize: 'var(--fs-xs)' }}>
        <span>{points[0]?.date}</span>
        <span>{points[Math.floor(points.length / 2)]?.date}</span>
        <span>{points[points.length - 1]?.date}</span>
      </div>
    </div>
  );
}

/** One stage of the complaint → inspection pipeline. */
function PipelineStage({
  actor,
  verb,
  label,
  caption,
  count,
  sub,
  subLabel,
}: {
  actor: string;
  verb: string;
  label: string;
  caption: string;
  count: number;
  sub?: number;
  subLabel?: string;
}) {
  return (
    <div className="dept-pipeline__stage">
      <span className="dept-pipeline__actor">
        {actor} <Icon name="arrowRight" size={11} /> {verb}
      </span>
      <span className="dept-pipeline__count cell-mono">{count}</span>
      <span className="dept-pipeline__label">{label}</span>
      <span className="dept-pipeline__caption">{caption}</span>
      {sub !== undefined && (
        <span className="dept-pipeline__caption">
          ({sub} {subLabel})
        </span>
      )}
    </div>
  );
}
