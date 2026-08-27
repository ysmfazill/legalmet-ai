/**
 * Presentation formatters. Pure, dependency-free, and safe on `null`/`undefined`
 * so tables never crash on partial data.
 */
import { CONFIDENCE_THRESHOLDS } from '@legalmet/config';
import type { Tone } from '@legalmet/config';

const DATE_FMT: Intl.DateTimeFormatOptions = { day: '2-digit', month: 'short', year: 'numeric' };
const TIME_FMT: Intl.DateTimeFormatOptions = { hour: '2-digit', minute: '2-digit', hour12: false };

export function formatDate(iso?: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleDateString('en-GB', DATE_FMT);
}

export function formatDateTime(iso?: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return `${d.toLocaleDateString('en-GB', DATE_FMT)}, ${d.toLocaleTimeString('en-GB', TIME_FMT)}`;
}

/** Compact relative time ("3h ago", "2d ago"). */
export function formatRelative(iso?: string | null): string {
  if (!iso) return '—';
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return '—';
  const diff = Date.now() - then;
  const mins = Math.round(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.round(hrs / 24);
  if (days < 30) return `${days}d ago`;
  return formatDate(iso);
}

/** Fraction in 0..1 → percentage string. */
export function formatPercent(fraction: number, digits = 0): string {
  return `${(fraction * 100).toFixed(digits)}%`;
}

/** Human-readable byte size ("2.4 MB", "812 KB"). Safe on null/undefined. */
export function formatBytes(bytes?: number | null): string {
  if (bytes == null || Number.isNaN(bytes)) return '—';
  if (bytes < 1024) return `${bytes} B`;
  const units = ['KB', 'MB', 'GB'];
  let value = bytes / 1024;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(value >= 10 ? 0 : 1)} ${units[unit]}`;
}

export type ConfidenceBand = 'high' | 'medium' | 'low';

export function confidenceBand(fraction: number): ConfidenceBand {
  if (fraction >= CONFIDENCE_THRESHOLDS.high) return 'high';
  if (fraction >= CONFIDENCE_THRESHOLDS.medium) return 'medium';
  return 'low';
}

export const CONFIDENCE_TONE: Record<ConfidenceBand, Tone> = {
  high: 'positive',
  medium: 'warning',
  low: 'critical',
};

/** Fallback humaniser for enum-like SCREAMING_SNAKE values without explicit meta. */
export function humanizeEnum(value: string): string {
  return value
    .toLowerCase()
    .split('_')
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ');
}
