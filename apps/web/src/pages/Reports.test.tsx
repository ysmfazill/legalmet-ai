// @vitest-environment jsdom
//
// UI-08 — Reports page tests for the REAL report surfaces: the Report Center
// list (live KPIs + rows from real records), the report detail page (frozen
// snapshot sections, finalization gate, honest error surfaces), and the RBAC
// hiding of write actions for read-only roles. The api client and app context
// are mocked at module boundaries; the pages under test are the real ones.

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { ReportDetail, ReportKpis, ReportList, User } from '@legalmet/types';

import { MemoryRouter, Route, Routes } from 'react-router-dom';

// --- module mocks (specifiers exactly as the pages import them) -------------

vi.mock('../api/client', () => ({
  api: {
    listReports: vi.fn(),
    reportKpis: vi.fn(),
    getReport: vi.fn(),
    generateReport: vi.fn(),
    reviewReport: vi.fn(),
    finalizeReport: vi.fn(),
    amendReport: vi.fn(),
    getEvidencePack: vi.fn(),
    getReportAudit: vi.fn(),
    exportReport: vi.fn(),
  },
  ApiClientError: class extends Error {
    constructor(_status: number, _payload: unknown, message: string) {
      super(message);
    }
  },
}));

let mockUser: User = {
  id: 'u1',
  fullName: 'Inspector Ishaan',
  email: 'i@y.z',
  role: 'INSPECTOR',
  isActive: true,
  createdAt: '2026-01-01T00:00:00Z',
};

vi.mock('../app/AppContext', () => ({
  useApp: () => ({ isLive: true, user: mockUser }),
}));

import { api } from '../api/client';
import { ReportsPage } from './Reports';
import { ReportDetailPage } from './ReportDetail';

const listReportsMock = vi.mocked(api.listReports);
const kpisMock = vi.mocked(api.reportKpis);
const getReportMock = vi.mocked(api.getReport);
const generateMock = vi.mocked(api.generateReport);
const finalizeMock = vi.mocked(api.finalizeReport);
const amendMock = vi.mocked(api.amendReport);
const packMock = vi.mocked(api.getEvidencePack);
const auditMock = vi.mocked(api.getReportAudit);

// --- fixtures ----------------------------------------------------------------

const KPIS: ReportKpis = {
  total: 6,
  draft: 2,
  finalized: 3,
  exported: 1,
  underReview: 1,
  amended: 0,
  requiresReview: 0,
};

const LIST: ReportList = {
  total: 1,
  page: 1,
  pageSize: 100,
  items: [
    {
      id: 'r1',
      inspectionId: 'i1',
      inspectionReference: 'LM-00012345',
      productName: 'DEMO Namkeen 200g',
      inspectionDate: '2026-09-03T10:00:00Z',
      inspectorName: 'Inspector Ishaan',
      result: 'COMPLIANT',
      status: 'FINALIZED',
      version: 1,
      evidenceCount: 17,
      generatedAt: '2026-09-03T11:00:00Z',
      finalizedAt: '2026-09-03T12:00:00Z',
      amendmentReason: null,
      createdBy: 'u1',
      updatedAt: '2026-09-03T12:00:00Z',
    },
  ],
};

