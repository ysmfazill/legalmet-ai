/**
 * Engine review queue (Prompt 6 + Prompt 8) — REAL backend findings.
 *
 * Lists the deterministic engine findings awaiting an inspector decision:
 * REVIEW_REQUIRED, NON_COMPLIANT, NOT_DETECTED and NOT_EVALUATED from each
 * inspection's LATEST evaluation (superseded evaluations never re-queue).
 *
 * Each row shows BOTH verdicts, never conflated:
 *   - the SYSTEM finding (what the engine concluded — badge)
 *   - the HUMAN review state (what the inspector decided — badge)
 * Clicking a row opens the inspection workspace where the review actions live.
 */
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

import type { EngineFinding } from '@legalmet/types';

import { api } from '../api/client';
import { EngineFindingBadge, FindingReviewStateBadge } from '../components/Badge';
import { Card, CardBody, CardHead } from '../components/Card';
import type { Column } from '../components/DataTable';
import { DataTable } from '../components/DataTable';
import { Drawer } from '../components/Drawer';
import { EvidenceTracePanel } from '../evidence/EvidenceTracePanel';
import { evidenceLoaders } from '../evidence/useEvidenceGraph';
import { EmptyState } from '../components/states';
import { useAsync } from '../data/useAsync';
import { formatDateTime } from '../lib/format';

export function EngineReviewQueueSection() {
  const navigate = useNavigate();
  const [traceFinding, setTraceFinding] = useState<EngineFinding | null>(null);
  const query = useAsync(
    () => api.listComplianceReviewQueue({ page: 1, pageSize: 100 }),
    [],
  );

  if (query.status === 'loading') {
    return (
      <Card>
        <CardHead
          eyebrow="Compliance engine"
          title="Engine review queue"
          subtitle="Deterministic findings awaiting an inspector decision"
        />
        <CardBody>
          <p style={{ color: 'var(--text-muted)' }}>Loading engine findings…</p>
        </CardBody>
      </Card>
    );
  }

  if (query.status === 'error') {
    return (
      <Card>
        <CardHead
          eyebrow="Compliance engine"
          title="Engine review queue"
          subtitle="Deterministic findings awaiting an inspector decision"
        />
        <CardBody>
          <p style={{ color: 'var(--text-muted)' }}>
            Engine findings unavailable ({query.error.message}).
          </p>
        </CardBody>
      </Card>
    );
  }

  const findings = query.data.items;

  const columns: Column<EngineFinding>[] = [
    {
      key: 'requirement',
      header: 'Requirement',
      render: (f) => (
        <div style={{ minWidth: 0 }}>
          <div className="cell-strong">{f.provenance?.requirementCode ?? '—'}</div>
          <div className="cell-muted" style={{ fontSize: 'var(--fs-sm)' }}>
            {f.provenance?.requirementTitle ?? ''}
          </div>
        </div>
      ),
    },
    { key: 'status', header: 'System finding', render: (f) => <EngineFindingBadge status={f.status} /> },
    {
      key: 'review',
      header: 'Human review',
      render: (f) => <FindingReviewStateBadge state={f.reviewState} />,
    },
    {
      key: 'detected',
      header: 'Detected',
      render: (f) => (
        <span
          className="cell-muted"
          style={{ fontSize: 'var(--fs-sm)', maxWidth: 260, display: 'inline-block', overflowWrap: 'anywhere' }}
        >
          {f.detectedValue ?? 'Nothing detected — not evidence of absence'}
        </span>
      ),
    },
    {
      key: 'version',
      header: 'Version in force',
      render: (f) => (
        <span className="cell-muted" style={{ fontSize: 'var(--fs-sm)' }}>
          {f.provenance?.versionLabel ?? '—'}
        </span>
      ),
    },
    {
      key: 'created',
      header: 'Evaluated',
      render: (f) => (
        <span className="cell-muted" style={{ fontSize: 'var(--fs-sm)' }}>
          {formatDateTime(f.createdAt)}
        </span>
      ),
    },
    {
      key: 'trace',
      header: '',
      render: (f) => (
        <button
          type="button"
          className="btn btn--ghost btn--sm"
          title="Open the evidence-graph trace for this finding"
          onClick={(e) => {
            e.stopPropagation();
            setTraceFinding(f);
          }}
        >
          Trace
        </button>
      ),
    },
  ];

  return (
    <>
      <Card>
        <CardHead
          title={`Engine findings${findings.length ? ` (${query.data.total})` : ''}`}
          subtitle="From each inspection's latest evaluation — superseded runs never re-queue"
        />
        <CardBody flush>
          {findings.length === 0 ? (
            <div style={{ padding: 'var(--space-6)' }}>
              <EmptyState
                icon="check"
                title="Queue clear"
                message="No engine findings are awaiting a decision. Run an evaluation from an inspection workspace."
              />
            </div>
          ) : (
            <DataTable
              columns={columns}
              rows={findings}
              getRowId={(f) => f.id}
              ariaLabel="Engine review queue"
              onRowClick={(f) => navigate(`/inspections/${f.inspectionId}`)}
            />
          )}
        </CardBody>
      </Card>
      <p style={{ fontSize: 'var(--fs-sm)', color: 'var(--text-faint)' }}>
        Queued statuses: Non-Compliant, Review Required, Not Detected and Not Evaluated — COMPLIANT
        and Not Applicable findings are informational and never queued. Each row shows both verdicts
        separately: the system finding (AI) and the inspector's review state (human). Compliance
        findings are system-generated decision-support outputs; they are not, by themselves, legal
        enforcement determinations. LegalMet AI provides AI-assisted inspection analysis and
        traceability — the authorized inspector remains responsible for the final inspection decision.
      </p>

      {traceFinding && (
        <Drawer
          wide
          title={traceFinding.provenance?.requirementCode ?? 'Finding trace'}
          subtitle="Evidence graph — read-only traceability, not a compliance determination"
          onClose={() => setTraceFinding(null)}
        >
          <EvidenceTracePanel
            loader={evidenceLoaders.finding(traceFinding.id)}
            inspectionId={traceFinding.inspectionId}
          />
        </Drawer>
      )}
    </>
  );
}
