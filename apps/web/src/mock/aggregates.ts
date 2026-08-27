/**
 * Derived DEMO aggregates for dashboards, queues and analytics screens.
 * All values are demonstrative only. ⚠ DEMO DATA — NOT LEGAL ADVICE.
 */
import type { AuditEvent, BatchInspection, DashboardSummary, InspectionStatus } from '@legalmet/types';

import { assistanceScore, countsFrom, inspectorName } from './fixtures';
import { allFindings, inspections } from './inspections';
import type {
  ActivityPoint,
  CategoryStat,
  EvidenceItem,
  ReportItem,
  ReviewQueueItem,
  RiskCase,
} from './types';

const productName = (inspectionId: string): string =>
  inspections.find((i) => i.id === inspectionId)?.product?.name ?? 'Unknown product';

const productCategory = (inspectionId: string): string =>
  inspections.find((i) => i.id === inspectionId)?.product?.category ?? '—';

/* -------------------------------------------------------------------------- */
/* Command Center dashboard                                                   */
/* -------------------------------------------------------------------------- */
export const dashboard: DashboardSummary = {
  inspections: {
    total: 128,
    byStatus: {
      CREATED: 4,
      IMAGES_PENDING: 6,
      ANALYZING: 3,
      ANALYZED: 22,
      UNDER_REVIEW: 17,
      COMPLETED: 71,
      ARCHIVED: 5,
    } as Record<InspectionStatus, number>,
  },
  findings: {
    total: 812,
    compliant: 604,
    potentialViolation: 47,
    reviewRequired: 63,
    notApplicable: 84,
    lowConfidence: 9,
    imageQualityInsufficient: 5,
  },
  recentInspections: inspections.slice(0, 6),
  recurringViolations: [
    { fieldType: 'COUNTRY_OF_ORIGIN', ruleId: null, ruleCode: 'DR-COO-01', count: 14, affectedInspections: 11 },
    { fieldType: 'MRP', ruleId: null, ruleCode: 'DR-MRP-01', count: 6, affectedInspections: 6 },
    { fieldType: 'NET_QUANTITY', ruleId: null, ruleCode: 'DR-NQ-01', count: 3, affectedInspections: 3 },
    { fieldType: 'DATE_OF_PACKING', ruleId: null, ruleCode: 'DR-DATE-01', count: 2, affectedInspections: 2 },
  ],
  generatedAt: '2026-08-24T09:45:00Z',
};

export const metricTrends = {
  totalInspections: { value: 128, delta: 12, dir: 'up' as const, note: 'vs last week' },
  packagesScanned: { value: 143, delta: 9, dir: 'up' as const, note: 'vs last week' },
  reviewRequired: { value: 17, delta: 4, dir: 'up' as const, note: 'awaiting inspector' },
  potentialViolations: { value: 9, delta: 2, dir: 'down' as const, note: 'vs last week' },
};

export const activityByRange: Record<'today' | 'week' | 'month', ActivityPoint[]> = {
  today: [
    { label: '08:00', scanned: 4, flagged: 1 },
    { label: '10:00', scanned: 9, flagged: 2 },
    { label: '12:00', scanned: 7, flagged: 1 },
    { label: '14:00', scanned: 11, flagged: 3 },
    { label: '16:00', scanned: 6, flagged: 1 },
  ],
  week: [
    { label: 'Mon', scanned: 22, flagged: 4 },
    { label: 'Tue', scanned: 28, flagged: 6 },
    { label: 'Wed', scanned: 19, flagged: 3 },
    { label: 'Thu', scanned: 31, flagged: 7 },
    { label: 'Fri', scanned: 26, flagged: 5 },
    { label: 'Sat', scanned: 12, flagged: 2 },
    { label: 'Sun', scanned: 5, flagged: 1 },
  ],
  month: [
    { label: 'Wk 1', scanned: 96, flagged: 18 },
    { label: 'Wk 2', scanned: 121, flagged: 24 },
    { label: 'Wk 3', scanned: 108, flagged: 19 },
    { label: 'Wk 4', scanned: 143, flagged: 27 },
  ],
};

export const riskOverview = { high: 9, medium: 21, low: 98 };

