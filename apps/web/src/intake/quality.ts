/**
 * Read the backend's deterministic image-usability metrics into display shapes.
 *
 * The analyzer (`services/api/app/services/quality/pillow.py`) returns a flat
 * camelCase dict. These helpers pull values out defensively — the payload is
 * typed as arbitrary `Json`, and a missing/renamed key must degrade gracefully
 * rather than throw in the UI.
 *
 * CRITICAL FRAMING: every number here is an IMAGE USABILITY signal (is the
 * label legible enough to analyse later?). It is NOT AI confidence, NOT
 * compliance confidence, and NOT a legal judgement. UI copy must say so.
 */
import type { ImageQualityGrade, Json } from '@legalmet/types';

export interface QualityComponent {
  key: string;
  label: string;
  /** 0..1 usability component. */
  score: number;
}

export interface QualityReadout {
  /** 0..1 overall usability (mirrors `PackageImage.qualityScore`). */
  overall: number | null;
  grade: ImageQualityGrade | null;
  components: QualityComponent[];
  facts: { label: string; value: string }[];
}

function num(metrics: Record<string, unknown>, key: string): number | null {
  const value = metrics[key];
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

const COMPONENT_KEYS: { key: string; label: string }[] = [
  { key: 'resolutionScore', label: 'Resolution' },
  { key: 'sharpnessScore', label: 'Sharpness' },
  { key: 'contrastScore', label: 'Contrast' },
  { key: 'brightnessScore', label: 'Lighting' },
];

/** Normalise an image's quality payload into rows the UI can render. */
export function readQuality(
  qualityMetrics: Json | null | undefined,
  qualityScore: number | null | undefined,
  qualityGrade: ImageQualityGrade | null | undefined,
): QualityReadout {
  const metrics =
    qualityMetrics && typeof qualityMetrics === 'object' && !Array.isArray(qualityMetrics)
      ? (qualityMetrics as Record<string, unknown>)
      : {};

  const components: QualityComponent[] = [];
  for (const { key, label } of COMPONENT_KEYS) {
    const score = num(metrics, key);
    if (score !== null) components.push({ key, label, score: Math.max(0, Math.min(1, score)) });
  }

  const facts: { label: string; value: string }[] = [];
  const width = num(metrics, 'width');
  const height = num(metrics, 'height');
  if (width !== null && height !== null) facts.push({ label: 'Resolution', value: `${width} × ${height}` });
  const megapixels = num(metrics, 'megapixels');
  if (megapixels !== null) facts.push({ label: 'Megapixels', value: `${megapixels.toFixed(1)} MP` });

  return {
    overall: typeof qualityScore === 'number' ? qualityScore : null,
    grade: qualityGrade ?? null,
    components,
    facts,
  };
}

/** Score (0..1) → design-system tone, purely for the usability bars. */
export function usabilityTone(score: number): 'positive' | 'warning' | 'critical' {
  return score >= 0.75 ? 'positive' : score >= 0.5 ? 'warning' : 'critical';
}
