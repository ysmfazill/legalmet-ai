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
import { useEffect, useRef, useState } from 'react';

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
  runs,
  hasEvaluation,
}: {
  analysis: PerceptionAnalysis | null;
  starting: boolean;
  onStart: () => void;
  hasImages: boolean;
  runs: ProcessingRun[];
  hasEvaluation?: boolean;
}) {
  const active = analysis?.active ?? false;
  const hasRuns = analysis?.hasRuns ?? false;
  const summary = analysis?.summary;

  // Latest run per image drives the stage indicator; a FAILED latest run
  // drives the failure card. Never fabricated — statuses come from the
  // backend processing-run rows.
  const latestRuns = new Map<string, ProcessingRun>();
  for (const run of runs) {
    if (!latestRuns.has(run.imageId)) latestRuns.set(run.imageId, run); // newest-first
  }
  const latestList = [...latestRuns.values()];
  const anyFailed = latestList.some((r) => r.status === 'FAILED');
  const failure = latestList.find((r) => r.status === 'FAILED');

  return (
    <Card>
      <CardHead
        eyebrow="Perception"
        title="Package perception"
        subtitle="Real OCR + symbol detection over the uploaded images"
        actions={
          hasRuns ? (
            <ProcessingRunBadge status={active ? 'OCR_PROCESSING' : anyFailed ? 'FAILED' : 'COMPLETED'} />
          ) : undefined
        }
      />
      <CardBody>
        {!hasImages ? (
          <p style={{ color: 'var(--text-muted)' }}>
            Upload at least one package image before running perception.
          </p>
        ) : (
          <div className="stack stack--sm">
            {active && <PerceptionPipelineStages runs={latestList} />}

            {anyFailed && failure && (
              <div className="demo-note demo-note--block" style={{ borderColor: 'var(--tone-critical)' }}>
                <Icon name="alert" size={15} />
                <span>
                  <strong>PROCESSING FAILED.</strong>{' '}
                  {typeof (failure.error as { message?: string } | null)?.message === 'string'
                    ? (failure.error as { message: string }).message
                    : 'The perception run failed.'}{' '}
                  Nothing was fabricated — no results were produced for this image. Retry below
                  once the underlying issue is fixed.
                </span>
              </div>
            )}

            {!active && !hasRuns && (
              <div className="stack stack--xs" style={{ gap: 'var(--space-1)' }}>
                <p style={{ color: 'var(--text-muted)' }}>
                  Image ready for analysis. Run perception to read the package label — text,
                  symbols and declaration fields with per-item confidence.
                </p>
                <p style={{ fontSize: 'var(--fs-xs)', color: 'var(--text-faint)' }}>
                  First run may take longer while the local OCR model loads (measured 4–8s per
                  image after warm-up; later runs are faster).
                </p>
              </div>
            )}

            {!active && hasRuns && !anyFailed && (
              <div className="demo-note" style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                <span style={{ color: 'var(--tone-positive)', fontWeight: 'var(--fw-semibold)' }}>✓</span>
                <span>
                  <strong>Perception completed.</strong> Results below update automatically — no
                  manual refresh needed.
                </span>
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
                    ? anyFailed
                      ? 'Retry perception'
                      : 'Re-run perception (new runs)'
                    : 'Run perception'}
            </button>

            <p style={{ fontSize: 'var(--fs-xs)', color: 'var(--text-faint)' }}>
              Every run creates new processing runs; previous runs and their evidence remain in the
              history below.
              {hasRuns && !hasEvaluation
                ? ' After perception completes, run the regulatory evaluation below to produce findings.'
                : ''}
            </p>
          </div>
        )}
      </CardBody>
    </Card>
  );
}

/**
 * Stage-based progress (never a fake percentage — the backend does not track
 * one). Stages mirror the backend processing-run statuses exactly; the
 * elapsed timer is real client-side wall time since the panel mounted into an
 * active run.
 */
function PerceptionPipelineStages({ runs }: { runs: ProcessingRun[] }) {
  const [elapsed, setElapsed] = useState(0);
  const startedRef = useRef<number>(Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setElapsed((Date.now() - startedRef.current) / 1000), 100);
    return () => window.clearInterval(timer);
  }, []);

  const order: ProcessingRun['status'][] = [
    'QUEUED',
    'PREPROCESSING',
    'OCR_PROCESSING',
    'VISION_PROCESSING',
    'FIELD_EXTRACTION',
  ];
  const rank = (status: ProcessingRun['status']) =>
    order.indexOf(status) >= 0 ? order.indexOf(status) : order.length;

  const stages: Array<{ key: string; label: string; state: 'done' | 'active' | 'pending' }> = [
    { key: 'image', label: 'Image received & validated', state: 'done' },
    { key: 'quality', label: 'Image quality checked', state: 'done' },
    { key: 'ocr', label: 'Reading package text (OCR)', state: 'pending' },
    { key: 'vision', label: 'Detecting QR / barcodes', state: 'pending' },
    { key: 'fields', label: 'Extracting declarations', state: 'pending' },
    { key: 'eval', label: 'Regulatory evaluation (separate step)', state: 'pending' },
  ];
  // The furthest-advanced run defines progress; OCR is the long stage.
  const furthest = runs.length
    ? Math.max(...runs.map((r) => rank(r.status)))
    : 0;
  const stageIndex = Math.min(furthest, 4);
  for (let i = 2; i <= 3; i += 1) stages[i].state = 'pending';
  if (stageIndex >= 2) {
    stages[2].state = 'active';
    for (let i = 0; i < 2; i += 1) stages[i].state = 'done';
  }
  if (stageIndex >= 3) stages[2].state = 'done';
  if (stageIndex >= 4) {
    stages[3].state = 'done';
    stages[4].state = 'active';
  }

  return (
    <div className="demo-note demo-note--block" style={{ gap: 'var(--space-2)' }}>
      <div className="row row--between" style={{ width: '100%' }}>
        <strong style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          <span className="spinner spinner--sm" aria-hidden />
          PROCESSING PACKAGE
        </strong>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--fs-sm)' }}>
          {elapsed.toFixed(1)}s
        </span>
      </div>
      <ul className="pipeline-stages" style={{ width: '100%' }}>
        {stages.map((s) => (
          <li key={s.key} className={`pipeline-stage pipeline-stage--${s.state}`}>
            <span className="pipeline-stage__mark" aria-hidden>
              {s.state === 'done' ? '✓' : s.state === 'active' ? '→' : '○'}
            </span>
            {s.label}
          </li>
        ))}
      </ul>
      <span style={{ fontSize: 'var(--fs-xs)', color: 'var(--text-faint)' }}>
        Local OCR engine — real recognition, no cloud calls.
      </span>
    </div>
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