function makeDetail(overrides: Partial<ReportDetail> = {}): ReportDetail {
  return {
    id: 'r1',
    inspectionId: 'i1',
    inspectionReference: 'LM-00012345',
    status: 'UNDER_REVIEW',
    result: 'NOT_EVALUATED',
    version: 1,
    productName: 'DEMO Namkeen 200g',
    productCategory: 'food',
    inspectionDate: '2026-09-03T10:00:00Z',
    inspectionStatus: 'UNDER_REVIEW',
    inspectorName: 'Inspector Ishaan',
    inspectorId: 'u1',
    createdBy: 'u1',
    createdByName: 'Inspector Ishaan',
    generatedAt: '2026-09-03T11:00:00Z',
    finalizedAt: null,
    finalizedBy: null,
    finalizedByName: null,
    amendmentReason: null,
    sourceComplaint: null,
    evidence: {
      requiredTotal: 2,
      requiredOpen: 1,
      recommendedOpen: 1,
      evidenceItems: 17,
      findingRows: 6,
      counts: {},
      blockers: ['Required evidence unresolved: task t1 is OPEN'],
      canFinalize: false,
    },
    versions: [
      {
        version: 1,
        id: 'v1',
        reason: 'Initial generation',
        createdAt: '2026-09-03T11:00:00Z',
        createdBy: 'u1',
        createdByName: 'Inspector Ishaan',
        statusAtCreation: null,
      },
    ],
    snapshot: {
      reportId: 'r1',
      inspectionId: 'i1',
      inspectionReference: 'LM-00012345',
      version: 1,
      generatedAt: '2026-09-03T11:00:00Z',
      result: 'NOT_EVALUATED',
      inspection: null,
      sourceComplaint: null,
      findings: [
        {
          id: 'f1',
          status: 'COMPLIANT',
          severity: 'MINOR',
          requirement: 'Net quantity must be declared on the principal display panel.',
          ruleCode: 'LM-QCR-01',
          ruleVersion: '1',
          regulatoryVersionLabel: null,
          detectedValue: '200 g',
          expectedValue: null,
          explanation: 'Declared net quantity detected and within tolerance.',
          reviewState: 'CONFIRMED',
          evidenceStatus: 'VERIFIED',
          source: 'OFFICIAL',
        },
      ],
      regulatoryBasis: [
        {
          engineVersion: '1.0.0',
          regulatoryVersionLabel: '2026 edition',
          contextDate: '2026-06-01',
          status: 'COMPLIANT',
        },
      ],
      measurements: [],
      lots: [],
      decision: null,
      completeness: null,
    },
    boundaryNote: 'Reports are decision-support artifacts.',
    ...overrides,
  };
}

