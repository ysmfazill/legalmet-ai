/**
 * Declaration evidence drawer (Prompts 4 + 5).
 *
 * Opens when an inspector clicks a perceived declaration. Shows the full
 * evidence chain for that single field:
 *
 *   FIELD → RAW OCR TEXT (verbatim) → REGION → OCR CONFIDENCE → PROCESSING
 *   RUN (reference, pipeline version, models) → extraction method
 *   → CANDIDATE REQUIREMENTS (Prompt 5)
 *
 * Deliberately does NOT show any compliance interpretation: candidate
 * requirements are definitions whose field key matches this detected field —
 * applicability is not evaluated and no compliance conclusion exists here.
 * That decision belongs to the compliance engine, never to this drawer.
 */
import { FIELD_TYPE_LABELS } from '@legalmet/config';

import type { ExtractedField, ImageRegion, OcrTextResult, ProcessingRun } from '@legalmet/types';

import { api } from '../api/client';
import { ConfidenceMeter, ExtractionStatusBadge, VerificationBadge } from '../components/Badge';
import { Drawer } from '../components/Drawer';
import { Icon } from '../components/Icon';
import { EvidenceTracePanel } from '../evidence/EvidenceTracePanel';
import { evidenceLoaders } from '../evidence/useEvidenceGraph';
import { useAsync } from '../data/useAsync';
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
  inspectionId,
  onClose,
}: {
  field: ExtractedField;
  ocrLine?: OcrTextResult | null;
  region?: ImageRegion | null;
  run?: ProcessingRun | null;
  /** Needed to resolve candidate requirements (Prompt 5). */
  inspectionId?: string;
  onClose: () => void;
}) {
  // Candidate requirements for the whole inspection; this drawer filters to
  // the selected field. Failure is non-fatal — the perception evidence above
  // is still fully usable without it.
  const candidatesQuery = useAsync(
    () => (inspectionId ? api.getFieldCandidates(inspectionId) : Promise.resolve(null)),
    [inspectionId],
  );
  const fieldCandidate =
    candidatesQuery.status === 'success'
      ? (candidatesQuery.data?.fields.find((f) => f.fieldId === field.id) ?? null)
      : null;
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
            {field.correctedValue != null && field.correctedValue !== '' ? (
              <>
                <Row label="Current value (human correction)">
                  <span style={{ fontFamily: 'var(--font-mono)' }}>{field.correctedValue}</span>{' '}
                  <span className="tag" title="Corrected by an authorized inspector">
                    HUMAN
                  </span>
                </Row>
                <Row label="AI-extracted value (preserved)">
                  <span style={{ fontFamily: 'var(--font-mono)' }}>
                    {field.normalizedValue ?? '— (no usable value read)'}
                  </span>{' '}
                  <span className="tag" title="Original pipeline output — never overwritten">
                    AI
                  </span>
                </Row>
                {field.correctedAt && <Row label="Corrected at">{formatDateTime(field.correctedAt)}</Row>}
              </>
            ) : (
              <Row label="Extracted value">
                <span style={{ fontFamily: 'var(--font-mono)' }}>
                  {field.normalizedValue ?? '— (no usable value read)'}
                </span>{' '}
                <span className="tag" title="Original pipeline output — not yet reviewed">
                  AI
                </span>
              </Row>
            )}
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

        <section className="stack stack--sm">
          <div className="eyebrow">Candidate requirements (regulatory)</div>
          {candidatesQuery.status === 'loading' && (
            <p style={{ color: 'var(--text-muted)' }}>Resolving candidate requirements…</p>
          )}
          {candidatesQuery.status === 'error' && (
            <p style={{ color: 'var(--text-muted)' }}>
              Candidate requirements unavailable ({candidatesQuery.error.message}).
            </p>
          )}
          {fieldCandidate && fieldCandidate.candidates.length > 0 && (
            <div className="stack stack--sm">
              {fieldCandidate.candidates.map((cand) => (
                <div
                  key={cand.requirementId}
                  className="detail-list"
                  style={{ paddingLeft: 'var(--space-3)', borderLeft: '2px solid var(--border)' }}
                >
                  <Row label="Requirement">
                    <span className="tag" style={{ marginRight: 8 }}>
                      {cand.ruleCode}
                    </span>
                    {cand.title}
                  </Row>
                  <Row label="Version in force">{cand.versionLabel}</Row>
                  {cand.effectiveFrom && <Row label="Effective from">{cand.effectiveFrom}</Row>}
                  {cand.sourceReference && (
                    <Row label="Source reference">
                      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--fs-sm)' }}>
                        {cand.sourceReference}
                      </span>
                    </Row>
                  )}
                  {cand.sourceVerificationStatus && (
                    <Row label="Source status">
                      <VerificationBadge status={cand.sourceVerificationStatus} />
                    </Row>
                  )}
                </div>
              ))}
              <p style={{ fontSize: 'var(--fs-sm)', color: 'var(--text-faint)' }}>
                <strong>Candidate association only.</strong> Whether each requirement applies to
                this package has not been evaluated, and no compliance conclusion exists — the
                compliance engine makes that decision.
              </p>
            </div>
          )}
          {fieldCandidate && fieldCandidate.candidates.length === 0 && (
            <p style={{ color: 'var(--text-muted)' }}>
              No requirement definition in force at this inspection's context date maps to this
              field type. This is an absence of a definition — not a statement of compliance.
            </p>
          )}
          {candidatesQuery.status === 'success' && !fieldCandidate && (
            <p style={{ color: 'var(--text-muted)' }}>
              This field is not part of the latest perception run's candidate mapping.
            </p>
          )}
          {!inspectionId && (
            <p style={{ color: 'var(--text-muted)' }}>
              Inspection context unavailable — candidate requirements cannot be resolved.
            </p>
          )}
        </section>

        {inspectionId && (
          <section className="stack stack--sm">
            <div className="eyebrow">Reverse trace (evidence graph)</div>
            <p style={{ margin: 0, fontSize: 'var(--fs-sm)', color: 'var(--text-muted)' }}>
              Every finding that used this field as evidence, traced back through the requirement,
              the version in force and the publishing source — the reverse direction of the
              compliance chain.
            </p>
            <EvidenceTracePanel
              loader={evidenceLoaders.field(field.id)}
              inspectionId={inspectionId}
            />
          </section>
        )}
      </div>
    </Drawer>
  );
}
