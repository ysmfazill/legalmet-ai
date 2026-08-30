/**
 * Perception panel pieces for the REAL Inspection Workspace (Prompt 4).
 *
 * Three cards, none of which ever renders a compliance verdict:
 *
 * - {@link PerceptionControlCard} — start / re-run perception, live stage
 *   indicator, aggregate perception summary (counts + models + duration).
 * - {@link PerceptionDeclarationsCard} — every declaration candidate the
 *   extractor perceived, with its outcome badge (DETECTED / LOW CONFIDENCE /
 *   NOT EXTRACTED), OCR confidence and click-to-highlight evidence region.
 * - {@link PerceptionRunHistoryCard} — every processing run ever executed,
 *   newest first; reanalysis adds rows, history is never rewritten.
 */
import { EXTRACTION_STATUS_META, FIELD_TYPE_LABELS, PROCESSING_RUN_STATUS_META } from '@legalmet/config';

import type {
  ExtractedField,
  PerceptionAnalysis,
  ProcessingRun,
} from '@legalmet/types';

import { ExtractionStatusBadge, ProcessingRunBadge } from '../components/Badge';
import { Card, CardBody, CardHead, SectionCard } from '../components/Card';
import { EmptyState } from '../components/states';
import { Icon } from '../components/Icon';
import { formatDateTime, formatDurationMs, formatPercent } from '../lib/format';

export function PerceptionControlCard({
  analysis,
  starting,
  onStart,
  hasImages,
}: {
  analysis: PerceptionAnalysis | null;
  starting: boolean;
  onStart: () => void;
  hasImages: boolean;
}) {
  const active = analysis?.active ?? false;
  const hasRuns = analysis?.hasRuns ?? false;
  const summary = analysis?.summary;

  return (
    <Card>
      <CardHead
        eyebrow="Perception"
        title="Package perception"
        subtitle="Real OCR + symbol detection over the uploaded images"
        actions={hasRuns ? <ProcessingRunBadge status={active ? 'OCR_PROCESSING' : 'COMPLETED'} /> : undefined}
      />
      <CardBody>
        {!hasImages ? (
          <p style={{ color: 'var(--text-muted)' }}>
            Upload at least one package image before running perception.
          </p>
        ) : (
          <div className="stack stack--sm">
            {active && (
              <div className="demo-note" style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                <span className="spinner spinner--sm" aria-hidden />
                <span>Perception is running — reading text and detecting symbols. This view refreshes automatically.</span>
              </div>
            )}

            {hasRuns && summary && (
              <dl className="meta-grid">
                <div>
                  <dt>Text lines (OCR)</dt>
                  <dd>{summary.textElements}</dd>
                </div>
                <div>
                  <dt>Visual regions</dt>
                  <dd>{summary.visualRegions}</dd>
                </div>
                <div>
                  <dt>Declarations found</dt>
                  <dd>{summary.fieldsExtracted}</dd>
                </div>
                <div>
                  <dt>Low-confidence items</dt>
                  <dd>{summary.lowConfidenceItems}</dd>
                </div>
                <div>
                  <dt>Processing time</dt>
                  <dd>{formatDurationMs(summary.totalProcessingMs)}</dd>
                </div>
                <div>
                  <dt>OCR model</dt>
                  <dd title={summary.ocrModel ?? undefined}>{summary.ocrModel ?? '—'}</dd>
                </div>
                <div>
                  <dt>Vision model</dt>
                  <dd title={summary.visionModel ?? undefined}>{summary.visionModel ?? '—'}</dd>
                </div>
              </dl>
            )}

            <button
              type="button"
              className="btn btn--primary"
              disabled={starting || active || !hasImages}
              onClick={onStart}
            >
              <Icon name="sparkscan" size={15} />
              {starting
                ? 'Starting…'
                : active
                  ? 'Perception running…'
                  : hasRuns
                    ? 'Re-run perception (new runs)'
                    : 'Run perception analysis'}
            </button>

            <p style={{ fontSize: 'var(--fs-xs)', color: 'var(--text-faint)' }}>
              Every run creates new processing runs; previous runs and their evidence remain in the
              history below.
            </p>
          </div>
        )}
      </CardBody>
    </Card>
  );
}

