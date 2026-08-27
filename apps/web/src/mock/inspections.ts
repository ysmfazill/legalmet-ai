/**
 * DEMO inspection details — fully interlinked package → image → region →
 * extracted field → rule → validation → finding chains for the workspace and
 * the WHY / Evidence experience.
 *
 * ⚠ DEMO DATA — NOT LEGAL ADVICE.
 */
import type { Inspection, Product } from '@legalmet/types';
import type { Tone } from '@legalmet/config';

import { RULE_REFS, assistanceScore, countsFrom } from './fixtures';
import type {
  ChainNode,
  DetectedDeclaration,
  FindingView,
  InspectionDetail,
  QualityMetric,
  ViewerRegion,
} from './types';

function product(id: string, name: string, category: string): Product {
  return { id, name, category, isDemo: true, createdAt: '2026-01-01T00:00:00Z' };
}

const STATUS_TONE = {
  COMPLIANT: 'positive',
  POTENTIAL_VIOLATION: 'critical',
  REVIEW_REQUIRED: 'warning',
  NOT_APPLICABLE: 'neutral',
  LOW_CONFIDENCE: 'warning',
  IMAGE_QUALITY_INSUFFICIENT: 'warning',
} as const satisfies Record<FindingView['status'], Tone>;

/** Build the ordered, human-readable evidence chain for a finding. */
function chain(args: {
  pkg: string;
  region: string | null;
  fieldLabel: string;
  detectedValue: string;
  ruleCode: string;
  ruleTitle: string;
  expected: string;
  detected: string;
  result: string;
  finding: string;
}): ChainNode[] {
  const nodes: ChainNode[] = [
    { type: 'PACKAGE', label: args.pkg },
    { type: 'IMAGE', label: 'Front label image', detail: 'Captured · demo' },
  ];
  if (args.region) {
    nodes.push({ type: 'IMAGE_REGION', label: args.region, detail: 'Highlighted region' });
  } else {
    nodes.push({ type: 'IMAGE_REGION', label: 'No region detected', detail: 'Expected, absent' });
  }
  nodes.push(
    { type: 'EXTRACTED_FIELD', label: args.detectedValue, detail: args.fieldLabel },
    { type: 'RULE', label: `${args.ruleCode} · ${args.ruleTitle}`, detail: 'Demo v3.0' },
    {
      type: 'VALIDATION_RESULT',
      label: args.result,
      detail: `Expected: ${args.expected} · Detected: ${args.detected}`,
    },
    { type: 'FINDING', label: args.finding },
  );
  return nodes;
}

/* ========================================================================== */
/* INS-10482 — hero inspection (Classic Salted Namkeen, 200 g)                */
/* ========================================================================== */
const PKG_10482 = 'Classic Salted Namkeen — 200 g';

