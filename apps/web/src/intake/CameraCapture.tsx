import { useCallback, useEffect, useRef, useState } from 'react';

import { Icon } from '../components/Icon';

type CameraStatus = 'idle' | 'starting' | 'live' | 'captured' | 'denied' | 'unsupported';

interface CameraCaptureProps {
  /** Called with a JPEG blob when the inspector accepts a captured frame. */
  onCapture: (blob: Blob) => void;
  /** Disables capture while an upload is in flight. */
  busy?: boolean;
}

const CAPTURE_MIME = 'image/jpeg';
const CAPTURE_QUALITY = 0.92;

/**
 * Live label capture using the browser camera (`getUserMedia`). No frame ever
 * leaves the device until the inspector explicitly accepts it; the accepted
 * frame is handed up as a JPEG blob for a real, server-validated upload.
 *
 * Degrades safely: an unsupported API or a denied permission shows guidance to
 * switch to file upload instead — it never blocks the intake flow.
 */
export function CameraCapture({ onCapture, busy = false }: CameraCaptureProps) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [status, setStatus] = useState<CameraStatus>('idle');
  const [preview, setPreview] = useState<string | null>(null);
  const [pendingBlob, setPendingBlob] = useState<Blob | null>(null);
  const [error, setError] = useState<string | null>(null);

  const stopStream = useCallback(() => {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
  }, []);

  // Always release the camera on unmount.
  useEffect(() => stopStream, [stopStream]);

  // Revoke the preview object URL when it changes / unmounts.
  useEffect(() => {
    return () => {
      if (preview) URL.revokeObjectURL(preview);
    };
  }, [preview]);

  const start = useCallback(async () => {
    if (!navigator.mediaDevices?.getUserMedia) {
      setStatus('unsupported');
      return;
    }
    setStatus('starting');
    setError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'environment' },
        audio: false,
      });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play().catch(() => undefined);
      }
      setStatus('live');
    } catch (err) {
      const name = err instanceof DOMException ? err.name : '';
      if (name === 'NotAllowedError' || name === 'SecurityError') {
        setStatus('denied');
      } else if (name === 'NotFoundError' || name === 'OverconstrainedError') {
        setStatus('unsupported');
        setError('No camera device was found.');
      } else {
        setStatus('unsupported');
        setError(err instanceof Error ? err.message : 'Camera unavailable.');
      }
      stopStream();
    }
  }, [stopStream]);

  const capture = useCallback(() => {
    const video = videoRef.current;
    if (!video || !video.videoWidth) return;
    const canvas = document.createElement('canvas');
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    canvas.toBlob(
      (blob) => {
        if (!blob) return;
        setPreview((prev) => {
          if (prev) URL.revokeObjectURL(prev);
          return URL.createObjectURL(blob);
        });
        setPendingBlob(blob);
        stopStream();
        setStatus('captured');
      },
      CAPTURE_MIME,
      CAPTURE_QUALITY,
    );
  }, [stopStream]);

  const retake = useCallback(() => {
    setPendingBlob(null);
    setPreview((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return null;
    });
    void start();
  }, [start]);

  const accept = useCallback(() => {
    if (pendingBlob) onCapture(pendingBlob);
  }, [pendingBlob, onCapture]);

  return (
    <div className="camera">
      <div className="camera__stage" aria-live="polite">
        {status === 'captured' && preview ? (
          <img className="camera__media" src={preview} alt="Captured label preview" />
        ) : (
          <video
            ref={videoRef}
            className="camera__media"
            playsInline
            muted
            hidden={status !== 'live' && status !== 'starting'}
          />
        )}

        {status === 'idle' && (
          <div className="camera__placeholder">
            <Icon name="camera" size={26} />
            <p className="cell-muted">Use your device camera to capture the label live.</p>
          </div>
        )}
        {status === 'starting' && <div className="camera__placeholder"><span className="spinner" aria-hidden /></div>}
        {status === 'denied' && (
          <div className="camera__placeholder">
            <Icon name="alert" size={22} />
            <p className="cell-muted" style={{ maxWidth: '40ch', textAlign: 'center' }}>
              Camera permission was denied. Allow camera access in your browser, or switch to
              <strong> Upload images</strong> instead.
            </p>
          </div>
        )}
        {status === 'unsupported' && (
          <div className="camera__placeholder">
            <Icon name="alert" size={22} />
            <p className="cell-muted" style={{ maxWidth: '40ch', textAlign: 'center' }}>
              {error ?? 'Live capture is not available on this device.'} Use
              <strong> Upload images</strong> instead.
            </p>
          </div>
        )}
      </div>

      <div className="row" style={{ gap: 'var(--space-2)', justifyContent: 'center', flexWrap: 'wrap' }}>
        {status === 'idle' && (
          <button type="button" className="btn btn--primary btn--sm" onClick={() => void start()}>
            <Icon name="camera" size={15} />
            Start camera
          </button>
        )}
        {status === 'live' && (
          <button type="button" className="btn btn--primary btn--sm" onClick={capture} disabled={busy}>
            <Icon name="camera" size={15} />
            Capture
          </button>
        )}
        {status === 'captured' && (
          <>
            <button type="button" className="btn btn--primary btn--sm" onClick={accept} disabled={busy}>
              <Icon name="check" size={15} />
              Use photo
            </button>
            <button type="button" className="btn btn--subtle btn--sm" onClick={retake} disabled={busy}>
              <Icon name="reset" size={14} />
              Retake
            </button>
          </>
        )}
        {(status === 'denied' || status === 'unsupported') && (
          <button type="button" className="btn btn--subtle btn--sm" onClick={() => void start()}>
            <Icon name="reset" size={14} />
            Try again
          </button>
        )}
      </div>
    </div>
  );
}