function renderReports() {
  return render(
    <MemoryRouter initialEntries={['/reports']}>
      <Routes>
        <Route path="/reports" element={<ReportsPage />} />
        <Route path="/reports/:id" element={<ReportDetailPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

function renderDetail() {
  return render(
    <MemoryRouter initialEntries={['/reports/r1']}>
      <Routes>
        <Route path="/reports/:id" element={<ReportDetailPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  mockUser = {
    id: 'u1',
    fullName: 'Inspector Ishaan',
    email: 'i@y.z',
    role: 'INSPECTOR',
    isActive: true,
    createdAt: '2026-01-01T00:00:00Z',
  };
  listReportsMock.mockReset().mockResolvedValue(LIST);
  kpisMock.mockReset().mockResolvedValue(KPIS);
  getReportMock.mockReset().mockResolvedValue(makeDetail());
  generateMock.mockReset().mockResolvedValue(makeDetail());
  finalizeMock.mockReset().mockResolvedValue(makeDetail());
  amendMock.mockReset().mockResolvedValue(makeDetail());
  packMock.mockReset().mockResolvedValue({
    packId: 'p1',
    reportId: 'r1',
    inspectionId: 'i1',
    reportVersion: 1,
    createdAt: '2026-09-03T11:00:00Z',
    evidenceCount: 2,
    completeness: {
      requiredTotal: 2,
      requiredOpen: 1,
      recommendedOpen: 1,
      evidenceItems: 2,
      findingRows: 1,
      counts: {},
      blockers: [],
      canFinalize: false,
    },
    items: [
      {
        id: 'e1',
        ref: 'E-001',
        sequence: 1,
        evidenceType: 'IMAGE',
        evidenceId: 'img1',
        label: 'front.png',
        detail: { origin: 'OFFICIAL' },
      },
    ],
    sourceComplaint: null,
    decision: null,
    auditEvents: [],
    boundaryNote: 'Reports are decision-support artifacts.',
  });
  auditMock.mockReset().mockResolvedValue({
    reportId: 'r1',
    inspectionId: 'i1',
    events: [
      {
        id: 'a1',
        actorId: 'u1',
        actorRole: 'INSPECTOR',
        actorName: 'Inspector Ishaan',
        eventType: 'REPORT_CREATED',
        reportId: 'r1',
        inspectionId: 'i1',
        payload: {},
        createdAt: '2026-09-03T10:30:00Z',
      },
    ],
  });
});

afterEach(() => cleanup());

// ---------------------------------------------------------------- Report Center

describe('ReportsPage (UI-08)', () => {
  it('renders the spec header, live KPIs and real report rows', async () => {
    renderReports();

    expect(screen.getByRole('heading', { name: 'Reports' })).toBeTruthy();
    expect(
      screen.getByText('Generate, review and export evidence-backed inspection reports.'),
    ).toBeTruthy();

    // KPIs come from the live endpoint — real counts, not fabricated.
    await waitFor(() => expect(kpisMock).toHaveBeenCalled());
    expect(await screen.findByText('Total Reports')).toBeTruthy();
    expect(screen.getByText('6')).toBeTruthy();
    expect(screen.getAllByText('Draft').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Finalized').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Exported').length).toBeGreaterThan(0);

    // The real row: reference links to the detail page.
    const link = await screen.findByRole('link', { name: /LM-00012345/ });
    expect(link.getAttribute('href')).toBe('/reports/r1');
    expect(screen.getByText('DEMO Namkeen 200g')).toBeTruthy();
    expect(screen.getAllByText('Finalized').length).toBeGreaterThan(0);
    expect(screen.getByText('Compliant')).toBeTruthy();
  });

  it('shows the spec empty state with the Open Inspection CTA when no reports exist', async () => {
    listReportsMock.mockResolvedValue({
      total: 0,
      page: 1,
      pageSize: 100,
      items: [],
    });
    renderReports();

    expect(await screen.findByText('No finalized reports yet.')).toBeTruthy();
    const cta = screen.getByRole('link', { name: /Open Inspection/ });
    expect(cta.getAttribute('href')).toBe('/inspections');
  });

  it('searches server-side through the list endpoint', async () => {
    renderReports();
    await screen.findByRole('link', { name: /LM-00012345/ });

    const search = screen.getByLabelText('Search reports');
    fireEvent.change(search, { target: { value: 'namkeen' } });

    await waitFor(() =>
      expect(listReportsMock).toHaveBeenLastCalledWith(
        expect.objectContaining({ q: 'namkeen' }),
      ),
    );
  });
});

// -------------------------------------------------------------- report detail

describe('ReportDetailPage (UI-08)', () => {
  it('renders the frozen snapshot sections: findings, regulatory basis, decision honesty', async () => {
    renderDetail();

    expect(await screen.findByText('Executive findings')).toBeTruthy();
    // The frozen finding requirement text from the snapshot.
    expect(
      screen.getByText(/Net quantity must be declared on the principal display panel/),
    ).toBeTruthy();
    expect(screen.getByText('Regulatory basis')).toBeTruthy();
    expect(screen.getByText('1.0.0')).toBeTruthy();
    // §12: no decision recorded → honest NOT-EVALUATED statement.
    expect(screen.getAllByText(/No inspector decision recorded/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/AI is never the final legal authority/i)).toBeTruthy();
  });

  it('renders the finalization gate with the spec blocker message and CTAs', async () => {
    renderDetail();

    expect(await screen.findByText('Finalization gate')).toBeTruthy();
    // §8 exact contract: required evidence blocks finalization.
    expect(
      screen.getByText(/Report cannot be finalized until required evidence is resolved/),
    ).toBeTruthy();
    expect(screen.getAllByText(/No inspector decision recorded/).length).toBeGreaterThan(0);
    // §13 CTAs.
    expect(screen.getByRole('link', { name: /Resolve Missing Evidence/ }).getAttribute('href')).toBe('/inspections/i1');
    expect(screen.getByRole('link', { name: /Return to Inspection/ }).getAttribute('href')).toBe('/inspections/i1');
    // The finalize button is disabled while the gate is blocked.
    const finalize = screen.getByRole('button', { name: /Finalize Report/ });
    expect((finalize as HTMLButtonElement).disabled).toBe(true);
  });

  it('distinguishes SOURCE and OFFICIAL evidence in findings', async () => {
    getReportMock.mockResolvedValue(
      makeDetail({
        sourceComplaint: {
          reference: 'CMP-00042',
          status: 'INSPECTION_SCHEDULED',
          product: 'DEMO Tea 250g',
          location: 'Pune',
          issue: 'MRP appears inconsistent',
          description: null,
          priority: 'HIGH',
          submittedAt: '2026-09-01T10:00:00Z',
        },
      }),
    );
    renderDetail();

    // §4: the source context card labels citizen evidence as SOURCE.
    expect(await screen.findByText(/Citizen complaint — SOURCE evidence/i)).toBeTruthy();
    // Findings rows carry their own origin chips (OFFICIAL here).
    expect(screen.getAllByText(/Official \(inspection\)/i).length).toBeGreaterThan(0);
  });

  it('surfaces backend gate rejections honestly (no fake success)', async () => {
    finalizeMock.mockRejectedValue(
      Object.assign(new Error('Report cannot be finalized until required evidence is resolved. No inspector decision recorded — the report cannot state a result without one.'), {
        name: 'ApiClientError',
      }),
    );
    // Enable the button by resolving the gate: decision present + required
    // evidence closed. Must be set BEFORE render — useReport loads once.
    getReportMock.mockResolvedValue(
      makeDetail({
        evidence: {
          requiredTotal: 2,
          requiredOpen: 0,
          recommendedOpen: 1,
          evidenceItems: 17,
          findingRows: 6,
          counts: {},
          blockers: [],
          canFinalize: true,
        },
        snapshot: {
          reportId: 'r1',
          inspectionId: 'i1',
          version: 1,
          generatedAt: '2026-09-03T11:00:00Z',
          result: 'COMPLIANT',
          findings: [],
          regulatoryBasis: [],
          measurements: [],
          lots: [],
          decision: {
            decision: 'COMPLIANT',
            reason: 'All requirements verified.',
            decidedBy: 'u1',
            decidedByName: 'Inspector Ishaan',
            decidedAt: '2026-09-03T11:30:00Z',
            evaluationId: null,
          },
        },
      }),
    );
    renderDetail();

    const finalize = await screen.findByRole('button', { name: /Finalize Report/ });
    await waitFor(() => expect((finalize as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(finalize);

    expect(
      (await screen.findByRole('alert')).textContent,
    ).toMatch(/Report cannot be finalized until required evidence is resolved/);
  });

  it('hides lifecycle write actions for AUDITOR (backend still rejects them)', async () => {
    mockUser = { ...mockUser, role: 'AUDITOR', fullName: 'Auditor A.' };
    renderDetail();

    await screen.findByText('Executive findings');
    expect(screen.queryByRole('button', { name: /Finalize Report/ })).not.toBeTruthy();
    expect(screen.queryByRole('button', { name: /Generate Report/ })).not.toBeTruthy();
    expect(screen.getByText(/Read-only role/i)).toBeTruthy();
  });

  it('shows the ungenerated state with the generate CTA before any snapshot exists', async () => {
    getReportMock.mockResolvedValue(
      makeDetail({ generatedAt: null, snapshot: null, versions: [] }),
    );
    renderDetail();

    expect(await screen.findByText(/Not generated yet/i)).toBeTruthy();
    const generate = screen.getAllByRole('button', { name: /Generate Report/ })[0];
    fireEvent.click(generate);
    await waitFor(() => expect(generateMock.mock.calls[0]?.[0]).toBe('r1'));
  });

  it('opens the evidence pack drawer with stable E-00N identifiers', async () => {
    renderDetail();
    fireEvent.click(await screen.findByRole('button', { name: /Evidence Pack/ }));

    expect(await screen.findByText('E-001')).toBeTruthy();
    
    expect(screen.getByText('2 items')).toBeTruthy();
  });

  it('renders the report audit trail from the report-scoped endpoint', async () => {
    renderDetail();
    await screen.findByText('Audit trail');
    expect(auditMock).toHaveBeenCalledWith('r1');
    expect(await screen.findByText('Report Created')).toBeTruthy();
  });
});
