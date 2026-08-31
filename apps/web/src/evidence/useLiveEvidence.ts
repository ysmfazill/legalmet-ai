/**
 * LIVE evidence read-model for the Evidence Explorer (Prompt 11, Phase 7).
 *
 * Walks the REAL backend inspections, keeps the ones with perception
 * evidence, and flattens each extracted field into an evidence card row:
 * the stored image (rendered as a real thumbnail via the authenticated
 * object-URL fetch), the field's bounding-box region on that image, the
 * verbatim OCR line, and the finding status when the deterministic engine
 * evaluated it.
 *
 * Demo (mock) evidence never flows through here — the page renders the two
 * sources side by side, each clearly labelled.
 */
import { useAsync } from '../data/useAsync';
import { api } from '../api/client';
import type {
  BoundingBox,
  EngineFinding,
  ExtractedField,
  ImageRegion,
  Inspection,
} from '@legalmet/types';

export interface LiveEvidenceItem {
  fieldId: string;
  inspectionId: string;
  referenceNo: string;
  productName: string;
  imageStorageKey: string | null;
  /** Fractional bbox on the image, or null when the field has no region. */
  region: BoundingBox | null;
  fieldType: ExtractedField['fieldType'];
  value: string;
  rawText: string;
  confidence: number;
  status: ExtractedField['status'];
  findingStatus: string | null;
  findingSeverity: string | null;
}

export interface LiveEvidenceData {
  inspections: Inspection[];
  items: LiveEvidenceItem[];
  /** inspections that have images but no perception evidence yet. */
  pendingInspections: Inspection[];
}

export function useLiveEvidence(enabled: boolean) {
  return useAsync<LiveEvidenceData>(async () => {
    const page = await api.listInspections({ page: 1, pageSize: 100 });
    const inspections = page.items ?? [];

    const items: LiveEvidenceItem[] = [];
    const pending: Inspection[] = [];
    const findingsByField = new Map<string, EngineFinding>();

    for (const inspection of inspections) {
      const fields = await api.listFields(inspection.id);
      if (fields.length === 0) {
        if ((inspection.packages ?? []).some((p) => (p.images ?? []).length > 0)) {
          pending.push(inspection);
        }
        continue;
      }

      // Findings (if the engine has run) map extracted fields to statuses.
      try {
        const findings = await api.listEngineFindings(inspection.id);
        for (const f of findings) {
          if (f.extractedFieldId) findingsByField.set(f.extractedFieldId, f);
        }
      } catch {
        // No evaluation yet — evidence cards simply show no finding status.
      }

      const regions = await api.listRegions(inspection.id);
      const ocr = await api.listOcrResults(inspection.id);
      const regionsById = new Map(regions.map((r) => [r.id, r]));
      const ocrById = new Map(ocr.map((o) => [o.id, o]));
      const images =
        (inspection.packages ?? []).flatMap((p) => p.images ?? []) ?? [];
      const imagesById = new Map(images.map((i) => [i.id, i]));

      for (const field of fields) {
        const region = field.imageRegionId
          ? regionsById.get(field.imageRegionId)
          : undefined;
        const ocrLine = field.sourceOcrResultId
          ? ocrById.get(field.sourceOcrResultId)
          : undefined;
        const image = field.imageId ? imagesById.get(field.imageId) : undefined;
        const finding = findingsByField.get(field.id);
        items.push({
          fieldId: field.id,
          inspectionId: inspection.id,
          referenceNo: inspection.referenceNo,
          productName: inspection.product?.name ?? inspection.referenceNo,
          imageStorageKey: image?.storageKey ?? null,
          region: region?.bbox ?? ocrLine?.bbox ?? null,
          fieldType: field.fieldType,
          value: field.correctedValue ?? field.normalizedValue ?? field.rawText,
          rawText: ocrLine?.rawText ?? field.rawText,
          confidence: field.confidence,
          status: field.status,
          findingStatus: finding?.status ?? null,
          findingSeverity: finding?.severity ?? null,
        });
      }
    }

    return { inspections, items, pendingInspections: pending };
  }, [enabled]);
}

export type { ImageRegion };