const findings10482: FindingView[] = [
  {
    id: 'fnd-482-name',
    inspectionId: 'ins-10482',
    title: 'Generic name declared',
    fieldType: 'GENERIC_NAME',
    status: 'COMPLIANT',
    confidence: 0.97,
    risk: 'LOW',
    rationale:
      'A generic/common name region was detected and matched the expected declaration profile for this category.',
    isReviewed: false,
    detectedValue: 'Classic Salted Namkeen',
    regionId: 'rg-name',
    rule: RULE_REFS.mfg,
    expected: 'Generic name present',
    detected: 'Classic Salted Namkeen',
    validationResult: 'PASS',
    chain: chain({
      pkg: PKG_10482,
      region: 'Generic name (text block)',
      fieldLabel: 'Generic / common name',
      detectedValue: 'Classic Salted Namkeen',
      ruleCode: 'DR-GEN-01',
      ruleTitle: 'Generic name',
      expected: 'present',
      detected: 'present',
      result: 'PASS',
      finding: 'Generic name declared',
    }),
    createdAt: '2026-08-22T10:32:00Z',
  },
  {
    id: 'fnd-482-nq',
    inspectionId: 'ins-10482',
    title: 'Net quantity declared in standard units',
    fieldType: 'NET_QUANTITY',
    status: 'COMPLIANT',
    confidence: 0.95,
    risk: 'LOW',
    rationale: 'Net quantity "200 g" detected with a recognised metric unit.',
    isReviewed: false,
    detectedValue: '200 g',
    regionId: 'rg-nq',
    rule: RULE_REFS.nq,
    expected: 'Value + metric unit',
    detected: '200 g',
    validationResult: 'PASS',
    chain: chain({
      pkg: PKG_10482,
      region: 'Net quantity (text line)',
      fieldLabel: 'Net quantity',
      detectedValue: '200 g',
      ruleCode: 'DR-NQ-01',
      ruleTitle: 'Net quantity declaration',
      expected: 'value + metric unit',
      detected: '200 g',
      result: 'PASS',
      finding: 'Net quantity declared in standard units',
    }),
    createdAt: '2026-08-22T10:32:05Z',
  },
  {
    id: 'fnd-482-mrp',
    inspectionId: 'ins-10482',
    title: 'Potential MRP declaration issue',
    fieldType: 'MRP',
    status: 'REVIEW_REQUIRED',
    confidence: 0.96,
    risk: 'HIGH',
    rationale:
      'An MRP value (₹499) was detected clearly, but the "inclusive of all taxes" qualifier expected by DR-MRP-01 (Demo v3.0) was not detected near it. Because the value itself is legible (96% confidence), the system does not auto-conclude — it flags the finding for inspector review.',
    isReviewed: false,
    detectedValue: '₹499',
    regionId: 'rg-mrp',
    rule: RULE_REFS.mrp,
    expected: 'MRP inclusive of all taxes',
    detected: '₹499 (no tax qualifier detected)',
    validationResult: 'INCONCLUSIVE',
    chain: chain({
      pkg: PKG_10482,
      region: 'MRP (text line)',
      fieldLabel: 'Maximum Retail Price',
      detectedValue: '₹499',
      ruleCode: 'DR-MRP-01',
      ruleTitle: 'Maximum Retail Price declaration',
      expected: 'inclusive of all taxes',
      detected: 'no tax qualifier',
      result: 'INCONCLUSIVE → REVIEW REQUIRED',
      finding: 'Potential MRP declaration issue',
    }),
    createdAt: '2026-08-22T10:32:11Z',
  },
  {
    id: 'fnd-482-mfg',
    inspectionId: 'ins-10482',
    title: 'Manufacturer details declared',
    fieldType: 'MANUFACTURER_DETAILS',
    status: 'COMPLIANT',
    confidence: 0.9,
    risk: 'LOW',
    rationale: 'Manufacturer name and address text detected in a single block.',
    isReviewed: false,
    detectedValue: 'Acme Foods Pvt Ltd, Pune 411001',
    regionId: 'rg-mfg',
    rule: RULE_REFS.mfg,
    expected: 'Name + complete address',
    detected: 'Acme Foods Pvt Ltd, Pune 411001',
    validationResult: 'PASS',
    chain: chain({
      pkg: PKG_10482,
      region: 'Manufacturer details (text block)',
      fieldLabel: 'Manufacturer details',
      detectedValue: 'Acme Foods Pvt Ltd, Pune 411001',
      ruleCode: 'DR-MFG-01',
      ruleTitle: 'Manufacturer / packer details',
      expected: 'name + address',
      detected: 'name + address',
      result: 'PASS',
      finding: 'Manufacturer details declared',
    }),
    createdAt: '2026-08-22T10:32:15Z',
  },
  {
    id: 'fnd-482-date',
    inspectionId: 'ins-10482',
    title: 'Date of packing declared',
    fieldType: 'DATE_OF_PACKING',
    status: 'COMPLIANT',
    confidence: 0.88,
    risk: 'LOW',
    rationale: 'A packing date "08/2026" was detected and parsed to a month/year.',
    isReviewed: false,
    detectedValue: '08/2026',
    regionId: 'rg-date',
    rule: RULE_REFS.date,
    expected: 'Month/year present',
    detected: '08/2026',
    validationResult: 'PASS',
    chain: chain({
      pkg: PKG_10482,
      region: 'Date of packing (text line)',
      fieldLabel: 'Date of packing',
      detectedValue: '08/2026',
      ruleCode: 'DR-DATE-01',
      ruleTitle: 'Date of manufacture / packing',
      expected: 'month/year',
      detected: '08/2026',
      result: 'PASS',
      finding: 'Date of packing declared',
    }),
    createdAt: '2026-08-22T10:32:19Z',
  },
  {
    id: 'fnd-482-coo',
    inspectionId: 'ins-10482',
    title: 'Country of origin not detected',
    fieldType: 'COUNTRY_OF_ORIGIN',
    status: 'POTENTIAL_VIOLATION',
    confidence: 0.71,
    risk: 'HIGH',
    rationale:
      'No country-of-origin declaration region was detected on the analysed image. DR-COO-01 (Demo v3.0) expects this declaration for this product context, so its absence is surfaced as a potential violation for inspector confirmation.',
    isReviewed: false,
    detectedValue: 'Not detected',
    regionId: undefined,
    rule: RULE_REFS.coo,
    expected: 'Country of origin present',
    detected: 'Not detected',
    validationResult: 'FAIL',
    chain: chain({
      pkg: PKG_10482,
      region: null,
      fieldLabel: 'Country of origin',
      detectedValue: 'Not detected',
      ruleCode: 'DR-COO-01',
      ruleTitle: 'Country of origin declaration',
      expected: 'present',
      detected: 'absent',
      result: 'FAIL → POTENTIAL VIOLATION',
      finding: 'Country of origin not detected',
    }),
    createdAt: '2026-08-22T10:32:24Z',
  },
  {
    id: 'fnd-482-bb',
    inspectionId: 'ins-10482',
    title: 'Best before declared',
    fieldType: 'BEST_BEFORE',
    status: 'COMPLIANT',
    confidence: 0.86,
    risk: 'LOW',
    rationale: 'A "best before" duration was detected near the packing date.',
    isReviewed: false,
    detectedValue: 'Best before 6 months',
    regionId: 'rg-bb',
    rule: RULE_REFS.date,
    expected: 'Best-before present',
    detected: 'Best before 6 months',
    validationResult: 'PASS',
    chain: chain({
      pkg: PKG_10482,
      region: 'Best before (text line)',
      fieldLabel: 'Best before',
      detectedValue: 'Best before 6 months',
      ruleCode: 'DR-DATE-01',
      ruleTitle: 'Date of manufacture / packing',
      expected: 'present',
      detected: 'present',
      result: 'PASS',
      finding: 'Best before declared',
    }),
    createdAt: '2026-08-22T10:32:28Z',
  },
  {
    id: 'fnd-482-batch',
    inspectionId: 'ins-10482',
    title: 'Batch number declared',
    fieldType: 'BATCH_NUMBER',
    status: 'COMPLIANT',
    confidence: 0.93,
    risk: 'LOW',
    rationale: 'A batch/lot code was detected.',
    isReviewed: false,
    detectedValue: 'LOT AC-8842',
    regionId: 'rg-batch',
    rule: RULE_REFS.mfg,
    expected: 'Batch/lot present',
    detected: 'LOT AC-8842',
    validationResult: 'PASS',
    chain: chain({
      pkg: PKG_10482,
      region: 'Batch number (text line)',
      fieldLabel: 'Batch / lot number',
      detectedValue: 'LOT AC-8842',
      ruleCode: 'DR-MFG-01',
      ruleTitle: 'Manufacturer / packer details',
      expected: 'present',
      detected: 'present',
      result: 'PASS',
      finding: 'Batch number declared',
    }),
    createdAt: '2026-08-22T10:32:31Z',
  },
  {
    id: 'fnd-482-care',
    inspectionId: 'ins-10482',
    title: 'Consumer care details',
    fieldType: 'CONSUMER_CARE',
    status: 'NOT_APPLICABLE',
    confidence: 0.5,
    risk: 'LOW',
    rationale: 'No applicable rule resolved for consumer-care details in this demo product context.',
    isReviewed: false,
    detectedValue: '—',
    regionId: undefined,
    expected: 'n/a',
    detected: 'n/a',
    validationResult: 'INCONCLUSIVE',
    chain: chain({
      pkg: PKG_10482,
      region: null,
      fieldLabel: 'Consumer care',
      detectedValue: '—',
      ruleCode: '—',
      ruleTitle: 'No applicable rule',
      expected: 'n/a',
      detected: 'n/a',
      result: 'NOT APPLICABLE',
      finding: 'Consumer care details',
    }),
    createdAt: '2026-08-22T10:32:34Z',
  },
  {
    id: 'fnd-482-usp',
    inspectionId: 'ins-10482',
    title: 'Unit sale price',
    fieldType: 'UNIT_SALE_PRICE',
    status: 'NOT_APPLICABLE',
    confidence: 0.5,
    risk: 'LOW',
    rationale: 'Unit sale price is not required for this demo product context; no rule resolved.',
    isReviewed: false,
    detectedValue: '—',
    regionId: undefined,
    expected: 'n/a',
    detected: 'n/a',
    validationResult: 'INCONCLUSIVE',
    chain: chain({
      pkg: PKG_10482,
      region: null,
      fieldLabel: 'Unit sale price',
      detectedValue: '—',
      ruleCode: '—',
      ruleTitle: 'No applicable rule',
      expected: 'n/a',
      detected: 'n/a',
      result: 'NOT APPLICABLE',
      finding: 'Unit sale price',
    }),
    createdAt: '2026-08-22T10:32:37Z',
  },
];

