/**
 * Physical verification — measurement history card (UI-07, §14).
 *
 * Every measurement recorded for this inspection, from the append-only
 * server history. Columns are real persisted fields only:
 *
 *   ID · DECLARED · MEASURED · UNIT · INSTRUMENT · INSPECTOR · TIMESTAMP · STATUS
 *
 * Honesty contracts:
 *
 * - DECLARED and MEASURED are shown separately and never merged; the declared
 *   quantity is immutable once read from the label.
 * - The difference shown per row is the OBSERVED difference (arithmetic on
 *   normalized values) — never a legal deficiency.
 * - The status column is the frozen regulatory evaluation when one exists,
 *   and "Evaluation unavailable — inspector review" when it does not. The
 *   system never invents a tolerance.
 * - Instrument verification status is only shown when it was recorded; the
 *   panel never displays "verified" for an instrument whose status is absent.
 * - History is append-only: a correction is a NEW measurement with an audit
 *   event, never a silent edit — which is why this list only ever grows.
 */
import { useState } from 'react';

import type { MeasurementHistoryRow } from '@legalmet/types';

import { api } from '../api/client';
import { Badge } from '../components/Badge';
import { Card, CardBody, CardHead } from '../components/Card';
import { DataTable, type Column } from '../components/DataTable';
import { Drawer } from '../components/Drawer';
import { Icon } from '../components/Icon';
import { useAsync } from '../data/useAsync';
import { formatDateTime } from '../lib/format';
import { EvaluationBadge, EvaluationNote, ObservedDifferenceNote } from './ObservedEvaluation';

function anchorLabel(row: MeasurementHistoryRow): string {
  if (row.anchor.kind === 'LOT_PACKAGE') return 'lot package';
  if (row.anchor.kind === 'FINDING') return 'finding';
  return 'declaration';
}

function HistoryRowDrawer({
  row,
  onClose,
}: {
  row: MeasurementHistoryRow;
  onClose: () => void;
}) {
  return (
    <Drawer title={`Measurement ${row.measurementId.slice(0, 8)}…`} subtitle={anchorLabel(row)} onClose={onClose}>
      <div className="stack">
        <div className="detail-list">
          <div className="detail-list__row">
            <span className="detail-list__key">Declared value</span>
            <span className="detail-list__val">{row.declaredValue ?? 'NOT RECORDED'}</span>
          </div>
          <div className="detail-list__row">
            <span className="detail-list__key">Measured value</span>
            <span className="detail-list__val">
              {row.measuredValue != null
                ? `${row.measuredValue} ${row.unit ?? ''}`.trim()
                : 'NOT RECORDED'}
            </span>
          </div>
          <div className="detail-list__row">
            <span className="detail-list__key">Instrument</span>
            <span className="detail-list__val">
              {row.instrumentId ?? 'Not recorded'}
              {row.instrumentId
                ? row.instrumentVerificationStatus
                  ? ` · verification status: ${row.instrumentVerificationStatus}`
                  : ' · verification status NOT RECORDED'
                : ''}
            </span>
          </div>
          <div className="detail-list__row">
            <span className="detail-list__key">Recorded by</span>
            <span className="detail-list__val">
              {row.recordedByName ?? row.recordedBy.slice(0, 8) + '…'} · {formatDateTime(row.recordedAt)}
            </span>
          </div>
          <div className="detail-list__row">
            <span className="detail-list__key">Verification task</span>
            <span className="detail-list__val">
              {row.taskId.slice(0, 8)}… · {row.taskStatus.replace('_', ' ')}
            </span>
          </div>
          {row.observation && (
            <div className="detail-list__row">
              <span className="detail-list__key">Observation</span>
              <span className="detail-list__val">{row.observation}</span>
            </div>
          )}
          {row.notes && (
            <div className="detail-list__row">
              <span className="detail-list__key">Notes</span>
              <span className="detail-list__val">{row.notes}</span>
            </div>
          )}
        </div>

        <ObservedDifferenceNote observed={row.observed ?? null} />
        <EvaluationNote evaluation={row.evaluation ?? null} />

        <p className="cell-muted" style={{ margin: 0, fontSize: 'var(--fs-xs)' }}>
          History is append-only — this record is never edited in place. A correction is a new
          measurement with an audit event.
        </p>
      </div>
    </Drawer>
  );
}

