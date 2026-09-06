/**
 * Report detail page (UI-08 §4–§13, §18, §19).
 *
 * /reports/:id — three columns:
 *   LEFT   metadata, status, inspection + inspector context, source complaint
 *   CENTER the frozen snapshot: executive findings, regulatory basis,
 *          physical measurements, lot intelligence, evidence manifest
 *   RIGHT  evidence completeness (the planner gate), the finalization gate
 *          checklist, the inspector decision, and the sticky actions
 *          (generate / review / finalize / amend / export / evidence pack).
 *
 * Everything rendered comes from the frozen snapshot the backend generated —
 * the page never recomputes findings, never invents regulatory text, and
 * never presents the AI as the legal authority.
 */
import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';

import { REPORT_BOUNDARY_NOTE } from '@legalmet/types';
import type {
  ReportSnapshotFinding,
  ReportSnapshotLot,
  ReportSnapshotMeasurement,
  ReportSourceComplaint,
} from '@legalmet/types';

import { useApp } from '../app/AppContext';
import { Badge } from '../components/Badge';
import { Card, CardBody, SectionCard } from '../components/Card';
import { DataTable, type Column } from '../components/DataTable';
import { Icon } from '../components/Icon';
import { PageHeader } from '../components/PageHeader';
import { EmptyState, ErrorState } from '../components/states';
import { formatDateTime, humanizeEnum } from '../lib/format';

import {
  EvidenceSourceChip,
  EvidenceStatusChip,
  ReportResultChip,
  ReportStatusChip,
} from '../reports/ReportChips';
import { useReport } from '../reports/useReport';
import { ReportActionsPanel } from '../reports/ReportActionsPanel';
import { EvidencePackDrawer } from '../reports/EvidencePackDrawer';
import { ReportAuditCard } from '../reports/ReportAuditCard';

/** Write actions are hidden AND the backend rejects them (defense in depth). */
const WRITE_ROLES = ['ADMIN', 'INSPECTOR', 'SUPERVISOR'];