const regions10482: ViewerRegion[] = [
  region('rg-name', 'GENERIC_NAME', 'Generic name', 0.16, 0.16, 0.52, 0.09, 'positive'),
  region('rg-date', 'DATE_OF_PACKING', 'Date of packing', 0.16, 0.48, 0.34, 0.07, 'positive'),
  region('rg-bb', 'BEST_BEFORE', 'Best before', 0.54, 0.48, 0.3, 0.07, 'positive'),
  region('rg-nq', 'NET_QUANTITY', 'Net quantity', 0.16, 0.6, 0.3, 0.08, 'positive'),
  region('rg-mrp', 'MRP', 'MRP', 0.54, 0.6, 0.3, 0.08, 'warning'),
  region('rg-mfg', 'MANUFACTURER_DETAILS', 'Manufacturer', 0.16, 0.72, 0.68, 0.11, 'positive'),
  region('rg-batch', 'BATCH_NUMBER', 'Batch no.', 0.16, 0.86, 0.4, 0.06, 'positive'),
];

function region(
  id: string,
  fieldType: ViewerRegion['fieldType'],
  label: string,
  x: number,
  y: number,
  width: number,
  height: number,
  tone: Tone,
): ViewerRegion {
  return { id, fieldType, label, bbox: { x, y, width, height }, tone };
}