export function PhysicalVerificationCard({
  inspectionId,
  enabled,
  refreshKey,
}: {
  inspectionId: string;
  enabled: boolean;
  /** Bumped by the workspace after any verification write, so the history reloads. */
  refreshKey: number;
}) {
  const [openId, setOpenId] = useState<string | null>(null);

  const history = useAsync(
    () => (enabled ? api.getMeasurementHistory(inspectionId) : Promise.resolve(null)),
    [inspectionId, enabled, refreshKey],
  );

  const rows = history.data?.measurements ?? [];
  const openRow = openId ? (rows.find((r) => r.measurementId === openId) ?? null) : null;
  const columns: Column<MeasurementHistoryRow>[] = [
    {
      key: 'id',
      header: 'Measurement',
      render: (r) => <span className="cell-strong">{r.measurementId.slice(0, 8)}…</span>,
    },
    {
      key: 'anchor',
      header: 'Anchor',
      render: (r) => <span className="cell-muted">{anchorLabel(r)}</span>,
    },
    {
      key: 'declared',
      header: 'Declared',
      render: (r) => r.declaredValue ?? '—',
    },
    {
      key: 'measured',
      header: 'Measured',
      render: (r) =>
        r.measuredValue != null ? (
          <span className="cell-strong">{`${r.measuredValue} ${r.unit ?? ''}`.trim()}</span>
        ) : (
          '—'
        ),
    },
    {
      key: 'observed',
      header: 'Observed difference',
      render: (r) => {
        const observed = r.observed;
        if (!observed) return '—';
        if (!observed.comparable) return <span className="cell-muted" title={observed.reason ?? ''}>not comparable</span>;
        const unit = observed.declared?.unit ?? '';
        return (
          <span>
            {observed.difference}
            {unit ? ` ${unit}` : ''}
            {observed.percentDifference != null ? (
              <span className="cell-muted"> ({observed.percentDifference}%)</span>
            ) : null}
          </span>
        );
      },
    },
    {
      key: 'instrument',
      header: 'Instrument',
      render: (r) => (
        <span title={r.instrumentVerificationStatus ? `Verification status: ${r.instrumentVerificationStatus}` : 'Instrument verification status not recorded'}>
          {r.instrumentId ?? <span className="cell-muted">not recorded</span>}
        </span>
      ),
    },
    {
      key: 'inspector',
      header: 'Inspector',
      render: (r) => r.recordedByName ?? r.recordedBy.slice(0, 8) + '…',
    },
    {
      key: 'recordedAt',
      header: 'Recorded',
      render: (r) => <span className="cell-muted">{formatDateTime(r.recordedAt)}</span>,
    },
    {
      key: 'status',
      header: 'Status',
      render: (r) =>
        r.evaluation ? (
          <EvaluationBadge evaluation={r.evaluation} />
        ) : (
          <Badge tone="neutral" outline>
            {r.taskStatus.replace('_', ' ')}
          </Badge>
        ),
    },
  ];

  // Mirrors the planner: the physical-verification layer appears only once
  // perception data exists for this inspection.
  if (!enabled) return null;

  return (
    <>
      <Card className="pvcard">
        <CardHead
          eyebrow="Physical verification"
          title="Measurement history"
          subtitle="Every recorded measurement — append-only, with its frozen regulatory evaluation"
          actions={
            <Badge tone={rows.length > 0 ? 'info' : 'neutral'} dot>
              {rows.length} recorded
            </Badge>
          }
        />
        <CardBody>
          <div className="eplan__banner" role="note">
            <Icon name="scale" size={15} />
            <span>
              <strong>OCR reads declarations; only an inspector measures contents.</strong> Each row
              below is a manual entry by an authorised inspector. The declared quantity is never
              overwritten, corrections are new audited measurements, and an absent evaluation means
              the applicable rule was not configured — never a guessed tolerance.
            </span>
          </div>

          {history.status === 'error' && history.error && (
            <div className="demo-note demo-note--error" style={{ display: 'flex', gap: 8 }} role="alert">
              <Icon name="alert" size={15} />
              <span>Could not load the measurement history: {history.error.message}</span>
            </div>
          )}

          {history.status === 'loading' ? (
            <p className="cell-muted" style={{ padding: 'var(--space-3) 0' }}>
              Loading measurement history…
            </p>
          ) : rows.length === 0 ? (
            <p className="cell-muted" style={{ padding: 'var(--space-3) 0' }}>
              No measurements recorded yet — start a measurement verification from the evidence
              planner above. Only an inspector can record one.
            </p>
          ) : (
            <DataTable
              columns={columns}
              rows={rows}
              getRowId={(r) => r.measurementId}
              onRowClick={(r) => setOpenId(r.measurementId)}
              ariaLabel="Measurement history for this inspection"
            />
          )}
        </CardBody>
      </Card>

      {openRow && <HistoryRowDrawer row={openRow} onClose={() => setOpenId(null)} />}
    </>
  );
}
