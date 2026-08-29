/**
 * Evidence trace card (Prompt 7) — the Workspace entry point to traceability.
 *
 * Appears once an inspection has a compliance evaluation. Opening it loads the
 * inspection's FULL evidence graph (every image, region, OCR line, field,
 * requirement, rule and finding of the traced evaluation) and renders the
 * EvidenceTracePanel: WHY chain, graph view, node details, image evidence.
 *
 * The card and drawer are read-only — the graph is a traceability
 * representation, not a compliance decision.
 */
import { useState } from 'react';

import { Card, CardBody, CardHead } from '../components/Card';
import { Drawer } from '../components/Drawer';
import { Icon } from '../components/Icon';
import { EvidenceTracePanel } from './EvidenceTracePanel';
import { evidenceLoaders } from './useEvidenceGraph';

export function EvidenceTraceCard({
  inspectionId,
  evaluationId,
  hasEvaluation,
}: {
  inspectionId: string;
  /** Latest evaluation id (the graph defaults to it server-side when omitted). */
  evaluationId?: string | null;
  hasEvaluation: boolean;
}) {
  const [open, setOpen] = useState(false);

  if (!hasEvaluation) return null;

  return (
    <>
      <Card>
        <CardHead
          eyebrow="Traceability"
          title="Evidence graph"
          subtitle="The full chain: image → OCR → field → requirement → rule → finding"
          actions={
            <button
              type="button"
              className="btn btn--subtle btn--sm"
              onClick={() => setOpen(true)}
            >
              <Icon name="evidence" size={15} />
              View trace
            </button>
          }
        />
        <CardBody>
          <p style={{ margin: 0, color: 'var(--text-muted)', fontSize: 'var(--fs-sm)' }}>
            Every conclusion in this workspace can be traced end-to-end: from the pixels the
            inspector captured, through the OCR lines and extracted declarations the system
            perceived, to the requirement in force and the deterministic rule that produced each
            finding — in both directions.
          </p>
        </CardBody>
      </Card>

      {open && (
        <Drawer
          wide
          title="Evidence trace"
          subtitle="Read-only traceability — the graph does not determine compliance"
          onClose={() => setOpen(false)}
        >
          <EvidenceTracePanel
            loader={evidenceLoaders.inspection(inspectionId, evaluationId ?? undefined)}
            inspectionId={inspectionId}
          />
        </Drawer>
      )}
    </>
  );
}