export function ReportDetailPage() {
  const { id = '' } = useParams();
  const { user, isLive } = useApp();
  const report = useReport(id, isLive);
  const canWrite = WRITE_ROLES.includes(user.role);

  const [packOpen, setPackOpen] = useState(false);

  if (report.loading) {
    return (
      <div className="page">
        <PageHeader eyebrow="Output" title="Report" lead="Loading report…" />
        <Card>
          <CardBody>
            <p style={{ color: 'var(--text-muted)' }}>Loading report…</p>
            <span className="spinner" aria-hidden />
          </CardBody>
        </Card>
      </div>
    );
  }

  if (report.error || !report.report) {
    return (
      <div className="page">
        <PageHeader eyebrow="Output" title="Report" lead="The report could not be loaded." />
        <ErrorState
          error={new Error(report.error ?? 'Report not found.')}
          onRetry={() => void report.reload()}
        />
      </div>
    );
  }

  const data = report.report;
  const snapshot = (data.snapshot ?? null) as
    | (Record<string, unknown> & {
        findings?: ReportSnapshotFinding[];
        measurements?: ReportSnapshotMeasurement[];
        lots?: ReportSnapshotLot[];
      })
    | null;
  const findings = snapshot?.findings ?? [];
  const measurements = snapshot?.measurements ?? [];
  const lots = snapshot?.lots ?? [];

  return (
    <div className="page">
      <PageHeader
        eyebrow="Output"
        title={`Report — ${data.inspectionReference}`}
        lead="Evidence-backed inspection report. Versioned, traceable, inspector-reviewed."
        actions={
          <>
            <Link className="btn btn--subtle" to={`/inspections/${data.inspectionId}`}>
              <Icon name="inspections" size={15} />
              Open Inspection
            </Link>
            <ReportStatusChip status={data.status} />
          </>
        }
      />

      <div className="report-layout">
        {/* ---------------------------------------------------------- LEFT */}
        <div className="report-col report-col--meta">
          <SectionCard title="Report metadata" eyebrow="Identity">
            <dl className="kv">
              <dt>Report ID</dt>
              <dd title={data.id}>{data.id.slice(0, 13)}…</dd>
              <dt>Inspection ID</dt>
              <dd title={data.inspectionId}>{data.inspectionId.slice(0, 13)}…</dd>
              <dt>Reference</dt>
              <dd>{data.inspectionReference || '—'}</dd>
              <dt>Version</dt>
              <dd>v{data.version}</dd>
              <dt>Status</dt>
              <dd>
                <ReportStatusChip status={data.status} />
              </dd>
              <dt>Result</dt>
              <dd>
                <ReportResultChip result={data.result} />
              </dd>
              <dt>Created by</dt>
              <dd>{data.createdByName ?? '—'}</dd>
              <dt>Generated</dt>
              <dd>{formatDateTime(data.generatedAt)}</dd>
              <dt>Finalized</dt>
              <dd>
                {data.finalizedAt ? (
                  <>
                    {formatDateTime(data.finalizedAt)}
                    <div className="cell-muted" style={{ fontSize: 'var(--fs-sm)' }}>
                      by {data.finalizedByName ?? '—'}
                    </div>
                  </>
                ) : (
                  '—'
                )}
              </dd>
            </dl>
          </SectionCard>

          <SectionCard title="Inspection" eyebrow="Context">
            <dl className="kv">
              <dt>Product</dt>
              <dd>{data.productName ?? '—'}</dd>
              <dt>Category</dt>
              <dd>{data.productCategory ? humanizeEnum(data.productCategory) : '—'}</dd>
              <dt>Inspection date</dt>
              <dd>{formatDateTime(data.inspectionDate)}</dd>
              <dt>Inspection status</dt>
              <dd>{data.inspectionStatus ? humanizeEnum(data.inspectionStatus) : '—'}</dd>
              <dt>Inspector</dt>
              <dd>{data.inspectorName ?? 'NOT RECORDED'}</dd>
            </dl>
          </SectionCard>

          {/* §4: source context — citizen complaints stay distinct from
              official evidence. */}
          <SourceContextCard complaint={data.sourceComplaint ?? null} />
        </div>

        {/* -------------------------------------------------------- CENTER */}
        <div className="report-col report-col--main">
          {!snapshot ? (
            <Card>
              <CardBody>
                <EmptyState
                  icon="reports"
                  title="Not generated yet"
                  message="Generate the report to freeze a snapshot of the inspection evidence, findings and decision. Nothing is asserted before that."
                  action={
                    canWrite ? (
                      <button
                        type="button"
                        className="btn btn--primary"
                        disabled={report.acting}
                        onClick={() => void report.generate()}
                      >
                        <Icon name="sparkscan" size={15} />
                        Generate Report
                      </button>
                    ) : undefined
                  }
                />
              </CardBody>
            </Card>
          ) : (
            <>
              <FindingsCard findings={findings} />
              <RegulatoryBasisCard snapshot={snapshot} />
              <MeasurementsCard measurements={measurements} />
              {lots.length > 0 && <LotsCard lots={lots} />}
              <DecisionCard snapshot={snapshot} />
            </>
          )}
        </div>

        {/* --------------------------------------------------------- RIGHT */}
        <div className="report-col report-col--side">
          <ReportActionsPanel
            report={data}
            acting={report.acting}
            canWrite={canWrite}
            actionError={report.actionError}
            actionNotice={report.actionNotice}
            onGenerate={() => void report.generate()}
            onReview={() => void report.review()}
            onFinalize={() => void report.finalize()}
            onAmend={(reason) => report.amend(reason)}
            onExport={(fmt) => report.export(fmt)}
            onOpenPack={() => setPackOpen(true)}
          />
          <ReportAuditCard reportId={data.id} />
        </div>
      </div>

      <p className="boundary-note" style={{ fontSize: 'var(--fs-sm)', color: 'var(--text-faint)' }}>
        <Icon name="info" size={14} />
        {REPORT_BOUNDARY_NOTE}
      </p>

      {packOpen && <EvidencePackDrawer reportId={data.id} onClose={() => setPackOpen(false)} />}
    </div>
  );
}

/* ------------------------------------------------------------------ source */

function SourceContextCard({ complaint }: { complaint: ReportSourceComplaint | null }) {
  if (!complaint) {
    return (
      <SectionCard title="Source context" eyebrow="Origin">
        <p style={{ margin: 0, color: 'var(--text-muted)', fontSize: 'var(--fs-sm)' }}>
          Routine inspection — no citizen complaint origin.
        </p>
      </SectionCard>
    );
  }
  return (
    <SectionCard
      title="Source context"
      eyebrow="Origin"
      subtitle="Citizen complaint — SOURCE evidence, kept separate from official evidence"
      actions={<EvidenceSourceChip source="SOURCE" />}
    >
      <dl className="kv">
        <dt>Complaint ref.</dt>
        <dd>{complaint.reference}</dd>
        <dt>Status</dt>
        <dd>{humanizeEnum(complaint.status)}</dd>
        <dt>Product</dt>
        <dd>{complaint.product ?? '—'}</dd>
        <dt>Location</dt>
        <dd>{complaint.location ?? '—'}</dd>
        <dt>Issue</dt>
        <dd>{complaint.issue}</dd>
        <dt>Priority</dt>
        <dd>{complaint.priority ? humanizeEnum(complaint.priority) : '—'}</dd>
        <dt>Submitted</dt>
        <dd>{formatDateTime(complaint.submittedAt)}</dd>
      </dl>
    </SectionCard>
  );
}