/* -------------------------------------------------------------------------- */
/* Review queue — built from authored REVIEW_REQUIRED / POTENTIAL_VIOLATION   */
/* -------------------------------------------------------------------------- */
export const reviewQueue: ReviewQueueItem[] = allFindings
  .filter((f) => f.status === 'REVIEW_REQUIRED' || f.status === 'POTENTIAL_VIOLATION')
  .map((f) => ({
    findingId: f.id,
    inspectionId: f.inspectionId,
    product: productName(f.inspectionId),
    finding: f.title,
    status: f.status,
    confidence: f.confidence,
    risk: f.risk,
    reason: f.rationale,
    createdAt: f.createdAt,
    assignedTo: 'Anita Rao',
  }));

/* -------------------------------------------------------------------------- */
/* Risk radar                                                                 */
/* -------------------------------------------------------------------------- */
export const riskCases: RiskCase[] = allFindings
  .filter((f) => f.risk !== 'LOW')
  .map((f) => ({
    inspectionId: f.inspectionId,
    product: productName(f.inspectionId),
    category: productCategory(f.inspectionId),
    risk: f.risk,
    riskScore: Math.round(f.confidence * (f.risk === 'HIGH' ? 95 : 70)),
    reason: f.title,
    confidence: f.confidence,
    finding: f.title,
    recommendedAction:
      f.status === 'POTENTIAL_VIOLATION' ? 'Inspector confirmation' : 'Manual review',
  }))
  .sort((a, b) => b.riskScore - a.riskScore);

export const riskFactors = [
  { label: 'Evidence confidence', weight: 'High' },
  { label: 'Number of findings', weight: 'Medium' },
  { label: 'Finding severity', weight: 'High' },
  { label: 'Image quality', weight: 'Medium' },
  { label: 'Repeated issue pattern', weight: 'Medium' },
  { label: 'Historical pattern (category)', weight: 'Low' },
];

/* -------------------------------------------------------------------------- */
/* Evidence explorer                                                          */
/* -------------------------------------------------------------------------- */
export const evidenceItems: EvidenceItem[] = allFindings
  .filter((f) => f.detectedValue && f.detectedValue !== '—' && f.detectedValue !== 'Not detected')
  .map((f) => ({
    id: `evi-${f.id}`,
    inspectionId: f.inspectionId,
    product: productName(f.inspectionId),
    fieldType: f.fieldType ?? 'OTHER',
    value: f.detectedValue ?? '—',
    confidence: f.confidence,
    finding: f.title,
    status: f.status,
    region: { x: 0.16, y: 0.4, width: 0.5, height: 0.12 },
  }));

/* -------------------------------------------------------------------------- */
/* Reports                                                                    */
/* -------------------------------------------------------------------------- */
export const reports: ReportItem[] = [
  {
    id: 'rep-10484',
    type: 'INSPECTION',
    title: 'Inspection report — Glucose Biscuits 100 g',
    inspectionId: 'ins-10484',
    createdAt: '2026-08-21T12:31:00Z',
    status: 'FINALIZED',
    inspector: 'Rahul Verma',
  },
  {
    id: 'rep-10488',
    type: 'INSPECTION',
    title: 'Inspection report — Toothpaste 100 g',
    inspectionId: 'ins-10488',
    createdAt: '2026-08-19T11:21:00Z',
    status: 'FINALIZED',
    inspector: 'Anita Rao',
  },
  {
    id: 'rep-batch-08',
    type: 'BATCH',
    title: 'Batch report — August retail sweep',
    createdAt: '2026-08-24T09:00:00Z',
    status: 'DRAFT',
    inspector: 'Rahul Verma',
  },
  {
    id: 'rep-10482',
    type: 'INSPECTION',
    title: 'Inspection report — Classic Salted Namkeen 200 g',
    inspectionId: 'ins-10482',
    createdAt: '2026-08-24T09:20:00Z',
    status: 'DRAFT',
    inspector: 'Anita Rao',
  },
];

