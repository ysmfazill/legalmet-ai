// @vitest-environment jsdom
//
// Regression test for the Evidence Explorer image bug: the /inspections LIST
// endpoint returns summaries WITHOUT packages/images/product, so the evidence
// read-model must fetch each inspection's DETAIL to obtain the stored package
// image. If this fetch disappears, every imageStorageKey becomes null and no
// package photo ever renders on the Evidence page.

import { cleanup, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type {
  EngineFinding,
  ExtractedField,
  ImageRegion,
  Inspection,
  OcrTextResult,
  PackageImage,
} from '@legalmet/types';

const listInspections = vi.fn();
const getInspection = vi.fn();
const listFields = vi.fn();
const listEngineFindings = vi.fn();
const listRegions = vi.fn();
const listOcrResults = vi.fn();

vi.mock('../api/client', () => ({
  api: {
    listInspections: (...a: unknown[]) => listInspections(...a),
    getInspection: (...a: unknown[]) => getInspection(...a),
    listFields: (...a: unknown[]) => listFields(...a),
    listEngineFindings: (...a: unknown[]) => listEngineFindings(...a),
    listRegions: (...a: unknown[]) => listRegions(...a),
    listOcrResults: (...a: unknown[]) => listOcrResults(...a),
  },
}));

import { useLiveEvidence } from './useLiveEvidence';

// --- fixtures ----------------------------------------------------------------

/** LIST-shape summary: what GET /inspections actually returns (no packages). */
function listShapeInspection(overrides: Partial<Inspection> = {}): Inspection {
  return {
    id: 'i1',
    referenceNo: 'LM-00012345',
    status: 'CREATED',
    productId: 'p1',
    // The list endpoint does NOT embed product/packages — this is the bug
    // surface. (The type allows them; the wire format omits them.)
    product: null,
    packages: [],
    inspectorId: 'u1',
    inspectorName: 'Inspector',
    batchId: null,
    note: null,
    isDemo: false,
    createdAt: '2026-09-03T10:00:00Z',
    updatedAt: '2026-09-03T10:00:00Z',
    completedAt: null,
    ...overrides,
  } as Inspection;
}

function detailShapeInspection(): Inspection {
  const image: PackageImage = {
    id: 'img1',
    packageId: 'pkg1',
    storageKey: 'packages/demo-photo.png',
    originalFilename: 'demo-photo.png',
    mimeType: 'image/png',
    width: 1000,
    height: 624,
    imageType: 'FRONT',
    qualityStatus: 'OK',
    isDemo: false,
    createdAt: '2026-09-03T10:00:00Z',
    captureSource: 'CAMERA',
    processingStatus: 'READY',
  } as PackageImage;
  return {
    ...listShapeInspection(),
    product: { id: 'p1', name: 'DEMO Tea 250g' } as Inspection['product'],
    packages: [{ id: 'pkg1', images: [image] }] as Inspection['packages'],
  };
}

function extractedField(): ExtractedField {
  return {
    id: 'f1',
    imageId: 'img1',
    imageRegionId: 'reg1',
    packageId: 'pkg1',
    fieldType: 'MRP',
    rawText: 'MRP Rs 120',
    normalizedValue: '120',
    unit: 'INR',
    confidence: 0.92,
    extractionMethod: 'OCR',
    isDemo: false,
    createdAt: '2026-09-03T10:05:00Z',
    status: 'DETECTED',
    sourceOcrResultId: 'ocr1',
  } as ExtractedField;
}

const region: ImageRegion = {
  id: 'reg1',
  imageId: 'img1',
  regionType: 'TEXT_BLOCK',
  bbox: { x: 0.1, y: 0.2, width: 0.3, height: 0.05 },
  confidence: 0.9,
  createdAt: '2026-09-03T10:05:00Z',
} as ImageRegion;

const ocrLine: OcrTextResult = {
  id: 'ocr1',
  imageId: 'img1',
  processingRunId: 'run1',
  rawText: 'MRP Rs 120',
  bbox: { x: 0.11, y: 0.21, width: 0.28, height: 0.04 },
  confidence: 0.94,
  provider: 'paddleocr',
  modelName: 'paddle',
  modelVersion: '1',
  createdAt: '2026-09-03T10:05:00Z',
} as OcrTextResult;

const finding: EngineFinding = {
  id: 'ef1',
  evaluationId: 'ev1',
  inspectionId: 'i1',
  requirementId: 'req1',
  extractedFieldId: 'f1',
  status: 'VIOLATION',
  severity: 'MAJOR',
  applicability: 'APPLICABLE',
  explanation: 'MRP below the declared value.',
  provenance: 'ENGINE',
  detail: {},
  reviewState: 'PENDING_REVIEW',
  createdAt: '2026-09-03T10:06:00Z',
  boundaryNote: '',
} as unknown as EngineFinding;

// -----------------------------------------------------------------------------

beforeEach(() => {
  vi.clearAllMocks();
  // The wire shapes the real backend returns.
  listInspections.mockResolvedValue({
    items: [listShapeInspection()],
    page: 1,
    pageSize: 100,
    total: 1,
    totalPages: 1,
  });
  getInspection.mockResolvedValue(detailShapeInspection());
  listFields.mockResolvedValue([extractedField()]);
  listEngineFindings.mockResolvedValue([finding]);
  listRegions.mockResolvedValue([region]);
  listOcrResults.mockResolvedValue([ocrLine]);
});

afterEach(cleanup);

describe('useLiveEvidence (evidence image data flow)', () => {
  it('populates image storage key + metadata from the DETAIL fetch (list omits packages)', async () => {
    const { result } = renderHook(() => useLiveEvidence(true));

    await waitFor(() => expect(result.current.status).toBe('success'), { timeout: 3000 });
    const item = result.current.data!.items[0];

    // The real stored image — this is what makes the Evidence page render
    // the actual package photo. Null here = the original bug.
    expect(item.imageStorageKey).toBe('packages/demo-photo.png');
    expect(item.imageMimeType).toBe('image/png');
    expect(item.imageWidth).toBe(1000);
    expect(item.imageHeight).toBe(624);

    // Product name comes from the detail response too.
    expect(item.productName).toBe('DEMO Tea 250g');

    // The detail endpoint was actually consulted per inspection.
    expect(getInspection).toHaveBeenCalledWith('i1');
  });

  it('binds the field to its real region, OCR line and finding', async () => {
    const { result } = renderHook(() => useLiveEvidence(true));

    await waitFor(() => expect(result.current.status).toBe('success'), { timeout: 3000 });
    const item = result.current.data!.items[0];

    expect(item.region).toEqual(region.bbox);
    expect(item.rawText).toBe('MRP Rs 120');
    expect(item.findingStatus).toBe('VIOLATION');
    expect(item.findingSeverity).toBe('MAJOR');
  });

  it('falls back to the OCR bbox when the field has no dedicated region', async () => {
    listFields.mockResolvedValue([{ ...extractedField(), imageRegionId: null }]);

    const { result } = renderHook(() => useLiveEvidence(true));

    await waitFor(() => expect(result.current.status).toBe('success'), { timeout: 3000 });
    expect(result.current.data!.items[0].region).toEqual(ocrLine.bbox);
  });

  it('detects pending inspections (images, no fields) via the detail images', async () => {
    listFields.mockResolvedValue([]);

    const { result } = renderHook(() => useLiveEvidence(true));

    await waitFor(() => expect(result.current.status).toBe('success'), { timeout: 3000 });
    expect(result.current.data!.items).toHaveLength(0);
    // The list item alone carries no images — only the detail fetch can see
    // that this inspection has a stored photo awaiting perception.
    expect(result.current.data!.pendingInspections.map((i) => i.id)).toEqual(['i1']);
  });

  it('never fabricates a region: no region and no OCR line → null', async () => {
    listRegions.mockResolvedValue([]);
    listOcrResults.mockResolvedValue([]);
    listFields.mockResolvedValue([
      { ...extractedField(), imageRegionId: null, sourceOcrResultId: null },
    ]);

    const { result } = renderHook(() => useLiveEvidence(true));

    await waitFor(() => expect(result.current.status).toBe('success'), { timeout: 3000 });
    expect(result.current.data!.items[0].region).toBeNull();
  });
});