function declarationsFrom(findings: FindingView[]): DetectedDeclaration[] {
  return findings
    .filter((f) => f.detectedValue && f.detectedValue !== '—')
    .map((f) => ({
      field: f.fieldType ?? 'OTHER',
      value: f.detectedValue ?? '—',
      status: f.status,
      confidence: f.confidence,
      regionId: f.regionId,
    }));
}

const quality10482: QualityMetric[] = [
  { label: 'Resolution', score: 0.98, status: 'Excellent' },
  { label: 'Sharpness', score: 0.94, status: 'Good' },
  { label: 'Lighting', score: 0.91, status: 'Good' },
  { label: 'Text visibility', score: 0.96, status: 'Excellent' },
];

/* ========================================================================== */
/* INS-10483 — Packaged Drinking Water 1 L (analysed, near-clean)             */
/* ========================================================================== */
const PKG_10483 = 'Packaged Drinking Water — 1 L';
const findings10483: FindingView[] = [
  {
    id: 'fnd-483-nq',
    inspectionId: 'ins-10483',
    title: 'Net quantity declared',
    fieldType: 'NET_QUANTITY',
    status: 'COMPLIANT',
    confidence: 0.97,
    risk: 'LOW',
    rationale: 'Net quantity "1 L" detected with a recognised metric unit.',
    isReviewed: false,
    detectedValue: '1 L',
    regionId: 'rg483-nq',
    rule: RULE_REFS.nq,
    expected: 'Value + metric unit',
    detected: '1 L',
    validationResult: 'PASS',
    chain: chain({
      pkg: PKG_10483,
      region: 'Net quantity (text line)',
      fieldLabel: 'Net quantity',
      detectedValue: '1 L',
      ruleCode: 'DR-NQ-01',
      ruleTitle: 'Net quantity declaration',
      expected: 'value + metric unit',
      detected: '1 L',
      result: 'PASS',
      finding: 'Net quantity declared',
    }),
    createdAt: '2026-08-24T08:12:00Z',
  },
  {
    id: 'fnd-483-mrp',
    inspectionId: 'ins-10483',
    title: 'MRP declared inclusive of taxes',
    fieldType: 'MRP',
    status: 'COMPLIANT',
    confidence: 0.92,
    risk: 'LOW',
    rationale: 'MRP "₹20 (incl. of all taxes)" detected with the tax qualifier present.',
    isReviewed: false,
    detectedValue: '₹20 (incl. of all taxes)',
    regionId: 'rg483-mrp',
    rule: RULE_REFS.mrp,
    expected: 'MRP inclusive of all taxes',
    detected: '₹20 (incl. of all taxes)',
    validationResult: 'PASS',
    chain: chain({
      pkg: PKG_10483,
      region: 'MRP (text line)',
      fieldLabel: 'Maximum Retail Price',
      detectedValue: '₹20 (incl. of all taxes)',
      ruleCode: 'DR-MRP-01',
      ruleTitle: 'Maximum Retail Price declaration',
      expected: 'inclusive of all taxes',
      detected: 'inclusive qualifier present',
      result: 'PASS',
      finding: 'MRP declared inclusive of taxes',
    }),
    createdAt: '2026-08-24T08:12:04Z',
  },
  {
    id: 'fnd-483-mfg',
    inspectionId: 'ins-10483',
    title: 'Manufacturer address legibility low',
    fieldType: 'MANUFACTURER_DETAILS',
    status: 'REVIEW_REQUIRED',
    confidence: 0.63,
    risk: 'MEDIUM',
    rationale:
      'A manufacturer block was detected but text confidence is low (63%). The system does not conclude on partially legible text; inspector confirmation is requested.',
    isReviewed: false,
    detectedValue: 'Blue Springs Bottlers, …',
    regionId: 'rg483-mfg',
    rule: RULE_REFS.mfg,
    expected: 'Name + complete address',
    detected: 'Partially legible',
    validationResult: 'INCONCLUSIVE',
    chain: chain({
      pkg: PKG_10483,
      region: 'Manufacturer details (text block)',
      fieldLabel: 'Manufacturer details',
      detectedValue: 'Blue Springs Bottlers, …',
      ruleCode: 'DR-MFG-01',
      ruleTitle: 'Manufacturer / packer details',
      expected: 'name + address',
      detected: 'partially legible',
      result: 'INCONCLUSIVE → REVIEW REQUIRED',
      finding: 'Manufacturer address legibility low',
    }),
    createdAt: '2026-08-24T08:12:09Z',
  },
];
const regions10483: ViewerRegion[] = [
  region('rg483-nq', 'NET_QUANTITY', 'Net quantity', 0.18, 0.58, 0.3, 0.08, 'positive'),
  region('rg483-mrp', 'MRP', 'MRP', 0.54, 0.58, 0.32, 0.08, 'positive'),
  region('rg483-mfg', 'MANUFACTURER_DETAILS', 'Manufacturer', 0.16, 0.74, 0.68, 0.11, 'warning'),
];
const quality10483: QualityMetric[] = [
  { label: 'Resolution', score: 0.9, status: 'Good' },
  { label: 'Sharpness', score: 0.72, status: 'Fair' },
  { label: 'Lighting', score: 0.68, status: 'Fair' },
  { label: 'Text visibility', score: 0.74, status: 'Fair' },
];