/* -------------------------------------------------------------------------- */
/* Batch intelligence                                                         */
/* -------------------------------------------------------------------------- */
export const batch: BatchInspection = {
  id: 'batch-08',
  name: 'August retail sweep',
  description: 'Demonstration batch grouping of packaged-commodity inspections.',
  status: 'PROCESSING',
  totalCount: 42,
  stats: {
    total: 42,
    byStatus: {
      COMPLIANT: 28,
      POTENTIAL_VIOLATION: 6,
      REVIEW_REQUIRED: 5,
      NOT_APPLICABLE: 3,
      LOW_CONFIDENCE: 0,
      IMAGE_QUALITY_INSUFFICIENT: 0,
    },
    reviewRequired: 5,
    potentialViolations: 6,
  },
  createdBy: 'usr-rahul',
  createdAt: '2026-08-20T09:00:00Z',
  updatedAt: '2026-08-24T09:00:00Z',
};

export const batchSummary = {
  scanned: 42,
  compliant: 28,
  review: 5,
  violations: 6,
  avgConfidence: 0.89,
};

export const violationPatterns = [
  { label: 'Missing declaration', count: 14 },
  { label: 'MRP issue', count: 6 },
  { label: 'Quantity issue', count: 3 },
  { label: 'Date issue', count: 2 },
];

export const categoryStats: CategoryStat[] = [
  { category: 'Snacks', total: 12, violationRate: 0.16, reviewRate: 0.25, confidence: 0.92 },
  { category: 'Beverages', total: 9, violationRate: 0.11, reviewRate: 0.22, confidence: 0.9 },
  { category: 'Edible Oils', total: 7, violationRate: 0.28, reviewRate: 0.14, confidence: 0.88 },
  { category: 'Spices', total: 8, violationRate: 0.25, reviewRate: 0.25, confidence: 0.85 },
  { category: 'Bakery', total: 6, violationRate: 0.0, reviewRate: 0.16, confidence: 0.94 },
];

/* -------------------------------------------------------------------------- */
/* Audit trail                                                                */
/* -------------------------------------------------------------------------- */
export const auditEvents: AuditEvent[] = [
  {
    id: 'aud-1',
    inspectionId: 'ins-10482',
    entityType: 'Inspection',
    entityId: 'ins-10482',
    actorId: 'usr-anita',
    eventType: 'INSPECTION_CREATED',
    payload: { reference: 'INS-10482' },
    createdAt: '2026-08-22T10:30:00Z',
  },
  {
    id: 'aud-2',
    inspectionId: 'ins-10482',
    entityType: 'PackageImage',
    entityId: 'img-1',
    actorId: 'usr-anita',
    eventType: 'IMAGE_UPLOADED',
    payload: { imageType: 'FRONT' },
    createdAt: '2026-08-22T10:31:00Z',
  },
  {
    id: 'aud-3',
    inspectionId: 'ins-10482',
    entityType: 'Inspection',
    entityId: 'ins-10482',
    actorId: null,
    eventType: 'ANALYSIS_STARTED',
    payload: { engine: 'DeterministicRuleEngine', component: 'inspection.orchestrator' },
    createdAt: '2026-08-22T10:31:40Z',
  },
  {
    id: 'aud-4',
    inspectionId: 'ins-10482',
    entityType: 'Inspection',
    entityId: 'ins-10482',
    actorId: null,
    eventType: 'ANALYSIS_COMPLETED',
    payload: { findings: 10, component: 'rules.engine' },
    createdAt: '2026-08-22T10:32:40Z',
  },
  {
    id: 'aud-5',
    inspectionId: 'ins-10482',
    entityType: 'ComplianceFinding',
    entityId: 'fnd-482-mrp',
    actorId: null,
    eventType: 'FINDING_CREATED',
    payload: { status: 'REVIEW_REQUIRED', field: 'MRP', component: 'rules.engine' },
    createdAt: '2026-08-22T10:32:11Z',
  },
  {
    id: 'aud-6',
    inspectionId: 'ins-10484',
    entityType: 'Inspection',
    entityId: 'ins-10484',
    actorId: 'usr-rahul',
    eventType: 'INSPECTION_COMPLETED',
    payload: { reference: 'INS-10484' },
    createdAt: '2026-08-21T12:30:00Z',
  },
  {
    id: 'aud-7',
    inspectionId: 'ins-10488',
    entityType: 'ReviewAction',
    entityId: 'rev-1',
    actorId: 'usr-anita',
    eventType: 'REVIEW_RECORDED',
    payload: { action: 'ACCEPT', component: 'review.service' },
    createdAt: '2026-08-19T11:19:00Z',
  },
];

/* re-exports used across pages */
export { inspectorName, countsFrom, assistanceScore };
