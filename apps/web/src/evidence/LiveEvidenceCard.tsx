/**
 * LIVE evidence card with a REAL package-image thumbnail (Prompt 11, Phase 7).
 *
 * The thumbnail is the actual stored inspection image, fetched through the
 * bearer-authenticated `/storage` route as a blob URL — never a placeholder
 * graphic. The field's evidence region is drawn over the real pixels as a
 * fractional bounding box. When the field has no region, the card says
 * REGION NOT AVAILABLE instead of inventing coordinates.
 */
import { memo } from 'react';

import { FIELD_TYPE_LABELS } from '@legalmet/config';
import type { LiveEvidenceItem } from './useLiveEvidence';

import { ExtractionStatusBadge } from '../components/Badge';
import { Icon } from '../components/Icon';
import { useObjectUrl } from '../intake/useObjectUrl';
import { formatPercent } from '../lib/format';

export const LiveEvidenceCard = memo(function LiveEvidenceCard({
  item,
  onOpen,
}: {
  item: LiveEvidenceItem;
  onOpen: (item: LiveEvidenceItem) => void;
}) {
  const view = useObjectUrl(item.imageStorageKey);

  return (
    <button
      type="button"
      className="evi-card"
      onClick={() => onOpen(item)}
      title="Open this evidence in the inspection workspace"
    >
      <div className="evi-card__thumb evi-card__thumb--real" aria-hidden>
        {view.status === 'ready' ? (
          <img src={view.url} alt="" draggable={false} />
        ) : view.status === 'loading' ? (
          <span className="spinner" aria-hidden />
        ) : (
          <span className="evi-card__thumb-missing">
            <Icon name="image" size={18} />
          </span>
        )}
        {view.status === 'ready' &&
          (item.region ? (
            <div
              className="evi-card__region"
              style={{
                left: `${item.region.x * 100}%`,
                top: `${item.region.y * 100}%`,
                width: `${item.region.width * 100}%`,
                height: `${item.region.height * 100}%`,
              }}
            />
          ) : (
            <span className="evi-card__no-region">REGION NOT AVAILABLE</span>
          ))}
      </div>
      <div className="evi-card__body">
        <span className="eyebrow">{FIELD_TYPE_LABELS[item.fieldType]}</span>
        <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 'var(--fw-semibold)' }}>
          {item.value}
        </span>
        <span className="cell-muted" style={{ fontSize: 'var(--fs-sm)' }}>
          {item.referenceNo} · {item.productName}
        </span>
        <span
          className="cell-muted"
          style={{ fontSize: 'var(--fs-xs)', fontFamily: 'var(--font-mono)' }}
          title="Verbatim OCR line this value came from"
        >
          “{item.rawText}”
        </span>
        <div className="row row--between" style={{ marginTop: 'var(--space-2)' }}>
          <ExtractionStatusBadge status={item.status} />
          <span className="decl__conf" title="OCR confidence × pattern weight">
            {formatPercent(item.confidence)}
          </span>
        </div>
        {item.findingStatus && (
          <span
            className="tag"
            style={{ marginTop: 4, alignSelf: 'flex-start' }}
            title="Deterministic engine finding for this declaration"
          >
            engine: {item.findingStatus.replaceAll('_', ' ').toLowerCase()}
            {item.findingSeverity ? ` · ${item.findingSeverity.toLowerCase()}` : ''}
          </span>
        )}
      </div>
    </button>
  );
});