/* ========================================================================== */
/* INS-10485 — Refined Sunflower Oil 1 L (violation)                          */
/* ========================================================================== */
const PKG_10485 = 'Refined Sunflower Oil — 1 L';
const findings10485: FindingView[] = [
  {
    id: 'fnd-485-nq',
    inspectionId: 'ins-10485',
    title: 'Net quantity declared',
    fieldType: 'NET_QUANTITY',
    status: 'COMPLIANT',
    confidence: 0.95,
    risk: 'LOW',
    rationale: 'Net quantity "1 L" detected with a recognised metric unit.',
    isReviewed: false,
    detectedValue: '1 L',
    regionId: 'rg485-nq',
    rule: RULE_REFS.nq,
    expected: 'Value + metric unit',
    detected: '1 L',
    validationResult: 'PASS',
    chain: chain({
      pkg: PKG_10485,
      region: 'Net quantity (text line)',
      fieldLabel: 'Net quantity',
      detectedValue: '1 L',
      ruleCode: 'DR-NQ-01',
      ruleTitle: 'Net quantity declaration',
      expected: 'value + metric unit',
      detected: '1 L',
      result: 'PASS',
      finding: 'Net quantity declared',
    }),
    createdAt: '2026-08-23T14:02:00Z',
  },
  {
    id: 'fnd-485-mrp',
    inspectionId: 'ins-10485',
    title: 'MRP declaration not detected',
    fieldType: 'MRP',
    status: 'POTENTIAL_VIOLATION',
    confidence: 0.8,
    risk: 'HIGH',
    rationale:
      'No MRP text region was detected on the analysed image. DR-MRP-01 (Demo v3.0) requires a retail sale price, so the absence is surfaced as a potential violation for inspector confirmation.',
    isReviewed: false,
    detectedValue: 'Not detected',
    regionId: undefined,
    rule: RULE_REFS.mrp,
    expected: 'MRP present, inclusive of all taxes',
    detected: 'Not detected',
    validationResult: 'FAIL',
    chain: chain({
      pkg: PKG_10485,
      region: null,
      fieldLabel: 'Maximum Retail Price',
      detectedValue: 'Not detected',
      ruleCode: 'DR-MRP-01',
      ruleTitle: 'Maximum Retail Price declaration',
      expected: 'present',
      detected: 'absent',
      result: 'FAIL → POTENTIAL VIOLATION',
      finding: 'MRP declaration not detected',
    }),
    createdAt: '2026-08-23T14:02:06Z',
  },
  {
    id: 'fnd-485-date',
    inspectionId: 'ins-10485',
    title: 'Date of manufacture declared',
    fieldType: 'DATE_OF_MANUFACTURE',
    status: 'COMPLIANT',
    confidence: 0.87,
    risk: 'LOW',
    rationale: 'A manufacture date "06/2026" was detected and parsed to a month/year.',
    isReviewed: false,
    detectedValue: '06/2026',
    regionId: 'rg485-date',
    rule: RULE_REFS.date,
    expected: 'Month/year present',
    detected: '06/2026',
    validationResult: 'PASS',
    chain: chain({
      pkg: PKG_10485,
      region: 'Date of manufacture (text line)',
      fieldLabel: 'Date of manufacture',
      detectedValue: '06/2026',
      ruleCode: 'DR-DATE-01',
      ruleTitle: 'Date of manufacture / packing',
      expected: 'month/year',
      detected: '06/2026',
      result: 'PASS',
      finding: 'Date of manufacture declared',
    }),
    createdAt: '2026-08-23T14:02:11Z',
  },
];
const regions10485: ViewerRegion[] = [
  region('rg485-nq', 'NET_QUANTITY', 'Net quantity', 0.16, 0.56, 0.3, 0.08, 'positive'),
  region('rg485-date', 'DATE_OF_MANUFACTURE', 'Mfg date', 0.16, 0.7, 0.36, 0.07, 'positive'),
];
const quality10485: QualityMetric[] = [
  { label: 'Resolution', score: 0.93, status: 'Good' },
  { label: 'Sharpness', score: 0.88, status: 'Good' },
  { label: 'Lighting', score: 0.85, status: 'Good' },
  { label: 'Text visibility', score: 0.9, status: 'Good' },
];