/* ---------------------------------------------------------------- findings */

function FindingsCard({ findings }: { findings: ReportSnapshotFinding[] }) {
  const columns: Column<ReportSnapshotFinding>[] = [
    {
      key: 'id',
      header: 'ID',
      width: '90px',
      render: (f) => <span className="cell-muted" title={f.id}>{f.id.slice(0, 8)}</span>,
    },
    {
      key: 'status',
      header: 'Status',
      render: (f) => <Badge tone={f.status === 'COMPLIANT' ? 'positive' : f.status === 'NOT_DETECTED' ? 'warning' : 'critical'}>{humanizeEnum(f.status)}</Badge>,
    },
    {
      key: 'severity',
      header: 'Severity',
      render: (f) => <span>{humanizeEnum(f.severity)}</span>,
    },
    {
      key: 'requirement',
      header: 'Requirement',
      render: (f) => (
        <div>
          <div>{f.requirement || '—'}</div>
          {f.ruleCode && (
            <div className="cell-muted" style={{ fontSize: 'var(--fs-sm)' }}>
              Rule {f.ruleCode}
              {f.ruleVersion ? ` · ${f.ruleVersion}` : ''}
            </div>
          )}
        </div>
      ),
    },
    {
      key: 'evidence',
      header: 'Evidence',
      render: (f) => <EvidenceStatusChip status={f.evidenceStatus} />,
    },
    {
      key: 'review',
      header: 'Review',
      render: (f) => <span>{humanizeEnum(f.reviewState)}</span>,
    },
    {
      key: 'source',
      header: 'Source',
      render: (f) => <EvidenceSourceChip source={f.source} />,
    },
  ];

  return (
    <SectionCard
      title="Executive findings"
      eyebrow="Findings"
      subtitle="Frozen at generation — engine output with the inspector's review state"
      flush
    >
      {findings.length > 0 ? (
        <DataTable columns={columns} rows={findings} getRowId={(f) => f.id} ariaLabel="Report findings" />
      ) : (
        <CardBody>
          <EmptyState
            icon="info"
            title="No evaluation findings recorded"
            message="Result is NOT EVALUATED — the report does not claim compliance or violation without an engine evaluation."
          />
        </CardBody>
      )}
    </SectionCard>
  );
}

/* -------------------------------------------------------- regulatory basis */

function RegulatoryBasisCard({ snapshot }: { snapshot: Record<string, unknown> }) {
  const basis = (snapshot['regulatoryBasis'] ?? []) as Array<Record<string, unknown>>;
  return (
    <SectionCard
      title="Regulatory basis"
      eyebrow="Basis"
      subtitle="Quoted from the deterministic engine output frozen at evaluation time"
    >
      <div className="stack stack--sm">
        {basis.map((entry, i) => {
          const engineVersion = entry['engineVersion'];
          const versionLabel = entry['regulatoryVersionLabel'];
          const note = entry['note'];
          if (!engineVersion) {
            return (
              <div key={i} className="demo-note">
                <Icon name="alert" size={14} />
                <span>
                  {typeof note === 'string'
                    ? note
                    : 'NOT EVALUATED — REGULATORY REVIEW REQUIRED'}
                </span>
              </div>
            );
          }
          return (
            <dl key={i} className="kv">
              <dt>Engine version</dt>
              <dd>{String(engineVersion)}</dd>
              <dt>Regulatory version</dt>
              <dd>{versionLabel ? String(versionLabel) : '—'}</dd>
              <dt>Context date</dt>
              <dd>{entry['contextDate'] ? String(entry['contextDate']) : '—'}</dd>
            </dl>
          );
        })}
      </div>
    </SectionCard>
  );
}

/* ---------------------------------------------------------- measurements */

