/**
 * Declaration evidence drawer (Prompt 4).
 *
 * Opens when an inspector clicks a perceived declaration. Shows the full
 * evidence chain for that single field:
 *
 *   FIELD → RAW OCR TEXT (verbatim) → REGION → OCR CONFIDENCE → PROCESSING
 *   RUN (reference, pipeline version, models) → extraction method
 *
 * Deliberately does NOT show any compliance interpretation: the drawer ends
 * with the "awaiting regulatory evaluation" note, because whether a detected
 * declaration satisfies the Legal Metrology rules is decided later, by the
 * regulatory layer — never here.
 */
import { FIELD_TYPE_LABELS } from '@legalmet/config';

import type { ExtractedField, ImageRegion, OcrTextResult, ProcessingRun } from '@legalmet/types';

import { ConfidenceMeter, ExtractionStatusBadge } from '../components/Badge';
import { Drawer } from '../components/Drawer';
import { Icon } from '../components/Icon';
import { formatDateTime, formatDurationMs } from '../lib/format';

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="detail-list__row">
      <span className="detail-list__key">{label}</span>
      <span className="detail-list__val">{children}</span>
    </div>
  );
}

export function FieldEvidenceDrawer({
  field,
  ocrLine,
  region,
  run,
  onClose,
}: {
  field: ExtractedField;
  ocrLine?: OcrTextResult | null;
  region?: ImageRegion | null;
  run?: ProcessingRun | null;
  onClose: () => void;
}) {
  return (
    <Drawer wide title={FIELD_TYPE_LABELS[field.fieldType]} subtitle="Perception evidence" onClose={onClose}>
      <div className="stack">
        <div className="row row--wrap">
          <ExtractionStatusBadge status={field.status} />
          <ConfidenceMeter value={field.confidence} />
        </div>

        <p className="demo-note demo-note--block" style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}>
          <Icon name="info" size={15} />
          <span>
            This is <strong>perception evidence only</strong>. The value below is what the OCR +
            extraction pipeline believes it saw on the package — it says nothing about whether the
            declaration is legally required, sufficient or correct. <strong>Awaiting regulatory
            evaluation.</strong>
          </span>
        </p>

        <section className="stack stack--sm">
          <div className="eyebrow">Detected information</div>
          <div className="detail-list">
            <Row label="Field">
              {FIELD_TYPE_LABELS[field.fieldType]}
            </Row>
            <Row label="Extracted value">
              <span style={{ fontFamily: 'var(--font-mono)' }}>
                {field.normalizedValue ?? '— (no usable value read)'}
              </span>
            </Row>
            {field.unit && (
              <Row label="Unit">{field.unit}</Row>
            )}
            <Row label="Raw OCR text (verbatim)">
              <span style={{ fontFamily: 'var(--font-mono)' }}>“{field.rawText}”</span>
            </Row>
            <Row label="Source">Real OCR — {field.extractionMethod}</Row>
            <Row label="OCR confidence">
              {ocrLine ? `${(ocrLine.confidence * 100).toFixed(1)}%` : '—'}
              <span style={{ color: 'var(--text-faint)' }}> (recognition score — not legal confidence)</span>
            </Row>
            <Row label="Extracted at">{formatDateTime(field.createdAt)}</Row>
          </div>
        </section>

        <section className="stack stack--sm">
          <div className="eyebrow">Evidence region</div>
          {ocrLine ? (
            <div className="detail-list">
              <Row label="Region type">{region ? region.regionType : 'TEXT_LINE'}</Row>
              <Row label="Bounding box">
                <span style={{ fontFamily: 'var(--font-mono)' }}>
                  x {(ocrLine.bbox.x * 100).toFixed(1)}% · y {(ocrLine.bbox.y * 100).toFixed(1)}% · w{' '}
                  {(ocrLine.bbox.width * 100).toFixed(1)}% · h {(ocrLine.bbox.height * 100).toFixed(1)}%
                </span>
              </Row>
              <Row label="Normalized text">{ocrLine.normalizedText ?? '—'}</Row>
              {ocrLine.language && <Row label="Language tag">{ocrLine.language}</Row>}
            </div>
          ) : (
            <p style={{ color: 'var(--text-muted)' }}>No OCR line is linked to this field.</p>
          )}
        </section>

        <section className="stack stack--sm">
          <div className="eyebrow">Processing run</div>
          {run ? (
            <div className="detail-list">
              <Row label="Run reference">
                <span style={{ fontFamily: 'var(--font-mono)' }}>{run.reference}</span>
              </Row>
              <Row label="Status">{run.status}</Row>
              <Row label="Pipeline version">{run.pipelineVersion}</Row>
              <Row label="OCR model">
                {run.ocrProvider} / {run.ocrModel} ({run.ocrVersion})
              </Row>
              {run.visionModel && (
                <Row label="Vision model">
                  {run.visionProvider} / {run.visionModel} ({run.visionVersion})
                </Row>
              )}
              {run.durationMs != null && <Row label="Duration">{formatDurationMs(run.durationMs)}</Row>}
              <Row label="Started">{formatDateTime(run.startedAt)}</Row>
            </div>
          ) : (
            <p style={{ color: 'var(--text-muted)' }}>Run details unavailable.</p>
          )}
        </section>
      </div>
    </Drawer>
  );
}
