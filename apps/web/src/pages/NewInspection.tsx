import { useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import type { BatchUploadResponse, ImageType, PackageImage } from '@legalmet/types';

import { api, ApiClientError } from '../api/client';
import { useApp } from '../app/AppContext';
import { Card, CardBody, CardHead, SectionCard } from '../components/Card';
import { Icon } from '../components/Icon';
import type { IconName } from '../components/Icon';
import { Field, SelectField } from '../components/inputs';
import { PageHeader } from '../components/PageHeader';
import { cn } from '../lib/cn';
import { humanizeEnum } from '../lib/format';
import { CameraCapture } from '../intake/CameraCapture';
import { ImageCard } from '../intake/ImageCard';
import { QualityReadout } from '../intake/QualityReadout';
import {
  ACCEPT_ATTR,
  CATEGORY_OPTIONS,
  IMAGE_TYPE_OPTIONS,
  MAX_BATCH_FILES,
  validateFileForUpload,
} from '../intake/constants';
import { useIntakeSession } from '../intake/useIntakeSession';
import type { IntakeSession } from '../intake/useIntakeSession';

type Method = 'SCAN' | 'UPLOAD' | 'BATCH';

const METHODS: { id: Method; icon: IconName; label: string }[] = [
  { id: 'SCAN', icon: 'camera', label: 'Scan package' },
  { id: 'UPLOAD', icon: 'upload', label: 'Upload images' },
  { id: 'BATCH', icon: 'batch', label: 'Batch import' },
];

/** The whole pipeline, always visible so the flow is never a mystery. */
const PIPELINE_STEPS: { label: string; phase: 'intake' | 'perception' | 'review' }[] = [
  { label: 'Create inspection', phase: 'intake' },
  { label: 'Add image', phase: 'intake' },
  { label: 'Validation', phase: 'intake' },
  { label: 'Quality', phase: 'intake' },
  { label: 'Run perception', phase: 'perception' },
  { label: 'OCR + vision', phase: 'perception' },
  { label: 'Extraction', phase: 'perception' },
  { label: 'Evaluation', phase: 'perception' },
  { label: 'Findings', phase: 'review' },
  { label: 'Review', phase: 'review' },
];

function PipelineMap({ stage }: { stage: 'collect' | 'images' | 'ready' }) {
  const activeIndex =
    stage === 'collect' ? 0 : stage === 'images' ? 2 : 4; // create | validation | run perception
  return (
    <div className="pipeline-map" aria-label="Inspection pipeline">
      {PIPELINE_STEPS.map((step, i) => (
        <span
          key={step.label}
          className={cn(
            'pipeline-map__step',
            `pipeline-map__step--${step.phase}`,
            i === activeIndex && 'is-active',
            i < activeIndex && 'is-done',
          )}
        >
          {i < activeIndex ? '✓' : i + 1}. {step.label}
        </span>
      ))}
    </div>
  );
}

export function NewInspectionPage() {
  const { isLive, auth } = useApp();
  const navigate = useNavigate();
  const session = useIntakeSession();
  const [method, setMethod] = useState<Method>('SCAN');
  const [imageType, setImageType] = useState<ImageType>('FRONT');

  const lastImage = session.images.length ? session.images[session.images.length - 1] : null;

  return (
    <div className="page">
      <PageHeader
        eyebrow="Intake"
        title="New inspection"
        lead="Capture or upload real label images for a packaged commodity. Images are validated, quality-checked and stored, then the package is marked ready for analysis."
      />

      <div className="demo-note demo-note--block">
        <Icon name="info" size={15} />
        <span>
          This is <strong>real package intake</strong>. Uploaded images are validated and stored, and each
          gets a deterministic <strong>usability</strong> grade. No OCR, computer vision or compliance
          analysis runs at this stage — the strongest outcome here is <strong>Ready for analysis</strong>.
        </span>
      </div>

      {!isLive && (
        <Card>
          <CardBody>
            <div className="row" style={{ gap: 'var(--space-3)', alignItems: 'flex-start' }}>
              <Icon name="alert" size={18} />
              <div>
                <div className="cell-strong">Real intake is unavailable</div>
                <p className="cell-muted" style={{ fontSize: 'var(--fs-sm)', marginTop: 4 }}>
                  {auth.kind === 'anonymous'
                    ? auth.message
                    : 'Connecting to the backend…'}{' '}
                  You can still explore the worked demonstration inspections below.
                </p>
              </div>
            </div>
          </CardBody>
        </Card>
      )}

      {session.error && (
        <div className="upload-row upload-row--error" role="alert">
          <span>{session.error}</span>
          <button type="button" className="btn btn--ghost btn--sm" onClick={session.clearError}>
            Dismiss
          </button>
        </div>
      )}

      <PipelineMap stage={session.phase === 'collect' ? 'collect' : 'images'} />

      {session.phase === 'collect' ? (
        <PackageDetailsStep session={session} disabled={!isLive} />
      ) : (
        <>
          <SectionCard eyebrow="Step 2" title="Add label images">
            <div className="intake-tabs" role="tablist" aria-label="Capture method">
              {METHODS.map((m) => (
                <button
                  key={m.id}
                  type="button"
                  role="tab"
                  aria-selected={method === m.id}
                  className={cn('intake-tab', method === m.id && 'is-active')}
                  onClick={() => setMethod(m.id)}
                >
                  <Icon name={m.icon} size={15} />
                  {m.label}
                </button>
              ))}
            </div>

            {method !== 'BATCH' && (
              <div style={{ maxWidth: 260, marginTop: 'var(--space-4)' }}>
                <SelectField
                  label="Image type"
                  value={imageType}
                  options={IMAGE_TYPE_OPTIONS}
                  onChange={(v) => setImageType(v as ImageType)}
                />
              </div>
            )}

            <div style={{ marginTop: 'var(--space-4)' }}>
              {method === 'SCAN' && session.inspectionId && (
                <ScanPanel
                  inspectionId={session.inspectionId}
                  imageType={imageType}
                  onUploaded={session.addImage}
                />
              )}
              {method === 'UPLOAD' && session.inspectionId && (
                <UploadPanel
                  inspectionId={session.inspectionId}
                  imageType={imageType}
                  onUploaded={session.addImage}
                />
              )}
              {method === 'BATCH' && session.inspectionId && (
                <BatchPanel inspectionId={session.inspectionId} onUploaded={session.addImage} />
              )}
            </div>
          </SectionCard>

          {lastImage && (
            <Card>
              <CardHead
                eyebrow="Step 3"
                title="Image quality"
                subtitle="Deterministic usability check on the most recent image"
              />
              <CardBody>
                <QualityReadout image={lastImage} />
              </CardBody>
            </Card>
          )}

          {lastImage &&
            (lastImage.qualityGrade === 'POOR' || lastImage.qualityGrade === 'REJECTED') && (
              <div className="upload-row upload-row--error" role="alert">
                <span>
                  <strong>Low image usability ({humanizeEnum(lastImage.qualityGrade)}).</strong> The
                  most recent image may be hard to read reliably later. Retake it with better lighting,
                  focus and framing — this is an image-quality signal only, not a compliance result.
                </span>
                <button
                  type="button"
                  className="btn btn--subtle btn--sm"
                  onClick={() => setMethod('SCAN')}
                >
                  <Icon name="camera" size={14} />
                  Retake
                </button>
              </div>
            )}

          <StoredImagesStep session={session} />

          <ReadyStep
            session={session}
            onReady={(inspectionId) => navigate(`/inspections/${inspectionId}`)}
          />
        </>
      )}

      <DemoFooter />
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Step 1 — package details                                                   */
/* -------------------------------------------------------------------------- */
function PackageDetailsStep({ session, disabled }: { session: IntakeSession; disabled: boolean }) {
  const [productName, setProductName] = useState('');
  const [category, setCategory] = useState(CATEGORY_OPTIONS[0].value);
  const [note, setNote] = useState('');

  const canSubmit = productName.trim().length > 0 && !disabled && !session.creating;

  const submit = () => {
    if (!canSubmit) return;
    void session.create({
      productName: productName.trim(),
      productCategory: category,
      note: note.trim() || undefined,
    });
  };

  return (
    <SectionCard eyebrow="Step 1" title="Package details">
      <div className="stack stack--sm" style={{ maxWidth: 520 }}>
        <Field label="Product name" htmlFor="intake-name">
          <input
            id="intake-name"
            className="input"
            value={productName}
            placeholder="e.g. Namkeen Mix 200g"
            disabled={disabled}
            onChange={(e) => setProductName(e.target.value)}
          />
        </Field>
        <SelectField
          label="Product category"
          value={category}
          options={CATEGORY_OPTIONS}
          onChange={setCategory}
          disabled={disabled}
        />
        <Field label="Note (optional)" htmlFor="intake-note">
          <input
            id="intake-note"
            className="input"
            value={note}
            placeholder="Retail location, batch reference, …"
            disabled={disabled}
            onChange={(e) => setNote(e.target.value)}
          />
        </Field>
        <div className="row">
          <button type="button" className="btn btn--primary" disabled={!canSubmit} onClick={submit}>
            {session.creating ? 'Creating…' : 'Create inspection'}
            {!session.creating && <Icon name="arrowRight" size={15} />}
          </button>
        </div>
      </div>
    </SectionCard>
  );
}

/* -------------------------------------------------------------------------- */
/* Step 2a — live camera capture                                              */
/* -------------------------------------------------------------------------- */
function ScanPanel({
  inspectionId,
  imageType,
  onUploaded,
}: {
  inspectionId: string;
  imageType: ImageType;
  onUploaded: (image: PackageImage) => void;
}) {
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleCapture = async (blob: Blob) => {
    setUploading(true);
    setError(null);
    try {
      const image = await api.uploadImage(inspectionId, blob, {
        captureSource: 'CAMERA',
        imageType,
      });
      onUploaded(image);
    } catch (err) {
      setError(err instanceof ApiClientError ? err.message : 'Upload failed.');
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="stack stack--sm">
      <CameraCapture onCapture={(blob) => void handleCapture(blob)} busy={uploading} />
      {uploading && (
        <p className="cell-muted" style={{ fontSize: 'var(--fs-sm)' }}>
          <span className="spinner" aria-hidden /> Uploading capture…
        </p>
      )}
      {error && (
        <p className="upload-row upload-row--error" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Step 2b — file upload with per-file progress                               */
/* -------------------------------------------------------------------------- */
interface PendingUpload {
  key: string;
  name: string;
  percent: number;
  error?: string;
}

function UploadPanel({
  inspectionId,
  imageType,
  onUploaded,
}: {
  inspectionId: string;
  imageType: ImageType;
  onUploaded: (image: PackageImage) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [pending, setPending] = useState<PendingUpload[]>([]);
  const seq = useRef(0);
  const [dragOver, setDragOver] = useState(false);

  const uploadOne = async (file: File) => {
    const key = `u${seq.current++}`;
    const validation = validateFileForUpload(file);
    if (!validation.ok) {
      setPending((p) => [...p, { key, name: file.name, percent: 0, error: validation.reason }]);
      return;
    }
    setPending((p) => [...p, { key, name: file.name, percent: 0 }]);
    try {
      const image = await api.uploadImage(inspectionId, file, {
        captureSource: 'UPLOAD',
        imageType,
        onProgress: (pr) =>
          setPending((p) => p.map((x) => (x.key === key ? { ...x, percent: pr.percent } : x))),
      });
      onUploaded(image);
      setPending((p) => p.filter((x) => x.key !== key)); // success → moves into the stored grid
    } catch (err) {
      const message = err instanceof ApiClientError ? err.message : 'Upload failed.';
      setPending((p) => p.map((x) => (x.key === key ? { ...x, percent: 0, error: message } : x)));
    }
  };

  const handleFiles = (files: FileList | null) => {
    if (!files) return;
    for (const file of Array.from(files)) void uploadOne(file);
    if (inputRef.current) inputRef.current.value = '';
  };

  return (
    <div className="stack stack--sm">
      <div
        className="dropzone"
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          handleFiles(e.dataTransfer.files);
        }}
        style={dragOver ? { borderColor: 'var(--accent)' } : undefined}
      >
        <span className="capture-option__icon" aria-hidden>
          <Icon name="upload" size={22} />
        </span>
        <p className="cell-muted" style={{ textAlign: 'center', maxWidth: '42ch' }}>
          Drop front / back label images here, or browse. JPEG, PNG or WebP.
        </p>
        <button type="button" className="btn btn--primary btn--sm" onClick={() => inputRef.current?.click()}>
          <Icon name="upload" size={15} />
          Browse images
        </button>
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPT_ATTR}
          multiple
          hidden
          onChange={(e) => handleFiles(e.target.files)}
        />
      </div>

      {pending.length > 0 && (
        <div className="upload-list">
          {pending.map((u) => (
            <div key={u.key} className={cn('upload-row', u.error && 'upload-row--error')}>
              <span className="upload-row__name">{u.name}</span>
              <span className="cell-muted" style={{ fontSize: 'var(--fs-sm)' }}>
                {u.error ? u.error : `${u.percent}%`}
              </span>
              {!u.error && (
                <div className="progress">
                  <div className="progress__bar" style={{ width: `${u.percent}%` }} />
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Step 2c — batch import                                                      */
/* -------------------------------------------------------------------------- */
function BatchPanel({
  inspectionId,
  onUploaded,
}: {
  inspectionId: string;
  onUploaded: (image: PackageImage) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [percent, setPercent] = useState(0);
  const [dragOver, setDragOver] = useState(false);
  const [result, setResult] = useState<BatchUploadResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleFiles = async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    const list = Array.from(files).slice(0, MAX_BATCH_FILES);
    setBusy(true);
    setError(null);
    setResult(null);
    setPercent(0);
    try {
      const response = await api.batchUpload(inspectionId, list, {
        onProgress: (pr) => setPercent(pr.percent),
      });
      setResult(response);
      for (const item of response.items) if (item.image) onUploaded(item.image);
    } catch (err) {
      setError(err instanceof ApiClientError ? err.message : 'Batch upload failed.');
    } finally {
      setBusy(false);
      if (inputRef.current) inputRef.current.value = '';
    }
  };

  return (
    <div className="stack stack--sm">
      <div
        className="dropzone"
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          if (!busy) void handleFiles(e.dataTransfer.files);
        }}
        style={dragOver ? { borderColor: 'var(--accent)' } : undefined}
      >
        <span className="capture-option__icon" aria-hidden>
          <Icon name="batch" size={22} />
        </span>
        <p className="cell-muted" style={{ textAlign: 'center', maxWidth: '46ch' }}>
          Drop up to {MAX_BATCH_FILES} images here, or browse. Each is validated independently —
          valid images are stored and invalid ones are reported without failing the batch.
        </p>
        <button
          type="button"
          className="btn btn--primary btn--sm"
          disabled={busy}
          onClick={() => inputRef.current?.click()}
        >
          {busy ? 'Uploading…' : 'Select images'}
        </button>
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPT_ATTR}
          multiple
          hidden
          onChange={(e) => void handleFiles(e.target.files)}
        />
      </div>

      {busy && (
        <div className="upload-row">
          <span className="upload-row__name">Uploading batch…</span>
          <span className="cell-muted" style={{ fontSize: 'var(--fs-sm)' }}>
            {percent}%
          </span>
          <div className="progress">
            <div className="progress__bar" style={{ width: `${percent}%` }} />
          </div>
        </div>
      )}

      {error && (
        <p className="upload-row upload-row--error" role="alert">
          {error}
        </p>
      )}

      {result && (
        <div className="stack stack--sm">
          <div className="batch-summary">
            <span className="badge badge--positive">{result.uploaded} uploaded</span>
            {result.rejected > 0 && <span className="badge badge--critical">{result.rejected} rejected</span>}
          </div>
          <div className="batch-list">
            {result.items.map((item, idx) => (
              <div
                key={`${item.filename}-${idx}`}
                className={cn('batch-row', item.status === 'UPLOADED' ? 'batch-row--ok' : 'batch-row--rejected')}
              >
                <span className="batch-row__name">{item.filename}</span>
                <span className="cell-muted" style={{ fontSize: 'var(--fs-sm)' }}>
                  {item.status === 'UPLOADED' ? 'Uploaded' : item.error?.message ?? 'Rejected'}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Stored images + finalize                                                    */
/* -------------------------------------------------------------------------- */
function StoredImagesStep({ session }: { session: IntakeSession }) {
  if (session.images.length === 0) return null;
  return (
    <SectionCard
      eyebrow="Captured"
      title={`Stored images (${session.images.length})`}
      subtitle="Provenance and usability only — no OCR or compliance is shown for real uploads."
    >
      <div className="intake-grid">
        {session.images.map((image) => (
          <ImageCard
            key={image.id}
            image={image}
            busy={session.busyImageId === image.id}
            onRemove={session.removeImage}
            onPrepare={session.prepareImage}
          />
        ))}
      </div>
    </SectionCard>
  );
}

function ReadyStep({
  session,
  onReady,
}: {
  session: IntakeSession;
  onReady: (inspectionId: string) => void;
}) {
  const canFinalize = session.images.length > 0 && !session.finalizing;

  const finalize = async () => {
    const ready = await session.finalize();
    if (ready) onReady(ready.id);
  };

  return (
    <Card>
      <PipelineMap stage="ready" />
      <CardHead
        eyebrow="Step 4"
        title="Ready for analysis"
        subtitle="Marks the package ready — then perception runs in the workspace"
      />
      <CardBody>
        <div className="row row--between row--wrap" style={{ gap: 'var(--space-3)' }}>
          <span className="cell-muted" style={{ fontSize: 'var(--fs-sm)' }}>
            {session.images.length === 0
              ? 'Add at least one valid image to continue.'
              : `${session.images.length} image${session.images.length > 1 ? 's' : ''} stored and validated.`}
          </span>
          <button type="button" className="btn btn--primary" disabled={!canFinalize} onClick={() => void finalize()}>
            {session.finalizing ? 'Finalizing…' : 'Open workspace & run perception'}
            {!session.finalizing && <Icon name="arrowRight" size={15} />}
          </button>
        </div>
      </CardBody>
    </Card>
  );
}

/* -------------------------------------------------------------------------- */
/* Demo footer — keep the worked demonstration inspections reachable          */
/* -------------------------------------------------------------------------- */
function DemoFooter() {
  return (
    <p className="cell-muted" style={{ fontSize: 'var(--fs-sm)', marginTop: 'var(--space-4)' }}>
      Looking for the fully-worked demonstration?{' '}
      <Link to="/inspections/ins-10482">View a demo inspection</Link>. Demo inspections use clearly
      labelled placeholder data and are kept separate from real intake.
    </p>
  );
}
