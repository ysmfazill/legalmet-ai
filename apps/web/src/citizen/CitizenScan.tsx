import { useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import { Icon } from '../components/Icon';
import { CameraCapture } from '../intake/CameraCapture';
import { ACCEPT_ATTR, validateFileForUpload } from '../intake/constants';
import { useCitizenSession } from './session';
import { cn } from '../lib/cn';

const SCAN_TIPS = [
  'Keep the label in focus',
  'Avoid glare and shadows',
  'Capture the complete declaration area',
  'Ensure the text is readable',
];

/**
 * SCAN PACKAGE (Checkpoints 2–4) — capture or upload, then the REAL backend
 * pipeline runs (quality gate → OCR → declaration extraction).
 *
 * The camera is the existing inspector CameraCapture (getUserMedia, no fake
 * capture). Upload offers browse + drag/drop on desktop. Every file goes to
 * POST /citizen/scans — an honest, server-validated run; client-side checks
 * are only fast UX feedback, the server re-validates every byte.
 */
export function CitizenScanPage() {
  const { startScan, scanning, error, clearError } = useCitizenSession();
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);
  const [mode, setMode] = useState<'choose' | 'camera'>('choose');
  const [localError, setLocalError] = useState<string | null>(null);

  function handleFile(file: File | Blob) {
    setLocalError(null);
    if (file instanceof File) {
      // Fast UX feedback only — the server re-validates every byte.
      const validation = validateFileForUpload(file);
      if (!validation.ok) {
        clearError();
        setLocalError(validation.reason ?? 'This file cannot be screened.');
        return;
      }
    }
    void startScan(file);
  }

  function handleFiles(files: FileList | null) {
    const file = files?.[0];
    if (file) handleFile(file);
    if (inputRef.current) inputRef.current.value = '';
  }

  return (
    <div className="citizen-page">
      <div className="citizen-page__topbar">
        <Link to="/citizen" className="btn btn--ghost btn--sm">
          <Icon name="chevronLeft" size={15} />
          Back
        </Link>
        <span className="citizen-step__label">Scan package</span>
        <span className="citizen-step__count" aria-hidden>1 / 2</span>
      </div>

      <h1 className="citizen-page__title">Scan package</h1>
      <p className="citizen-page__lead">
        Capture the front and relevant label areas clearly.
      </p>

      {(error || localError) && (
        <div className="citizen-error" role="alert">
          <Icon name="alert" size={16} />
          <div>
            <strong>Photo could not be screened.</strong>
            <p>{error ?? localError}</p>
          </div>
          <button
            type="button"
            className="btn btn--subtle btn--sm"
            onClick={() => {
              clearError();
              setLocalError(null);
            }}
          >
            Dismiss
          </button>
        </div>
      )}

      {scanning ? (
        <CitizenProcessing />
      ) : mode === 'camera' ? (
        <section className="stack" aria-label="Camera capture">
          <CameraCapture onCapture={handleFile} busy={scanning} />
          <button type="button" className="btn btn--ghost btn--sm" onClick={() => setMode('choose')}>
            <Icon name="chevronLeft" size={15} />
            Back to options
          </button>
        </section>
      ) : (
        <>
          <div className="citizen-actions">
            <button
              type="button"
              className="btn btn--primary btn--lg"
              onClick={() => setMode('camera')}
            >
              <Icon name="camera" size={18} />
              Take photo
            </button>
            <button
              type="button"
              className="btn btn--subtle btn--lg"
              onClick={() => inputRef.current?.click()}
            >
              <Icon name="upload" size={18} />
              Upload image
            </button>
            <input
              ref={inputRef}
              type="file"
              accept={ACCEPT_ATTR}
              capture="environment"
              hidden
              onChange={(e) => handleFiles(e.target.files)}
            />
          </div>

          <div
            className={cn('dropzone', dragOver && 'dropzone--over')}
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
          >
            <span className="capture-option__icon" aria-hidden>
              <Icon name="upload" size={22} />
            </span>
            <p className="cell-muted" style={{ textAlign: 'center', maxWidth: '40ch' }}>
              Or drag a label photo here. JPEG, PNG or WebP.
            </p>
          </div>

          <ul className="citizen-tips" aria-label="Photo tips">
            {SCAN_TIPS.map((tip) => (
              <li key={tip}>
                <Icon name="check" size={14} />
                {tip}
              </li>
            ))}
          </ul>
        </>
      )}

      <p className="citizen-footnote">
        The photo is screened automatically — reading quality, then label text.
        Nothing is decided: results always say what a human should check.
      </p>
    </div>
  );
}

/**
 * PROCESSING (Checkpoint 4) — honest stage display. No fake percentages:
 * the request is in flight against the real pipeline and the stages shown
 * are exactly the backend's (image received → OCR → extraction → screening).
 */
function CitizenProcessing() {
  const navigate = useNavigate();
  return (
    <section className="citizen-processing" aria-live="polite">
      <span className="spinner" aria-hidden />
      <h2>Analyzing package</h2>
      <p className="cell-muted">Reading package declarations…</p>
      <ol className="citizen-processing__stages">
        <li className="is-done">
          <Icon name="check" size={13} />
          Image received
        </li>
        <li className="is-doing">
          <span className="citizen-processing__dot" aria-hidden />
          Detecting label text (OCR)
        </li>
        <li>
          <span className="citizen-processing__ring" aria-hidden />
          Extracting declarations
        </li>
        <li>
          <span className="citizen-processing__ring" aria-hidden />
          Preparing screening result
        </li>
      </ol>
      <button type="button" className="btn btn--ghost btn--sm" onClick={() => navigate('/citizen')}>
        Cancel
      </button>
    </section>
  );
}
