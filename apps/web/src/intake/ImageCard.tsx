import type { PackageImage } from '@legalmet/types';

import {
  ImageProcessingBadge,
  ImageQualityGradeBadge,
} from '../components/Badge';
import { Icon } from '../components/Icon';
import { formatBytes, formatRelative } from '../lib/format';
import { useObjectUrl } from './useObjectUrl';

interface ImageCardProps {
  image: PackageImage;
  onRemove: (image: PackageImage) => void;
  onPrepare: (image: PackageImage) => void;
  /** Disables actions while a mutation for this image is in flight. */
  busy?: boolean;
}

/**
 * A single stored intake image: real thumbnail (bearer-auth blob), provenance
 * and the deterministic usability grade. Deliberately shows NO OCR text and NO
 * compliance verdict — none exists at intake time.
 */
export function ImageCard({ image, onRemove, onPrepare, busy = false }: ImageCardProps) {
  const thumb = useObjectUrl(image.processedStorageKey ?? image.storageKey);
  const dimensions =
    image.width && image.height ? `${image.width} × ${image.height}` : 'Dimensions pending';
  const shortChecksum = image.checksum ? `${image.checksum.slice(0, 10)}…` : '—';
  const canPrepare = image.processingStatus !== 'READY' && image.processingStatus !== 'PROCESSING';

  return (
    <div className="intake-card">
      <div className="intake-card__thumb">
        {thumb.status === 'ready' ? (
          <img src={thumb.url} alt={image.originalFilename} loading="lazy" />
        ) : thumb.status === 'loading' ? (
          <span className="spinner" aria-hidden />
        ) : (
          <span className="intake-card__thumb-fallback" title={thumb.message}>
            <Icon name="image" size={22} />
          </span>
        )}
      </div>

      <div className="intake-card__body">
        <div className="row row--between" style={{ gap: 'var(--space-2)' }}>
          <span className="cell-strong intake-card__name" title={image.originalFilename}>
            {image.originalFilename}
          </span>
          {image.qualityGrade && <ImageQualityGradeBadge grade={image.qualityGrade} />}
        </div>

        <div className="row row--wrap" style={{ gap: 'var(--space-2)' }}>
          <span className="tag">{image.captureSource}</span>
          <span className="tag">{image.imageType}</span>
          <ImageProcessingBadge status={image.processingStatus} />
        </div>

        <dl className="intake-card__meta">
          <div>
            <dt>Resolution</dt>
            <dd>{dimensions}</dd>
          </div>
          <div>
            <dt>Size</dt>
            <dd>{formatBytes(image.fileSize)}</dd>
          </div>
          <div>
            <dt>Usability</dt>
            <dd>{image.qualityScore != null ? `${Math.round(image.qualityScore * 100)}/100` : '—'}</dd>
          </div>
          <div>
            <dt>Checksum</dt>
            <dd title={image.checksum ?? undefined}>{shortChecksum}</dd>
          </div>
          <div>
            <dt>Added</dt>
            <dd>{formatRelative(image.createdAt)}</dd>
          </div>
        </dl>

        <div className="row" style={{ gap: 'var(--space-2)' }}>
          <button
            type="button"
            className="btn btn--subtle btn--sm"
            onClick={() => onPrepare(image)}
            disabled={busy || !canPrepare}
            title={canPrepare ? 'Generate a metadata-stripped, resized derivative' : 'Derivative already prepared'}
          >
            <Icon name="layers" size={14} />
            {image.processingStatus === 'READY' ? 'Prepared' : 'Preprocess'}
          </button>
          <button
            type="button"
            className="btn btn--ghost btn--sm"
            onClick={() => onRemove(image)}
            disabled={busy}
          >
            <Icon name="close" size={14} />
            Remove
          </button>
        </div>
      </div>
    </div>
  );
}