/* ========================================================================== */
/* Inspection list rows                                                       */
/* ========================================================================== */
function makeInspection(args: {
  id: string;
  referenceNo: string;
  productName: string;
  category: string;
  status: Inspection['status'];
  inspectorId: string;
  createdAt: string;
  updatedAt: string;
  completedAt?: string;
  findings?: FindingView[];
  counts?: Inspection['findingCounts'];
}): Inspection {
  const counts = args.findings ? countsFrom(args.findings) : args.counts;
  return {
    id: args.id,
    referenceNo: args.referenceNo,
    status: args.status,
    productId: `prod-${args.id}`,
    product: product(`prod-${args.id}`, args.productName, args.category),
    inspectorId: args.inspectorId,
    batchId: null,
    note: null,
    isDemo: true,
    createdAt: args.createdAt,
    updatedAt: args.updatedAt,
    completedAt: args.completedAt ?? null,
    findingCounts: counts,
  };
}

const ins10482 = makeInspection({
  id: 'ins-10482',
  referenceNo: 'INS-10482',
  productName: 'Classic Salted Namkeen 200 g',
  category: 'Snacks',
  status: 'UNDER_REVIEW',
  inspectorId: 'usr-anita',
  createdAt: '2026-08-22T10:30:00Z',
  updatedAt: '2026-08-24T09:15:00Z',
  findings: findings10482,
});
const ins10483 = makeInspection({
  id: 'ins-10483',
  referenceNo: 'INS-10483',
  productName: 'Packaged Drinking Water 1 L',
  category: 'Beverages',
  status: 'ANALYZED',
  inspectorId: 'usr-anita',
  createdAt: '2026-08-24T08:10:00Z',
  updatedAt: '2026-08-24T08:13:00Z',
  findings: findings10483,
});
const ins10484 = makeInspection({
  id: 'ins-10484',
  referenceNo: 'INS-10484',
  productName: 'Glucose Biscuits 100 g',
  category: 'Bakery',
  status: 'COMPLETED',
  inspectorId: 'usr-rahul',
  createdAt: '2026-08-21T11:00:00Z',
  updatedAt: '2026-08-21T12:30:00Z',
  completedAt: '2026-08-21T12:30:00Z',
  counts: {
    total: 9,
    compliant: 8,
    potentialViolation: 0,
    reviewRequired: 0,
    notApplicable: 1,
    lowConfidence: 0,
    imageQualityInsufficient: 0,
  },
});
const ins10485 = makeInspection({
  id: 'ins-10485',
  referenceNo: 'INS-10485',
  productName: 'Refined Sunflower Oil 1 L',
  category: 'Edible Oils',
  status: 'ANALYZED',
  inspectorId: 'usr-anita',
  createdAt: '2026-08-23T14:00:00Z',
  updatedAt: '2026-08-23T14:03:00Z',
  findings: findings10485,
});
const ins10486 = makeInspection({
  id: 'ins-10486',
  referenceNo: 'INS-10486',
  productName: 'Instant Noodles 70 g',
  category: 'Instant Food',
  status: 'ANALYZING',
  inspectorId: 'usr-anita',
  createdAt: '2026-08-24T09:40:00Z',
  updatedAt: '2026-08-24T09:41:00Z',
  counts: {
    total: 0,
    compliant: 0,
    potentialViolation: 0,
    reviewRequired: 0,
    notApplicable: 0,
    lowConfidence: 0,
    imageQualityInsufficient: 0,
  },
});
const ins10487 = makeInspection({
  id: 'ins-10487',
  referenceNo: 'INS-10487',
  productName: 'Turmeric Powder 200 g',
  category: 'Spices',
  status: 'UNDER_REVIEW',
  inspectorId: 'usr-rahul',
  createdAt: '2026-08-20T15:20:00Z',
  updatedAt: '2026-08-24T07:50:00Z',
  counts: {
    total: 8,
    compliant: 5,
    potentialViolation: 1,
    reviewRequired: 1,
    notApplicable: 1,
    lowConfidence: 0,
    imageQualityInsufficient: 0,
  },
});
const ins10488 = makeInspection({
  id: 'ins-10488',
  referenceNo: 'INS-10488',
  productName: 'Toothpaste 100 g',
  category: 'Personal Care',
  status: 'COMPLETED',
  inspectorId: 'usr-anita',
  createdAt: '2026-08-19T10:05:00Z',
  updatedAt: '2026-08-19T11:20:00Z',
  completedAt: '2026-08-19T11:20:00Z',
  counts: {
    total: 7,
    compliant: 6,
    potentialViolation: 0,
    reviewRequired: 0,
    notApplicable: 1,
    lowConfidence: 0,
    imageQualityInsufficient: 0,
  },
});
const ins10489 = makeInspection({
  id: 'ins-10489',
  referenceNo: 'INS-10489',
  productName: 'Basmati Rice 5 kg',
  category: 'Staples',
  status: 'IMAGES_PENDING',
  inspectorId: 'usr-anita',
  createdAt: '2026-08-24T09:55:00Z',
  updatedAt: '2026-08-24T09:55:00Z',
  counts: {
    total: 0,
    compliant: 0,
    potentialViolation: 0,
    reviewRequired: 0,
    notApplicable: 0,
    lowConfidence: 0,
    imageQualityInsufficient: 0,
  },
});

export const inspections: Inspection[] = [
  ins10486,
  ins10489,
  ins10483,
  ins10485,
  ins10482,
  ins10487,
  ins10484,
  ins10488,
];

function detail(
  inspection: Inspection,
  regions: ViewerRegion[],
  quality: QualityMetric[],
  findings: FindingView[],
): InspectionDetail {
  const counts = countsFrom(findings);
  return {
    inspection,
    imageRegions: regions,
    quality,
    qualityScore: Math.round((quality.reduce((s, q) => s + q.score, 0) / quality.length) * 100),
    declarations: declarationsFrom(findings),
    findings,
    complianceScore: assistanceScore(counts),
  };
}

export const inspectionDetails: Record<string, InspectionDetail> = {
  'ins-10482': detail(ins10482, regions10482, quality10482, findings10482),
  'ins-10483': detail(ins10483, regions10483, quality10483, findings10483),
  'ins-10485': detail(ins10485, regions10485, quality10485, findings10485),
};

export { STATUS_TONE };

/** All authored findings, flattened, for the review queue / evidence explorer. */
export const allFindings: FindingView[] = [...findings10482, ...findings10483, ...findings10485];
