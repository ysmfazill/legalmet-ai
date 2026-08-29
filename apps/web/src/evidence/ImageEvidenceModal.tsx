/**
 * Image evidence modal (Prompt 7, Phase 11).
 *
 * Opens when the inspector acts on an IMAGE / REGION / OCR node: it shows the
 * REAL stored image (bearer-authenticated blob) with the perception overlays
 * re-used from the PerceptionViewer, and highlights the specific region the
 * trace points at. This is the "show me the pixels" answer to any trace step.
 *
 * Read-only: the modal renders what the pipeline recorded, nothing more.
 */
import { useMemo } from 'react';

import { api } from '../api/client';
import { Drawer } from '../components/Drawer';
import { Icon } from '../components/Icon';
import { PerceptionViewer } from '../perception/PerceptionViewer';
import { useAsync } from '../data/useAsync';
import type { ImageRegion, OcrTextResult, PackageImage } from '@legalmet/types';

export function ImageEvidenceModal({
  inspectionId,
  imageId,
  highlightRegionId,
  onClose,
}: {
  inspectionId: string;
  imageId: string;
  /** Region to highlight (e.g. the OCR line backing a field). */
  highlightRegionId?: string | null;
  onClose: () => void;
}) {
  const query = useAsync(
    async () => {
      const [images, ocr, regions] = await Promise.all([
        api.listImages(inspectionId),
        api.listOcrResults(inspectionId),
        api.listRegions(inspectionId),
      ]);
      return { images, ocr, regions };
    },
    [inspectionId],
  );

  const image: PackageImage | null =
    query.status === 'success'
      ? (query.data.images.find((img) => img.id === imageId) ?? null)
      : null;

  const ocrLines: OcrTextResult[] = useMemo(
    () =>
      query.status === 'success'
        ? query.data.ocr.filter((o) => o.imageId === imageId)
        : [],
    [query, imageId],
  );

  const regions: ImageRegion[] = useMemo(
    () =>
      query.status === 'success'
        ? query.data.regions.filter((r) => r.imageId === imageId)
        : [],
    [query, imageId],
  );

  // Highlight region: the explicitly requested one, or the region of the OCR
  // line it refers to.
  const selectedRegionId =
    highlightRegionId ??
    (ocrLines.length === 1 ? ocrLines[0].regionId ?? null : null);

  return (
    <Drawer
      wide
      title={image ? image.originalFilename : 'Image evidence'}
      subtitle="Real stored image with the traced perception overlays"
      onClose={onClose}
    >
      <div className="stack">
        <p className="demo-note demo-note--block" style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}>
          <Icon name="info" size={15} />
          <span>
            <strong>Perception evidence only.</strong> The overlays below are the real OCR lines and
            detected regions the traceability graph refers to — they say what the system saw, not
            whether the package is legally compliant.
          </span>
        </p>

        {query.status === 'loading' && <p style={{ color: 'var(--text-muted)' }}>Loading image…</p>}
        {query.status === 'error' && (
          <p style={{ color: 'var(--text-muted)' }}>
            Image evidence unavailable ({query.error.message}).
          </p>
        )}
        {query.status === 'success' && !image && (
          <p style={{ color: 'var(--text-muted)' }}>
            This image is not part of the inspection's current image set.
          </p>
        )}
        {image && (
          <PerceptionViewer
            image={image}
            ocrLines={ocrLines}
            symbolRegions={regions.filter(
              (r) => r.regionType === 'QR_CODE' || r.regionType === 'BARCODE',
            )}
            selectedRegionId={selectedRegionId}
          />
        )}
      </div>
    </Drawer>
  );
}
