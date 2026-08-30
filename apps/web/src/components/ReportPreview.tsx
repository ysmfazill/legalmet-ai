import { DEMO_DATA_LABEL, DEMO_DATA_NOTICE, FIELD_TYPE_LABELS } from '@legalmet/config';

import { formatDate } from '../lib/format';
import type { InspectionDetail } from '../mock/types';
import { Badge, StatusBadge } from './Badge';
import { Icon } from './Icon';

/**
 * Audit-report preview. Deliberately separates the AI-ASSISTED ANALYSIS from
 * the INSPECTOR'S DECISION, and carries the mandatory demo/legal disclaimer.
 */
export function ReportPreview({
  detail,
  reference,
  inspector,
  generatedAt,
  status,
}: {
  detail: InspectionDetail;
  reference: string;
  inspector: string;
  generatedAt: string;
  status: 'DRAFT' | 'FINALIZED';
}) {
  const { inspection, declarations, findings, complianceScore } = detail;
  const reviewed = findings.filter((f) => f.isReviewed).length;

  return (
    <div className="report">
      <div className="report__head">
        <div className="row row--between row--wrap">
          <div>
            <div className="eyebrow">Inspection report · {status}</div>
            <h2 style={{ fontSize: 'var(--fs-xl)', fontWeight: 700, marginTop: 4 }}>
              {inspection.product?.name ?? 'Packaged commodity'}
            </h2>
          </div>
          <Badge tone="info" square>
            {reference}
          </Badge>
        </div>
        <div className="demo-note" style={{ marginTop: 'var(--space-4)' }}>
          <Icon name="alert" size={15} />
          <span>
            <strong>{DEMO_DATA_LABEL}.</strong> {DEMO_DATA_NOTICE}
          </span>
        </div>
      </div>

      <div className="report__section">
        <div className="report__section-title">AI-assisted analysis summary</div>
        <div className="row row--wrap" style={{ gap: 'var(--space-6)' }}>
          <div>
            <div className="summary-score">
              <span className="summary-score__num">{complianceScore}</span>
              <span className="cell-muted">/ 100 assistance score</span>
            </div>
            <p style={{ fontSize: 'var(--fs-xs)', color: 'var(--text-faint)', maxWidth: '40ch' }}>
              Indicative assistance metric only — not a legal determination.
            </p>
          </div>
          <dl className="kv">
            <dt>Findings</dt>
            <dd>{findings.length} analysed</dd>
            <dt>Inspector-reviewed</dt>
            <dd>
              {reviewed} of {findings.length}
            </dd>
            <dt>Generated</dt>
            <dd>{formatDate(generatedAt)}</dd>
          </dl>
        </div>
      </div>

      <div className="report__section">
        <div className="report__section-title">Detected declarations</div>
        <div className="detail-list">
          {declarations.map((d) => (
            <div key={d.field} className="detail-list__row">
              <span className="detail-list__key">{FIELD_TYPE_LABELS[d.field]}</span>
              <span className="row" style={{ gap: 'var(--space-3)' }}>
                <span style={{ fontFamily: 'var(--font-mono)' }}>{d.value}</span>
                <StatusBadge status={d.status} dot={false} />
              </span>
            </div>
          ))}
        </div>
      </div>

      <div className="report__section">
        <div className="report__section-title">Findings & applicable requirements</div>
        <div className="stack stack--sm">
          {findings.map((f) => (
            <div key={f.id} className="row row--between row--wrap" style={{ gap: 'var(--space-3)' }}>
              <span>
                {f.title}
                {f.rule && <span className="tag" style={{ marginLeft: 8 }}>{f.rule.code}</span>}
              </span>
              <StatusBadge status={f.status} />
            </div>
          ))}
        </div>
      </div>

      <div className="report__section" style={{ borderBottom: 'none' }}>
        <div className="report__section-title">Inspector decision (human record)</div>
        <div className="demo-note demo-note--block">
          <Icon name="shield" size={15} />
          <span>
            <strong>AI-assisted analysis, human decision.</strong> The analysis above was produced
            by the deterministic engine; this decision was recorded by the authorised inspector.
            METRASIGHT provides AI-assisted inspection analysis and traceability — the authorized
            inspector remains responsible for the final inspection decision. Prepared by{' '}
            <strong>{inspector}</strong>.
            {status === 'DRAFT' ? ' Awaiting inspector sign-off.' : ' Signed off by inspector.'}
          </span>
        </div>
      </div>
    </div>
  );
}
