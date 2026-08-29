/**
 * Node detail panel (Prompt 7, Phase 10).
 *
 * Renders the whitelisted metadata of ONE traceability node, laid out per node
 * type. Everything shown here is exactly what the backend emitted — the panel
 * adds no interpretation of its own beyond labels, and it never offers a
 * compliance action (the graph is read-only traceability).
 */
import {
  EVIDENCE_GRAPH_NODE_META,
  EVIDENCE_STRENGTH_META,
  FIELD_TYPE_LABELS,
} from '@legalmet/config';

import type { Json, TraceEdge, TraceNode } from '@legalmet/types';
import type { EvidenceStrength } from '@legalmet/types';

import { Badge } from '../components/Badge';
import { Icon } from '../components/Icon';
import { formatDateTime, formatDurationMs, humanizeEnum } from '../lib/format';

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="detail-list__row">
      <span className="detail-list__key">{label}</span>
      <span className="detail-list__val">{children}</span>
    </div>
  );
}

function JsonValue({ value }: { value: Json }) {
  if (value === null) return <span style={{ color: 'var(--text-faint)' }}>—</span>;
  if (typeof value === 'boolean') return <>{String(value)}</>;
  if (typeof value === 'object') {
    return (
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--fs-sm)' }}>
        {JSON.stringify(value)}
      </span>
    );
  }
  return <>{String(value)}</>;
}

function monospace(children: React.ReactNode) {
  return <span style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--fs-sm)' }}>{children}</span>;
}

/** Metadata rows per node type — the per-type Phase 10 views. */
function metadataRows(node: TraceNode): Array<[string, React.ReactNode]> {
  const m = (node.metadata ?? {}) as Record<string, Json>;
  const rows: Array<[string, React.ReactNode]> = [];
  const push = (label: string, key: string, render?: (v: Json) => React.ReactNode) => {
    if (m[key] === undefined || m[key] === null) return;
    rows.push([label, render ? render(m[key]) : <JsonValue value={m[key]} />]);
  };

  switch (node.type) {
    case 'INSPECTION':
      push('Reference no.', 'referenceNo');
      push('Status', 'status', (v) => humanizeEnum(String(v)));
      push('Context date', 'contextDate', (v) => formatDateTime(String(v)));
      push('Created', 'createdAt', (v) => formatDateTime(String(v)));
      push('Demo data', 'isDemo');
      break;
    case 'IMAGE':
      push('Filename', 'filename');
      push('Image type', 'imageType', (v) => humanizeEnum(String(v)));
      push('Capture source', 'captureSource', (v) => humanizeEnum(String(v)));
      push('Processing', 'processingStatus', (v) => humanizeEnum(String(v)));
      push('Quality grade', 'qualityGrade', (v) => humanizeEnum(String(v)));
      push('Resolution', 'width', (v) => `${v} × ${m.height ?? '?'} px`);
      push('Checksum (truncated)', 'checksum');
      push('Captured', 'createdAt', (v) => formatDateTime(String(v)));
      break;
    case 'IMAGE_REGION':
      push('Region type', 'regionType', (v) => humanizeEnum(String(v)));
      push('Confidence', 'confidence', (v) => `${(Number(v) * 100).toFixed(1)}%`);
      push('Payload', 'payload');
      break;
    case 'OCR_RESULT':
      push('Raw text (verbatim)', 'rawText', (v) => monospace(`“${String(v)}”`));
      push('Normalized text', 'normalizedText');
      push('OCR confidence', 'confidence', (v) =>
        `${(Number(v) * 100).toFixed(1)}% (recognition score — not legal confidence)`,
      );
      push('Language', 'language');
      push('Engine', 'modelName', (v) => `${m.provider ?? '?'} / ${v} (${m.modelVersion ?? '?'})`);
      break;
    case 'EXTRACTED_FIELD':
      push('Field', 'fieldType', (v) => FIELD_TYPE_LABELS[String(v) as keyof typeof FIELD_TYPE_LABELS] ?? String(v));
      push('Extracted value', 'normalizedValue', (v) => monospace(String(v) || '— (no usable value)'));
      push('Raw OCR text (verbatim)', 'rawText', (v) => monospace(`“${String(v)}”`));
      push('Unit', 'unit');
      push('Perception status', 'status', (v) => humanizeEnum(String(v)));
      push('Confidence', 'confidence', (v) => `${(Number(v) * 100).toFixed(1)}%`);
      push('Extraction method', 'extractionMethod');
      push('Extracted', 'createdAt', (v) => formatDateTime(String(v)));
      break;
    case 'REGULATORY_SOURCE':
      push('Authority', 'authority');
      push('Source type', 'sourceType', (v) => humanizeEnum(String(v)));
      push('Jurisdiction', 'jurisdiction');
      push('Verification status', 'verificationStatus', (v) => humanizeEnum(String(v)));
      push('Canonical URL', 'canonicalUrl', (v) => (
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--fs-sm)', overflowWrap: 'anywhere' }}>
          {String(v)}
        </span>
      ));
      break;
    case 'REGULATORY_DOCUMENT':
      push('Code', 'code');
      push('Title', 'title');
      push('Identifier', 'documentIdentifier');
      push('Document type', 'documentType', (v) => humanizeEnum(String(v)));
      push('Publication date', 'publicationDate', (v) => formatDateTime(String(v)));
      push('Official source URL', 'officialSourceUrl', (v) => (
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--fs-sm)', overflowWrap: 'anywhere' }}>
          {String(v)}
        </span>
      ));
      push('Demo data', 'isDemo');
      break;
    case 'REGULATORY_VERSION':
      push('Version label', 'versionLabel');
      push('Status', 'status', (v) => humanizeEnum(String(v)));
      push('Effective from', 'effectiveFrom', (v) => formatDateTime(String(v)));
      push('Effective until', 'effectiveUntil', (v) => formatDateTime(String(v)));
      push('Publication date', 'publicationDate', (v) => formatDateTime(String(v)));
      push('Demo data', 'isDemo');
      break;
    case 'REQUIREMENT':
      push('Code', 'ruleCode');
      push('Title', 'title');
      push('Summary', 'requirementSummary');
      push('Requirement type', 'requirementType', (v) => humanizeEnum(String(v)));
      push('Field key', 'fieldKey');
      push('Mandatory', 'mandatory');
      push('Source reference', 'sourceReference', (v) => monospace(String(v)));
      push('Demo data', 'isDemo');
      break;
    case 'RULE':
      push('Rule code', 'ruleCode', (v) => monospace(String(v)));
      push('Rule type', 'ruleType', (v) => humanizeEnum(String(v)));
      push('Rule version', 'ruleVersion');
      push('Active', 'active');
      push('Description', 'description');
      break;
    case 'EVALUATION':
      push('Status', 'status', (v) => humanizeEnum(String(v)));
      push('Engine version', 'engineVersion');
      push('Context date', 'contextDate', (v) => formatDateTime(String(v)));
      push('Started', 'startedAt', (v) => formatDateTime(String(v)));
      push('Completed', 'completedAt', (v) => formatDateTime(String(v)));
      push('Summary (counts only)', 'summary', (v) => monospace(JSON.stringify(v)));
      break;
    case 'FINDING':
      push('Status', 'status', (v) => humanizeEnum(String(v)));
      push('Severity', 'severity', (v) => humanizeEnum(String(v)));
      push('Applicability', 'applicability', (v) => humanizeEnum(String(v)));
      push('Detected value', 'detectedValue', (v) => monospace(String(v)));
      push('Expected value', 'expectedValue', (v) => monospace(String(v)));
      push('Explanation', 'explanation');
      push('Absence marker', 'absence');
      push('Evaluated', 'createdAt', (v) => formatDateTime(String(v)));
      break;
    case 'PROCESSING_RUN':
      push('Run reference', 'reference', (v) => monospace(String(v)));
      push('Status', 'status', (v) => humanizeEnum(String(v)));
      push('Pipeline version', 'pipelineVersion');
      push('OCR model', 'modelName', (v) => `${m.ocrProvider ?? '?'} / ${v} (${m.ocrVersion ?? '?'})`);
      push('Vision model', 'visionModel', (v) => `${m.visionProvider ?? '?'} / ${v} (${m.visionVersion ?? '?'})`);
      push('Duration', 'durationMs', (v) => formatDurationMs(Number(v)));
      push('Started', 'startedAt', (v) => formatDateTime(String(v)));
      push('Completed', 'completedAt', (v) => formatDateTime(String(v)));
      break;
    case 'AUDIT_EVENT':
      push('Event type', 'eventType', (v) => humanizeEnum(String(v)));
      push('Entity', 'entityType');
      push('Recorded', 'createdAt', (v) => formatDateTime(String(v)));
      push('Payload', 'payload', (v) => monospace(JSON.stringify(v)));
      break;
  }
  return rows;
}

