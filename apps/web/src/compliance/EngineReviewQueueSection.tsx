/**
 * Engine review queue (Prompt 6, Phase 18) — REAL backend findings.
 *
 * Lists the deterministic engine findings awaiting an inspector decision:
 * REVIEW_REQUIRED, NON_COMPLIANT, NOT_DETECTED and NOT_EVALUATED from each
 * inspection's LATEST evaluation (superseded evaluations never re-queue).
 *
 * Read-only by design: each row says "System finding — inspector decision
 * pending". This queue performs no approval or rejection — recording the
 * final enforcement decision is a later phase, and the inspector remains
 * responsible for it.
 */
import { useNavigate } from 'react-router-dom';

import type { EngineFinding } from '@legalmet/types';

import { api } from '../api/client';
import { EngineFindingBadge } from '../components/Badge';
import { Card, CardBody, CardHead } from '../components/Card';
import type { Column } from '../components/DataTable';
import { DataTable } from '../components/DataTable';
import { EmptyState } from '../components/states';
import { useAsync } from '../data/useAsync';
import { formatDateTime } from '../lib/format';

export function EngineReviewQueueSection() {
  const navigate = useNavigate();
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
        and Not Applicable findings are informational and never queued. Compliance findings are
        system-generated decision-support outputs; they are not, by themselves, legal enforcement
        determinations.
      </p>
    </>
  );
}