export function PerceptionDeclarationsCard({
  fields,
  selectedFieldId,
  onSelect,
}: {
  fields: ExtractedField[];
  selectedFieldId?: string | null;
  onSelect: (field: ExtractedField) => void;
}) {
  return (
    <SectionCard
      eyebrow="Extraction"
      title="Detected declarations"
      subtitle="Perception results — select one to see its evidence"
    >
      {fields.length === 0 ? (
        <EmptyState
          icon="image"
          title="No declarations detected"
          message="Run perception to read the package. Fields the extractor cannot read confidently are listed here for review — never silently guessed."
        />
      ) : (
        <div className="stack stack--sm">
          {fields.map((field) => {
            const meta = EXTRACTION_STATUS_META[field.status];
            const selected = field.id === selectedFieldId;
            // Prompt 9 (Phase 12): a corrected field shows the HUMAN value —
            // clearly marked, never presented as an AI read.
            const corrected = field.correctedValue != null && field.correctedValue !== '';
            const shown = corrected ? field.correctedValue : (field.normalizedValue ?? '—');
            return (
              <button
                key={field.id}
                type="button"
                className={`decl decl--perception${selected ? ' is-selected' : ''}`}
                onClick={() => onSelect(field)}
                title={
                  corrected
                    ? `Human-corrected value (AI original: ${field.normalizedValue ?? '—'})`
                    : meta.description
                }
              >
                <span className="decl__main">
                  <span className="decl__label">{FIELD_TYPE_LABELS[field.fieldType]}</span>
                  <span className="decl__value" style={{ fontFamily: 'var(--font-mono)' }}>
                    {shown}
                  </span>
                </span>
                <span className="decl__side">
                  {corrected && (
                    <span className="tag" title="Corrected by an inspector — the AI value is preserved in history">
                      human correction
                    </span>
                  )}
                  <ExtractionStatusBadge status={field.status} />
                  <span className="decl__conf" title="OCR confidence × pattern weight — not legal confidence">
                    {formatPercent(field.confidence)}
                  </span>
                </span>
              </button>
            );
          })}
        </div>
      )}
    </SectionCard>
  );
}

export function PerceptionRunHistoryCard({
  runs,
  onReanalyze,
  reanalyzing,
}: {
  runs: ProcessingRun[];
  onReanalyze?: (imageId: string) => void;
  reanalyzing?: boolean;
}) {
  const byImage = new Map<string, ProcessingRun>();
  for (const run of runs) {
    if (!byImage.has(run.imageId)) byImage.set(run.imageId, run); // runs are newest-first
  }

  return (
    <SectionCard
      eyebrow="Traceability"
      title="Processing run history"
      subtitle="Every analysis ever run — reanalysis adds runs, history is preserved"
    >
      {runs.length === 0 ? (
        <EmptyState icon="clock" title="No processing runs yet" />
      ) : (
        <div className="stack stack--sm">
          {runs.map((run) => {
            const meta = PROCESSING_RUN_STATUS_META[run.status];
            const isLatest = byImage.get(run.imageId)?.id === run.id;
            return (
              <div key={run.id} className="run-row" title={meta.description}>
                <div className="run-row__head">
                  <span className="run-row__ref">{run.reference}</span>
                  <ProcessingRunBadge status={run.status} />
                  {isLatest ? <span className="tag">latest</span> : null}
                </div>
                <div className="run-row__meta">
                  <span>{formatDateTime(run.createdAt)}</span>
                  <span>·</span>
                  <span>{formatDurationMs(run.durationMs)}</span>
                  <span>·</span>
                  <span title={`${run.ocrProvider} / ${run.ocrModel} (${run.ocrVersion})`}>
                    {run.ocrModel ?? '—'}
                  </span>
                  {run.visionModel && (
                    <>
                      <span>·</span>
                      <span>{run.visionModel}</span>
                    </>
                  )}
                  <span>·</span>
                  <span>pipeline {run.pipelineVersion}</span>
                </div>
                {run.error != null && (
                  <p className="run-row__error">
                    <Icon name="alert" size={12} />{' '}
                    {typeof (run.error as { message?: string }).message === 'string'
                      ? (run.error as { message: string }).message
                      : 'Run failed.'}
                  </p>
                )}
                {isLatest && onReanalyze && (
                  <button
                    type="button"
                    className="btn btn--ghost btn--sm"
                    disabled={reanalyzing}
                    onClick={() => onReanalyze(run.imageId)}
                  >
                    <Icon name="reset" size={13} />
                    Re-analyze this image
                  </button>
                )}
              </div>
            );
          })}
        </div>
      )}
    </SectionCard>
  );
}