export function NodeDetailPanel({
  node,
  edges,
}: {
  node: TraceNode;
  /** Edges touching this node — its real relationships. */
  edges: TraceEdge[];
}) {
  const meta = EVIDENCE_GRAPH_NODE_META[node.type];
  const rows = metadataRows(node);
  const strength = (node.metadata as Record<string, Json> | null | undefined)?.evidenceStrength;
  const strengthMeta =
    typeof strength === 'string' ? EVIDENCE_STRENGTH_META[strength as EvidenceStrength] : undefined;

  return (
    <div className="stack stack--sm">
      <div className="row row--wrap" style={{ gap: 6 }}>
        <Badge tone={meta.tone} dot>
          {meta.label}
        </Badge>
        {strengthMeta && (
          <Badge tone={strengthMeta.tone} title={strengthMeta.description}>
            Evidence: {strengthMeta.label}
          </Badge>
        )}
      </div>

      <p style={{ margin: 0, fontSize: 'var(--fs-sm)', color: 'var(--text-muted)' }}>
        {meta.description}
      </p>

      <div className="detail-list">
        <Row label="Node id">{monospace(node.id)}</Row>
        {rows.map(([label, content]) => (
          <Row key={label} label={label}>
            {content}
          </Row>
        ))}
      </div>

      <section className="stack stack--sm">
        <div className="eyebrow">Relationships ({edges.length})</div>
        {edges.length === 0 ? (
          <p style={{ margin: 0, color: 'var(--text-muted)', fontSize: 'var(--fs-sm)' }}>
            No relationships recorded for this node.
          </p>
        ) : (
          <div className="stack stack--sm">
            {edges.map((edge) => (
              <div
                key={edge.id}
                className="detail-list"
                style={{ paddingLeft: 'var(--space-3)', borderLeft: '2px solid var(--border)' }}
              >
                <Row label="Relationship">{humanizeEnum(edge.type)}</Row>
                <Row label="From">{monospace(edge.source)}</Row>
                <Row label="To">{monospace(edge.target)}</Row>
                {edge.metadata && edge.metadata.evidenceStrength && (
                  <Row label="Evidence strength">
                    {String(edge.metadata.evidenceStrength)}
                  </Row>
                )}
              </div>
            ))}
          </div>
        )}
      </section>

      {node.type === 'FINDING' && (
        <p className="demo-note demo-note--block" style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}>
          <Icon name="info" size={15} />
          <span>
            A system-generated decision-support output — not an enforcement determination.
          </span>
        </p>
      )}
    </div>
  );
}
