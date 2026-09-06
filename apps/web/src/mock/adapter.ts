/**
 * MOCK DATA ADAPTER.
 *
 * This is the ONLY place the UI reads demo data. It is intentionally shaped
 * like an async API (promises + latency) so screens exercise real loading /
 * empty / error states, and so it can be swapped for the live backend later
 * without touching any component. Functions map 1:1 to planned endpoints
 * (see services/api routers): inspections, findings, review, regulations,
 * audit, analytics, batch.
 *
 * No compliance logic lives here — findings are pre-computed DEMO data. The
 * real deciding component is the backend's deterministic rule engine.
 */
import type {
  AuditEvent,
  BatchInspection,
  DashboardSummary,
  Inspection,
  Regulation,
  RegulationVersion,
  Rule,
} from '@legalmet/types';

import { currentUser, regulation, regulationVersions, rules } from './fixtures';
import {
  citizenMyReports,
  citizenScanDemo,
  complaints,
  nearbyComplaints,
} from './citizen';
import { inspectionDetails, inspections } from './inspections';
import {
  activityByRange,
  auditEvents,
  batch,
  batchSummary,
  categoryStats,
  dashboard,
  evidenceItems,
  metricTrends,
  reports,
  reviewQueue,
  riskCases,
  riskFactors,
  riskOverview,
  violationPatterns,
} from './aggregates';
import type {
  ActivityPoint,
  CategoryStat,
  EvidenceItem,
  InspectionDetail,
  ReportItem,
  ReviewQueueItem,
  RiskCase,
} from './types';
import type {
  CitizenReport,
  CitizenScanResult,
  Complaint,
  NearbyComplaint,
} from './citizen';

const LATENCY_MS = 260;

function delay<T>(value: T, ms = LATENCY_MS): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), ms));
}

export interface InspectionFilters {
  status?: string;
  category?: string;
  search?: string;
}

export const mockApi = {
  currentUser: () => delay(currentUser),

  listInspections: (filters: InspectionFilters = {}): Promise<Inspection[]> => {
    let rows = inspections;
    if (filters.status) rows = rows.filter((i) => i.status === filters.status);
    if (filters.category) rows = rows.filter((i) => i.product?.category === filters.category);
    if (filters.search) {
      const q = filters.search.toLowerCase();
      rows = rows.filter(
        (i) =>
          i.referenceNo.toLowerCase().includes(q) ||
          (i.product?.name.toLowerCase().includes(q) ?? false),
      );
    }
    return delay(rows);
  },

  getInspection: (id: string): Promise<Inspection | undefined> =>
    delay(inspections.find((i) => i.id === id)),

  getInspectionDetail: (id: string): Promise<InspectionDetail | undefined> =>
    delay(inspectionDetails[id]),

  getDashboard: (): Promise<{
    summary: DashboardSummary;
    trends: typeof metricTrends;
    activity: Record<'today' | 'week' | 'month', ActivityPoint[]>;
    risk: typeof riskOverview;
  }> =>
    delay({
      summary: dashboard,
      trends: metricTrends,
      activity: activityByRange,
      risk: riskOverview,
    }),

  getReviewQueue: (): Promise<ReviewQueueItem[]> => delay(reviewQueue),

  getRiskCases: (): Promise<{ cases: RiskCase[]; factors: typeof riskFactors }> =>
    delay({ cases: riskCases, factors: riskFactors }),

  getEvidenceItems: (): Promise<EvidenceItem[]> => delay(evidenceItems),

  getRegulation: (): Promise<{
    regulation: Regulation;
    versions: RegulationVersion[];
    rules: Rule[];
  }> => delay({ regulation, versions: regulationVersions, rules }),

  getAudit: (): Promise<AuditEvent[]> => delay(auditEvents),

  getBatchIntelligence: (): Promise<{
    batch: BatchInspection;
    summary: typeof batchSummary;
    patterns: typeof violationPatterns;
    categories: CategoryStat[];
  }> => delay({ batch, summary: batchSummary, patterns: violationPatterns, categories: categoryStats }),

  getReports: (): Promise<ReportItem[]> => delay(reports),

  /** Simulated inspector review action; the real backend records this + audits it. */
  recordReview: (findingId: string, action: string, note?: string): Promise<{ ok: true }> => {
    void findingId;
    void action;
    void note;
    return delay({ ok: true } as const, 200);
  },

  /* --- Complaint management (demo — no complaint backend exists yet) ------ */

  listComplaints: (filters: { status?: string; search?: string } = {}): Promise<Complaint[]> => {
    let rows = complaints;
    if (filters.status) rows = rows.filter((c) => c.status === filters.status);
    if (filters.search) {
      const q = filters.search.toLowerCase();
      rows = rows.filter(
        (c) =>
          c.referenceNo.toLowerCase().includes(q) ||
          c.product.toLowerCase().includes(q) ||
          c.location.toLowerCase().includes(q),
      );
    }
    return delay(rows);
  },

  getComplaint: (id: string): Promise<Complaint | undefined> =>
    delay(complaints.find((c) => c.id === id)),

  /**
   * Simulated complaint → inspection conversion (demo). The REAL conversion
   * navigates to the New Inspection flow, which creates a genuine backend
   * inspection; this seam exists so the demo keeps working offline.
   */
  convertComplaintToInspection: (complaintId: string): Promise<{ ok: true; inspectionId: string }> =>
    delay({ ok: true as const, inspectionId: `INS-DEMO-${complaintId.slice(-3).toUpperCase()}` }, 400),

  /* --- Citizen mode (demo — public experience) ---------------------------- */

  getCitizenScanDemo: (): Promise<CitizenScanResult> => delay(citizenScanDemo),

  listCitizenReports: (): Promise<CitizenReport[]> => delay(citizenMyReports),

  listNearbyComplaints: (): Promise<NearbyComplaint[]> => delay(nearbyComplaints),

  /**
   * Simulated citizen report submission (demo). Wording contract: the result
   * says the report was received — never that a violation is confirmed.
   */
  submitCitizenReport: (input: {
    product: string;
    issue: string;
    location: string;
  }): Promise<{ ok: true; referenceNo: string }> => {
    void input;
    return delay(
      { ok: true as const, referenceNo: `CMP-2026-0${150 + Math.floor(input.product.length / 7)}` },
      600,
    );
  },
};

export type MockApi = typeof mockApi;
