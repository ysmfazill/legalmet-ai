import { useState } from 'react';

import { Badge } from '../components/Badge';
import { Card, CardBody, CardHead } from '../components/Card';
import { Icon } from '../components/Icon';

/**
 * EVIDENCE PLANNER — the flagship "what would make this provable" panel.
 *
 * AI perception can read a DECLARED value; it can never MEASURE physical
 * contents. This component makes that boundary explicit and actionable:
 *
 *   EVIDENCE STATUS   — Complete / Incomplete, per declaration
 *   WHAT IS KNOWN     — the declared (read) value
 *   WHAT IS NOT VERIFIED — the physical/measured fact still missing
 *   REQUIRED NEXT STEP — the concrete inspector action that closes the gap
 *
 * A verified-scale integration (future) fills MEASURED values with instrument
 * ID, verification status, timestamp, operator and inspection reference.
 * Until then every measured row reads NOT VERIFIED — honestly.
 */

export type EvidenceGapKind =
  | 'PHYSICAL_MEASUREMENT'
  | 'PHOTO'
  | 'DOCUMENT'
  | 'INSPECTOR_OBSERVATION';

const GAP_META: Record<EvidenceGapKind, { label: string; icon: 'scale' | 'camera' | 'regulations' | 'eye' }> = {
  PHYSICAL_MEASUREMENT: { label: 'Physical measurement', icon: 'scale' },
  PHOTO: { label: 'Photo required', icon: 'camera' },
  DOCUMENT: { label: 'Document required', icon: 'regulations' },
  INSPECTOR_OBSERVATION: { label: 'Inspector observation', icon: 'eye' },
};

export interface EvidencePlanRow {
  /** Declaration the plan refers to (e.g. Net quantity). */
  declaration: string;
  /** Value read from the label by OCR — DECLARED, never measured. */
  declaredValue: string | null;
  /** Measured value from a verified instrument — null until integrated. */
  measuredValue: string | null;
  /** Confidence of the OCR reading itself (0..1). */
  confidence: number | null;
  /** The missing evidence kinds, in the order they should be collected. */
  gaps: EvidenceGapKind[];
}

function GapChip({ kind }: { kind: EvidenceGapKind }) {
  const meta = GAP_META[kind];
  return (
    <span className="chip" title={`${meta.label} — collected by the inspector, not by the system`}>
      <Icon name={meta.icon} size={12} />
      {meta.label}
    </span>
  );
}

function PlanRow({ row, onStart }: { row: EvidencePlanRow; onStart: (row: EvidencePlanRow) => void }) {
  const complete = row.gaps.length === 0;
  const primaryGap = row.gaps[0];

  return (
    <div className="eplan__row">
      <div className="eplan__row-head">
        <span className="eplan__declaration">{row.declaration}</span>
        {complete ? (
          <Badge tone="positive" dot title="Declared value read and no open evidence gap">
            Complete
          </Badge>
        ) : (
          <Badge tone="warning" dot title="A required piece of evidence is still missing — the system cannot conclude">
            Incomplete
          </Badge>
        )}
      </div>

      <div className="eplan__values">
        <div className="eplan__value">
          <span className="eplan__value-label">Declared value</span>
          <span className="eplan__value-num">{row.declaredValue ?? 'NOT DETECTED'}</span>
          <span className="eplan__value-src">
            {row.declaredValue
              ? `Read from label · ${Math.round((row.confidence ?? 0) * 100)}% reading confidence`
              : 'No readable declaration on the label'}
          </span>
        </div>
        <div className="eplan__arrow" aria-hidden>
          <Icon name="arrowRight" size={14} />
        </div>
        <div className="eplan__value">
          <span className="eplan__value-label">Measured value</span>
          <span
            className={`eplan__value-num ${row.measuredValue ? '' : 'eplan__value-num--muted'}`}
          >
            {row.measuredValue ?? 'NOT VERIFIED'}
          </span>
          <span className="eplan__value-src">
            {row.measuredValue
              ? 'From a verified measuring instrument'
              : 'No verified instrument reading yet — the system never guesses'}
          </span>
        </div>
      </div>

      {!complete && (
        <div className="eplan__gap">
          <span className="eplan__gap-label">Required next step</span>
          <div className="row row--wrap" style={{ gap: 6 }}>
            {row.gaps.map((g) => (
              <GapChip key={g} kind={g} />
            ))}
          </div>
          <button
            type="button"
            className="btn btn--sm btn--primary"
            onClick={() => onStart(row)}
            title={`Begin collecting the ${GAP_META[primaryGap].label.toLowerCase()} evidence as the inspector`}
          >
            <Icon name={GAP_META[primaryGap].icon} size={14} />
            Start {GAP_META[primaryGap].label.toLowerCase().replace('physical ', '')}
          </button>
        </div>
      )}
    </div>
  );
}

export function EvidencePlanner({ rows }: { rows: EvidencePlanRow[] }) {
  const [started, setStarted] = useState<string | null>(null);

  function start(row: EvidencePlanRow) {
    setStarted(row.declaration);
  }

  const incomplete = rows.filter((r) => r.gaps.length > 0).length;

  return (
    <Card className="eplan">
      <CardHead
        eyebrow="Evidence planner"
        title="Evidence completeness"
        subtitle="What the system knows, what is still unverified, and what closes the gap"
        actions={
          <Badge tone={incomplete > 0 ? 'warning' : 'positive'} dot>
            {incomplete > 0 ? `${incomplete} incomplete` : 'Complete'}
          </Badge>
        }
      />
      <CardBody>
        <div className="eplan__banner" role="note">
          <Icon name="shield" size={15} />
          <span>
            <strong>AI reads declarations; it cannot measure contents.</strong> The system does not
            automatically make the final legal decision — a human inspector verifies and decides.
            Measured values arrive only from a verified measuring instrument integration.
          </span>
        </div>

        {rows.length === 0 ? (
          <p className="cell-muted" style={{ padding: 'var(--space-3) 0' }}>
            No evidence plan yet — run perception to extract declarations first.
          </p>
        ) : (
          <div className="stack">
            {rows.map((row) => (
              <PlanRow key={row.declaration} row={row} onStart={start} />
            ))}
          </div>
        )}

        {started && (
          <div className="demo-note" style={{ marginTop: 'var(--space-4)' }} role="status">
            <Icon name="info" size={15} />
            <span>
              <strong>{started}:</strong> measurement capture is a planned integration. When a
              verified scale is connected, this records the measured quantity, instrument ID,
              verification status, timestamp, operator and inspection reference. Until then the
              measured value honestly stays <strong>NOT VERIFIED</strong>.
            </span>
          </div>
        )}
      </CardBody>
    </Card>
  );
}
