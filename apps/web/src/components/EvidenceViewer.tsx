import { useRef, useState } from 'react';
import type { PointerEvent as ReactPointerEvent } from 'react';

import { FIELD_TYPE_LABELS } from '@legalmet/config';

import type { DetectedDeclaration, ViewerRegion } from '../mock/types';
import { toneColor, toneSoft } from '../lib/tone';
import { cn } from '../lib/cn';
import { Icon } from './Icon';

const ZOOM_MIN = 0.6;
const ZOOM_MAX = 3;
const ZOOM_STEP = 0.3;

/**
 * Package image viewer. Renders a SYNTHETIC label stand-in (no real image is
 * read — demo only) with detected-region overlays, zoom and pan. Regions are
 * selectable and coloured by their finding tone; selecting one drives the
 * intelligence panel.
 */
export function EvidenceViewer({
  packageLabel,
  regions,
  declarations = [],
  selectedRegionId,
  onSelectRegion,
}: {
  packageLabel: string;
  regions: ViewerRegion[];
  declarations?: DetectedDeclaration[];
  selectedRegionId?: string | null;
  onSelectRegion?: (id: string) => void;
}) {
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [dragging, setDragging] = useState(false);
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
    setPan({ x: drag.current.px + (e.clientX - drag.current.x), y: drag.current.py + (e.clientY - drag.current.y) });
  };
  const endDrag = () => {
    drag.current = null;
    setDragging(false);
  };

  const labelRows = declarations.filter((d) => d.value && d.value !== '—').slice(0, 6);

  return (
    <div className="viewer">
      <div className="viewer__toolbar">
        <span className="row" style={{ gap: 6, fontSize: 'var(--fs-sm)', color: 'var(--text-muted)' }}>
          <Icon name="image" size={15} /> Front label
        </span>
        <span className="badge badge--square" title="Synthetic demo image">
          <Icon name="alert" size={11} /> Synthetic demo image
        </span>
        <span className="spacer" />
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
        className="viewer__stage"
        style={{ cursor: dragging ? 'grabbing' : 'grab' }}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={endDrag}
        onPointerLeave={endDrag}
      >
        <div
          className="viewer__canvas"
          style={{ transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})` }}
        >
          {/* Synthetic label stand-in */}
          <div className="package-mock">
            <div className="package-mock__brand">{packageLabel}</div>
            {labelRows.map((d) => (
              <div key={d.field} className="package-mock__row">
                <span className="package-mock__key">{FIELD_TYPE_LABELS[d.field]}</span>
                <span>{d.value}</span>
              </div>
            ))}
          </div>

          {/* Region overlays */}
          {regions.map((r) => {
            const selected = r.id === selectedRegionId;
            return (
              <button
                key={r.id}
                type="button"
                className={cn('viewer__region', selected && 'is-selected')}
                style={{
                  left: `${r.bbox.x * 100}%`,
                  top: `${r.bbox.y * 100}%`,
                  width: `${r.bbox.width * 100}%`,
                  height: `${r.bbox.height * 100}%`,
                  ...(selected
                    ? {}
                    : { borderColor: toneColor(r.tone), background: toneSoft(r.tone) }),
                }}
                onPointerDown={(e) => e.stopPropagation()}
                onClick={(e) => {
                  e.stopPropagation();
                  onSelectRegion?.(r.id);
                }}
                aria-label={`${r.label} region`}
                aria-pressed={selected}
              >
                <span
                  className="viewer__region-tag"
                  style={selected ? undefined : { background: toneColor(r.tone) }}
                >
                  {r.label}
                </span>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
