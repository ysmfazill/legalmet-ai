import { BarList } from '../components/charts';
import { ImageQualityGradeBadge } from '../components/Badge';
import { Icon } from '../components/Icon';
import type { PackageImage } from '@legalmet/types';

import { readQuality, usabilityTone } from './quality';

/**
 * Deterministic image-usability readout for a real uploaded image.
 *
 * Renders the analyzer's component scores as bars plus a few raw facts. The
 * copy is explicit and non-negotiable: this is a legibility signal for later
 * analysis — NOT AI confidence, NOT compliance confidence, NOT a legal verdict.
 */
export function QualityReadout({ image, compact = false }: { image: PackageImage; compact?: boolean }) {
  const readout = readQuality(image.qualityMetrics, image.qualityScore, image.qualityGrade);
  const overallPct = readout.overall != null ? Math.round(readout.overall * 100) : null;

  return (
    <div className="stack stack--sm">
      <div className="row row--between row--wrap" style={{ gap: 'var(--space-2)' }}>
        <span className="row" style={{ gap: 'var(--space-2)' }}>
          {readout.grade && <ImageQualityGradeBadge grade={readout.grade} />}
          {overallPct != null && (
            <span className="badge badge--square" title="Overall usability score (0–100)">
              {overallPct}/100
            </span>
          )}
        </span>
        {!compact && (
          <span className="cell-muted" style={{ fontSize: 'var(--fs-sm)' }}>
            Usability score
          </span>
        )}
      </div>

      {readout.components.length > 0 && (
        <BarList
          rows={readout.components.map((c) => ({
            label: c.label,
            value: Math.round(c.score * 100),
            display: `${Math.round(c.score * 100)}%`,
            tone: usabilityTone(c.score),
          }))}
        />
      )}

      {readout.facts.length > 0 && (
        <div className="row row--wrap" style={{ gap: 'var(--space-3)' }}>
          {readout.facts.map((f) => (
            <span key={f.label} className="cell-muted" style={{ fontSize: 'var(--fs-sm)' }}>
              <strong>{f.label}:</strong> {f.value}
            </span>
          ))}
        </div>
      )}

      <p className="demo-note" style={{ fontSize: 'var(--fs-sm)' }}>
        <Icon name="info" size={13} />
        <span>
          <strong>Image usability only.</strong> This measures whether the label is legible enough to
          analyse later — it is not an AI-confidence, accuracy, or Legal-Metrology-compliance score.
        </span>
      </p>
    </div>
  );
}
