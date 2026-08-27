import type { Tone } from '@legalmet/config';

import { toneColor } from '../lib/tone';
import type { ActivityPoint } from '../mock/types';

/* -------------------------------------------------------------------------- */
/* Legend                                                                     */
/* -------------------------------------------------------------------------- */
export interface LegendItem {
  label: string;
  value?: string | number;
  tone: Tone;
}

export function Legend({ items }: { items: LegendItem[] }) {
  return (
    <ul className="legend">
      {items.map((it) => (
        <li key={it.label} className="legend__item">
          <span className="legend__swatch" style={{ background: toneColor(it.tone) }} aria-hidden />
          <span className="legend__label">{it.label}</span>
          {it.value !== undefined && <span className="legend__value">{it.value}</span>}
        </li>
      ))}
    </ul>
  );
}

/* -------------------------------------------------------------------------- */
/* Donut / distribution                                                       */
/* -------------------------------------------------------------------------- */
export interface DonutSegment {
  label: string;
  value: number;
  tone: Tone;
}

export function DonutChart({
  segments,
  centerValue,
  centerLabel,
  size = 132,
}: {
  segments: DonutSegment[];
  centerValue?: string | number;
  centerLabel?: string;
  size?: number;
}) {
  const total = segments.reduce((s, seg) => s + seg.value, 0) || 1;
  let offset = 0;
  return (
    <div className="donut">
      <svg
        className="donut__svg"
        width={size}
        height={size}
        viewBox="0 0 120 120"
        role="img"
        aria-label={`Distribution: ${segments.map((s) => `${s.label} ${s.value}`).join(', ')}`}
      >
        <g transform="rotate(-90 60 60)">
          <circle cx="60" cy="60" r="46" fill="none" stroke="var(--surface-3)" strokeWidth="15" />
          {segments.map((seg) => {
            const pct = (seg.value / total) * 100;
            const el = (
              <circle
                key={seg.label}
                className="donut__seg"
                cx="60"
                cy="60"
                r="46"
                fill="none"
                stroke={toneColor(seg.tone)}
                strokeWidth="15"
                pathLength={100}
                strokeDasharray={`${pct} ${100 - pct}`}
                strokeDashoffset={-offset}
              />
            );
            offset += pct;
            return el;
          })}
        </g>
        {centerValue !== undefined && (
          <text x="60" y="59" textAnchor="middle" className="donut__center-value">
            {centerValue}
          </text>
        )}
        {centerLabel && (
          <text x="60" y="74" textAnchor="middle" className="donut__center-label">
            {centerLabel.toUpperCase()}
          </text>
        )}
      </svg>
      <Legend items={segments.map((s) => ({ label: s.label, value: s.value, tone: s.tone }))} />
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Stacked horizontal distribution bar                                        */
/* -------------------------------------------------------------------------- */
export function DistributionBar({ segments }: { segments: DonutSegment[] }) {
  const total = segments.reduce((s, seg) => s + seg.value, 0) || 1;
  return (
    <div className="stack stack--sm">
      <div className="hbar" role="img" aria-label="Distribution bar">
        {segments
          .filter((s) => s.value > 0)
          .map((seg) => (
            <span
              key={seg.label}
              className="hbar__seg"
              style={{ width: `${(seg.value / total) * 100}%`, background: toneColor(seg.tone) }}
              title={`${seg.label}: ${seg.value}`}
            />
          ))}
      </div>
      <Legend items={segments.map((s) => ({ label: s.label, value: s.value, tone: s.tone }))} />
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Bar list (category comparisons)                                            */
/* -------------------------------------------------------------------------- */
export interface BarRow {
  label: string;
  value: number;
  display?: string;
  tone?: Tone;
}

export function BarList({ rows }: { rows: BarRow[] }) {
  const max = Math.max(...rows.map((r) => r.value), 1);
  return (
    <div className="barlist">
      {rows.map((r) => (
        <div key={r.label} className="barlist__row">
          <span className="barlist__label" title={r.label}>
            {r.label}
          </span>
          <span className="barlist__track">
            <span
              className="barlist__fill"
              style={{
                width: `${(r.value / max) * 100}%`,
                background: r.tone ? toneColor(r.tone) : undefined,
              }}
            />
          </span>
          <span className="barlist__value">{r.display ?? r.value}</span>
        </div>
      ))}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Grouped activity bar chart (scanned vs flagged)                            */
/* -------------------------------------------------------------------------- */
export function ActivityChart({ points }: { points: ActivityPoint[] }) {
  const VIEW_W = 340;
  const PAD_L = 6;
  const PAD_R = 6;
  const BASE_Y = 104;
  const PLOT_H = 92;
  const plotW = VIEW_W - PAD_L - PAD_R;
  const n = Math.max(points.length, 1);
  const groupW = plotW / n;
  const barW = Math.min(groupW * 0.3, 16);
  const max = Math.max(...points.flatMap((p) => [p.scanned, p.flagged]), 1);
  const gridYs = [0, 0.25, 0.5, 0.75, 1];

  return (
    <div className="stack stack--sm">
      <div className="chart">
        <svg viewBox={`0 0 ${VIEW_W} 124`} role="img" aria-label="Packages scanned and flagged over time">
          <g className="chart__grid">
            {gridYs.map((g) => (
              <line key={g} x1={PAD_L} x2={VIEW_W - PAD_R} y1={BASE_Y - g * PLOT_H} y2={BASE_Y - g * PLOT_H} />
            ))}
          </g>
          <g className="chart__axis">
            {points.map((p, i) => {
              const gx = PAD_L + i * groupW + groupW / 2;
              const sH = (p.scanned / max) * PLOT_H;
              const fH = (p.flagged / max) * PLOT_H;
              return (
                <g key={p.label}>
                  <rect
                    className="chart__bar"
                    x={gx - barW - 1}
                    y={BASE_Y - sH}
                    width={barW}
                    height={sH}
                    rx={2}
                  >
                    <title>{`${p.label}: ${p.scanned} scanned`}</title>
                  </rect>
                  <rect
                    x={gx + 1}
                    y={BASE_Y - fH}
                    width={barW}
                    height={fH}
                    rx={2}
                    fill="var(--tone-critical)"
                  >
                    <title>{`${p.label}: ${p.flagged} flagged`}</title>
                  </rect>
                  <text x={gx} y={BASE_Y + 14} textAnchor="middle">
                    {p.label}
                  </text>
                </g>
              );
            })}
          </g>
        </svg>
      </div>
      <div className="row" style={{ gap: 'var(--space-4)' }}>
        <span className="legend__item">
          <span className="legend__swatch" style={{ background: 'var(--accent)' }} aria-hidden />
          <span className="legend__label">Scanned</span>
        </span>
        <span className="legend__item">
          <span className="legend__swatch" style={{ background: 'var(--tone-critical)' }} aria-hidden />
          <span className="legend__label">Flagged for review</span>
        </span>
      </div>
    </div>
  );
}