function MeasurementsCard({ measurements }: { measurements: ReportSnapshotMeasurement[] }) {
  const columns: Column<ReportSnapshotMeasurement>[] = [
    { key: 'anchor', header: 'Anchor', render: (m) => <span>{m.anchor}</span> },
    {
      key: 'declared',
      header: 'Declared',
      render: (m) => <span>{m.declaredValue ?? '—'}</span>,
    },
    {
      key: 'measured',
      header: 'Measured',
      render: (m) => (
        <span>
          {m.measuredValue ?? '—'}
          {m.unit ? ` ${m.unit}` : ''}
        </span>
      ),
    },
    {
      key: 'difference',
      header: 'Observed diff.',
      render: (m) => <span>{m.observedDifference ?? '—'}</span>,
    },
    {
      key: 'instrument',
      header: 'Instrument',
      render: (m) =>
        m.instrumentId ? (
          <span>
            {m.instrumentId}
            <div className="cell-muted" style={{ fontSize: 'var(--fs-sm)' }}>
              {m.instrumentVerificationStatus ? humanizeEnum(m.instrumentVerificationStatus) : 'status not recorded'}
            </div>
          </span>
        ) : (
          <span className="cell-muted" title="Manual measurement entry — instrument integration not available in prototype.">
            manual entry
          </span>
        ),
    },
    {
      key: 'evaluation',
      header: 'Evaluation',
      render: (m) => <EvidenceStatusChip status={m.evaluationStatus} />,
    },
  ];

  return (
    <SectionCard
      title="Physical verification"
      eyebrow="Measurements"
      subtitle="Declared vs measured, as recorded — the frozen engine evaluation is the only legal column"
      flush
    >
      {measurements.length > 0 ? (
        <>
          <DataTable columns={columns} rows={measurements} getRowId={(m) => m.measurementId} ariaLabel="Physical measurements" />
          <CardBody>
            <p style={{ margin: 0, fontSize: 'var(--fs-sm)', color: 'var(--text-faint)' }}>
              The observed difference is arithmetic on recorded values — a legal conclusion appears
              only in the evaluation column, never from the difference itself. Entries without an
              instrument are manual: instrument integration is not available in the prototype.
            </p>
          </CardBody>
        </>
      ) : (
        <CardBody>
          <EmptyState
            icon="scale"
            title="No physical measurements recorded"
            message="Physical verification happens in the inspection workspace; the report freezes whatever was recorded."
          />
        </CardBody>
      )}
    </SectionCard>
  );
}

/* ----------------------------------------------------------------- lots */

function LotsCard({ lots }: { lots: ReportSnapshotLot[] }) {
  const columns: Column<ReportSnapshotLot>[] = [
    { key: 'label', header: 'Lot', render: (l) => <span>{l.label}</span> },
    { key: 'declared', header: 'Declared', render: (l) => <span>{l.declaredValue}</span> },
    { key: 'size', header: 'Lot size', align: 'right', render: (l) => <span>{l.lotSize}</span> },
    { key: 'sampled', header: 'Sampled', align: 'right', render: (l) => <span>{l.sampled}</span> },
    { key: 'measured', header: 'Measured', align: 'right', render: (l) => <span>{l.measured}</span> },
    {
      key: 'decision',
      header: 'Result',
      render: (l) =>
        l.decision ? (
          <Badge tone={l.decision === 'COMPLIANT' ? 'positive' : l.decision === 'IN_PROGRESS' ? 'neutral' : 'critical'}>
            {humanizeEnum(l.decision)}
          </Badge>
        ) : (
          <span className="cell-muted">in progress</span>
        ),
    },
  ];
  return (
    <SectionCard
      title="Lot intelligence"
      eyebrow="Lots"
      subtitle="Observed sampling statistics — sampling shown is an AI-assisted recommendation, not a statutory procedure"
      flush
    >
      <DataTable columns={columns} rows={lots} getRowId={(l) => l.lotId} ariaLabel="Lot intelligence" />
    </SectionCard>
  );
}

/* ------------------------------------------------------------- decision */

function DecisionCard({ snapshot }: { snapshot: Record<string, unknown> }) {
  const decision = (snapshot['decision'] ?? null) as Record<string, unknown> | null;
  return (
    <SectionCard
      title="Inspector decision"
      eyebrow="Final decision"
      subtitle="AI-assisted assessment. Final decision recorded by authorized inspector."
    >
      {decision ? (
        <dl className="kv">
          <dt>Decision</dt>
          <dd>
            <ReportResultChip result={String(decision['decision'] ?? 'NOT_EVALUATED')} />
          </dd>
          <dt>Reason</dt>
          <dd>{(decision['reason'] as string) ?? '—'}</dd>
          <dt>Decided by</dt>
          <dd>{(decision['decidedByName'] as string) ?? '—'}</dd>
          <dt>Decided at</dt>
          <dd>{formatDateTime(decision['decidedAt'] as string)}</dd>
        </dl>
      ) : (
        <EmptyState
          icon="alert"
          title="No inspector decision recorded"
          message="The report cannot state a result without one — the AI is never the final legal authority."
        />
      )}
    </SectionCard>
  );
}
