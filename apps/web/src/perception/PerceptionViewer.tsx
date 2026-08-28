/**
 * REAL package-image viewer with perception overlays (Prompt 4).
 *
 * Renders the actual stored image (bearer-authenticated blob URL) with:
 * - zoom + pan over the real pixels,
 * - a toggleable OCR overlay (one box per recognized text line, labelled with
 *   the verbatim engine output and its OCR confidence),
 * - a toggleable symbol overlay (QR / barcode regions with their decoded
 *   payload),
 * - region highlighting driven by declaration selection (click a declaration
 *   in the panel and its evidence region lights up here).
 *
 * Overlays are perception evidence only. Nothing in this viewer states that a
 * declaration is legally correct or incorrect.
 */
import { useRef, useState } from 'react';
import type { PointerEvent as ReactPointerEvent } from 'react';

import type { BoundingBox, ImageRegion, OcrTextResult, PackageImage } from '@legalmet/types';

import { cn } from '../lib/cn';
import { Icon } from '../components/Icon';
import { useObjectUrl } from '../intake/useObjectUrl';

const ZOOM_MIN = 0.6;
const ZOOM_MAX = 4;
const ZOOM_STEP = 0.3;

/** OCR confidence band — the engine's own recognition score, never legal confidence. */
function ocrTone(confidence: number): string {
  if (confidence >= 0.85) return 'var(--tone-positive)';
  if (confidence >= 0.6) return 'var(--tone-info)';
  return 'var(--tone-warning)';
}

interface Overlay {
  id: string;
  bbox: BoundingBox;
  label: string;
  color: string;
  title: string;
}

function ocrOverlay(line: OcrTextResult): Overlay {
  return {
    id: line.id,
    bbox: line.bbox,
    label: `${Math.round(line.confidence * 100)}%`,
    color: ocrTone(line.confidence),
    title: `${line.rawText} — OCR confidence ${(line.confidence * 100).toFixed(1)}%`,
  };
}

function regionOverlay(region: ImageRegion): Overlay {
  const payload = region.payload as { symbology?: string; value?: string } | null;
  const kind = region.regionType === 'QR_CODE' ? 'QR' : (payload?.symbology ?? region.regionType);
  return {
    id: region.id,
    bbox: region.bbox,
    label: kind,
    color: 'var(--tone-critical)',
    title: payload?.value
      ? `${kind} — decoded value: ${payload.value}`
      : `${region.regionType} region (confidence ${(region.confidence * 100).toFixed(0)}%)`,
  };
}

export function PerceptionViewer({
  image,
  ocrLines,
  symbolRegions,
  selectedRegionId,
}: {
  image: PackageImage;
  /** OCR lines belonging to THIS image (latest run). */
  ocrLines: OcrTextResult[];
  /** QR / barcode regions belonging to THIS image (latest run). */
  symbolRegions: ImageRegion[];
  /** When set, this region is highlighted (evidence of the selected field). */
  selectedRegionId?: string | null;
}) {
  const view = useObjectUrl(image.processedStorageKey ?? image.storageKey);
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [dragging, setDragging] = useState(false);
  const [showOcr, setShowOcr] = useState(true);
  const [showSymbols, setShowSymbols] = useState(true);
  const drag = useRef<{ x: number; y: number; px: number; py: number } | null>(null);

  const reset = () => {
    setZoom(1);
    setPan({ x: 0, y: 0 });
  };

  const onPointerDown = (e: ReactPointerEvent<HTMLDivElement>) => {
    drag.current = { x: e.clientX, y: e.clientY, px: pan.x, py: pan.y };
    setDragging(true);
    e.currentTarget.setPointerCapture(e.pointerId);
  };
  const onPointerMove = (e: ReactPointerEvent<HTMLDivElement>) => {
    if (!drag.current) return;
    setPan({
      x: drag.current.px + (e.clientX - drag.current.x),
      y: drag.current.py + (e.clientY - drag.current.y),
    });
  };
  const endDrag = () => {
    drag.current = null;
    setDragging(false);
  };

  // The stage mirrors the image's own aspect ratio so fractional bboxes align
  // with the rendered pixels exactly.
  const ratio = image.width && image.height ? `${image.width} / ${image.height}` : '4 / 5';

  const overlays: Overlay[] = [
    ...(showOcr ? ocrLines.map(ocrOverlay) : []),
    ...(showSymbols ? symbolRegions.map(regionOverlay) : []),
  ];

  return (
    <div className="viewer">
      <div className="viewer__toolbar">
        <span className="row" style={{ gap: 6, fontSize: 'var(--fs-sm)', color: 'var(--text-muted)' }}>
          <Icon name="image" size={15} /> {image.imageType} · real image
        </span>
        <span className="spacer" />
        <button
          type="button"
          className={cn('btn btn--sm', showOcr ? 'btn--subtle' : 'btn--ghost')}
          aria-pressed={showOcr}
          onClick={() => setShowOcr((v) => !v)}
          title="Toggle recognized text lines (real OCR output)"
        >
          OCR text ({ocrLines.length})
        </button>
        <button
          type="button"
          className={cn('btn btn--sm', showSymbols ? 'btn--subtle' : 'btn--ghost')}
          aria-pressed={showSymbols}
          onClick={() => setShowSymbols((v) => !v)}
          title="Toggle QR / barcode regions"
        >
          Symbols ({symbolRegions.length})
        </button>
        <button type="button" className="icon-btn" onClick={() => setZoom((z) => Math.max(ZOOM_MIN, z - ZOOM_STEP))} aria-label="Zoom out">
          <Icon name="zoomOut" />
        </button>
        <span className="viewer__zoom">{Math.round(zoom * 100)}%</span>
        <button type="button" className="icon-btn" onClick={() => setZoom((z) => Math.min(ZOOM_MAX, z + ZOOM_STEP))} aria-label="Zoom in">
          <Icon name="zoomIn" />
        </button>
        <button type="button" className="icon-btn" onClick={reset} aria-label="Reset view">
          <Icon name="fit" />
        </button>
      </div>

      <div
        className="pviewer__stage"
        style={{ aspectRatio: ratio, cursor: dragging ? 'grabbing' : 'grab' }}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={endDrag}
        onPointerLeave={endDrag}
      >
        <div className="pviewer__frame" style={{ transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})` }}>
          {view.status === 'ready' ? (
            <img src={view.url} alt={image.originalFilename} draggable={false} />
          ) : view.status === 'loading' ? (
            <div className="pviewer__fallback"><span className="spinner" aria-hidden /></div>
          ) : (
            <div className="pviewer__fallback" title={view.message}>
              <Icon name="image" size={26} />
              <span>{view.message}</span>
            </div>
          )}

          {view.status === 'ready' &&
            overlays.map((o) => {
              const selected = o.id === selectedRegionId;
              return (
                <span
                  key={o.id}
                  className={cn('viewer__region', selected && 'is-selected')}
                  style={{
                    left: `${o.bbox.x * 100}%`,
                    top: `${o.bbox.y * 100}%`,
                    width: `${o.bbox.width * 100}%`,
                    height: `${o.bbox.height * 100}%`,
                    ...(selected ? {} : { borderColor: o.color, background: 'transparent' }),
                  }}
                  title={o.title}
                >
                  <span
                    className="viewer__region-tag"
                    style={selected ? undefined : { background: o.color, color: '#fff' }}
                  >
                    {o.label}
                  </span>
                </span>
              );
            })}
        </div>
      </div>
    </div>
  );
}
