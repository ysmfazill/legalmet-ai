// @vitest-environment jsdom
//
// UI-05 — Workspace page tests for the REAL inspection workspace: the source
// complaint brief (immutable citizen evidence, clearly separated from official
// findings) and the department assignment card. The api client, the app
// context, the object-url fetcher and the data hooks (perception / compliance
// / hitl) are mocked at module boundaries; the page and its new UI-05 cards
// are the real implementation.

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { Inspection, SourceComplaint, User } from '@legalmet/types';

import { MemoryRouter, Route, Routes } from 'react-router-dom';

// --- module mocks (specifiers exactly as the page imports them) -------------

vi.mock('../api/client', () => ({
  api: {
    getInspection: vi.fn(),
    getInspectionSourceComplaint: vi.fn(),
    assignInspection: vi.fn(),
    complaintInspectors: vi.fn(),
  },
  // Mirrors the real constructor: (status, payload, message).
  ApiClientError: class extends Error {
    constructor(_status: number, _payload: unknown, message: string) {
      super(message);
    }
  },
}));

let mockUser: User = {
  id: 'u1',
  fullName: 'Supervisor',
  email: 's@y.z',
  role: 'SUPERVISOR',
  isActive: true,
  createdAt: '2026-01-01T00:00:00Z',
};

vi.mock('../app/AppContext', () => ({
  useApp: () => ({ isLive: true, user: mockUser }),
}));

vi.mock('../mock/adapter', () => ({
  // No demo inspection matches the id under test — the real one must win.
  mockApi: { getInspectionDetail: vi.fn(async () => null) },
}));

vi.mock('../intake/useObjectUrl', () => ({
  useObjectUrl: () => ({ status: 'loading' }),
}));

vi.mock('../perception/usePerception', () => ({
  usePerception: () => ({
    loading: false,
    error: null,
    analysis: { hasRuns: false },
    ocr: [],
    regions: [],
    fields: [],
    runs: [],
    starting: false,
    start: vi.fn(async () => {}),
    reanalyze: vi.fn(async () => {}),
  }),
}));

vi.mock('../compliance/useCompliance', () => ({
  useCompliance: () => ({
    loading: false,
    error: null,
    status: null,
    evaluation: null,
    findings: [],
    evaluating: false,
    evaluate: vi.fn(async () => {}),
    reload: vi.fn(async () => {}),
  }),
}));

vi.mock('../hitl/useHitl', () => ({
  useHitl: () => ({
    loading: false,
    error: null,
    status: null,
    decisions: null,
    submitting: false,
    correctField: vi.fn(async () => true),
    reviewFinding: vi.fn(async () => null),
    submitDecision: vi.fn(async () => null),
    reload: vi.fn(async () => {}),
  }),
}));

import { api, ApiClientError } from '../api/client';
import { WorkspacePage } from './Workspace';

const getInspectionMock = vi.mocked(api.getInspection);
const getSourceMock = vi.mocked(api.getInspectionSourceComplaint);
const assignMock = vi.mocked(api.assignInspection);
const inspectorsMock = vi.mocked(api.complaintInspectors);

// --- fixtures ----------------------------------------------------------------

function makeInspection(overrides: Partial<Inspection> = {}): Inspection {
  return {
    id: 'i1',
    referenceNo: 'LM-00012345',
    status: 'CREATED',
    productId: null,
    product: null,
    inspectorId: 'u1',
    inspectorName: 'Supervisor',
    batchId: null,
    note: 'Created from citizen complaint CMP-00042 — MRP appears inconsistent (Pune)',
    isDemo: false,
    createdAt: '2026-09-03T10:00:00Z',
    updatedAt: '2026-09-03T10:00:00Z',
    completedAt: null,
    packages: [],
    sourceComplaint: {
      id: 'c1',
      reference: 'CMP-00042',
      status: 'INSPECTION_SCHEDULED',
      issue: 'MRP appears inconsistent',
      location: 'Pune',
      priority: 'HIGH',
    },
    ...overrides,
  };
}

function makeBrief(overrides: Partial<SourceComplaint> = {}): SourceComplaint {
  return {
    id: 'c1',
    reference: 'CMP-00042',
    status: 'INSPECTION_SCHEDULED',
    product: 'DEMO Tea 250g',
    shop: 'Test Store',
    location: 'Pune',
    issue: 'MRP appears inconsistent',
    description: 'The printed MRP looks tampered with',
    reporterName: 'A. Citizen',
    screeningRisk: 'HIGH',
    officialPriority: null,
    assignedInspectorId: null,
    assignedInspectorName: null,
    evidence: {
      imageUrl: '/api/v1/storage/citizen-photo.png',
      scanReference: 'SCN-0001',
      detectedFields: [],
      citizenFollowUps: [],
    },
    eventCount: 4,
    createdAt: '2026-09-01T10:00:00Z',
    ...overrides,
  };
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/inspections/i1']}>
      <Routes>
        <Route path="/inspections/:id" element={<WorkspacePage />} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  mockUser = {
    id: 'u1',
    fullName: 'Supervisor',
    email: 's@y.z',
    role: 'SUPERVISOR',
    isActive: true,
    createdAt: '2026-01-01T00:00:00Z',
  };
  getInspectionMock.mockReset();
  getSourceMock.mockReset();
  assignMock.mockReset();
  inspectorsMock.mockReset();
  getInspectionMock.mockResolvedValue(makeInspection());
  getSourceMock.mockResolvedValue(makeBrief());
  inspectorsMock.mockResolvedValue([
    { id: 'u9', fullName: 'Field Inspector', role: 'INSPECTOR' },
  ]);
});

afterEach(cleanup);

describe('RealInspectionWorkspace (UI-05)', () => {
  it('shows the inspection brief for a targeted inspection with immutable source evidence', async () => {
    renderPage();

    // The brief names its origin — the provenance chain the spec requires.
    // (The card header renders from the inspection row; the brief body is a
    // separate fetch, so wait for its content.)
    expect(await screen.findByText('Source complaint CMP-00042')).toBeTruthy();
    expect(await screen.findByText('MRP appears inconsistent')).toBeTruthy();
    expect(await screen.findByText('DEMO Tea 250g')).toBeTruthy();
    expect(await screen.findByText('Pune')).toBeTruthy();

    // Source evidence section, clearly separated from official findings.
    expect(screen.getByText('Source complaint evidence')).toBeTruthy();
    expect(screen.getByText(/not official findings/i)).toBeTruthy();
    expect(screen.getByText(/citizen.submitted at report time and never modified/i)).toBeTruthy();
    expect(screen.getByText(/The printed MRP looks tampered with/i)).toBeTruthy();

    // The complaint itself stays reachable.
    expect(screen.getByRole('link', { name: /Open complaint/i }).getAttribute('href')).toBe(
      '/complaints/c1',
    );
  });

  it('does not show a source brief for a standard-intake inspection', async () => {
    getInspectionMock.mockResolvedValue(makeInspection({ sourceComplaint: null }));
    renderPage();

    await screen.findByText('LM-00012345');
    expect(screen.queryByText('Source complaint evidence')).toBeNull();
    expect(screen.queryByRole('link', { name: /Open complaint/i })).toBeNull();
    // The workspace itself still renders.
    expect(screen.getByText('LIVE INSPECTION')).toBeTruthy();
  });

  it('SUPERVISOR assigns an inspector through the audited endpoint', async () => {
    assignMock.mockResolvedValue(
      makeInspection({ inspectorId: 'u9', inspectorName: 'Field Inspector' }),
    );
    renderPage();

    // The converting officer is the current inspector until a formal
    // assignment replaces them. Wait for the inspector options to load —
    // changing a select before its option exists silently clears the value.
    expect(await screen.findByText('Supervisor')).toBeTruthy();
    await screen.findByText('Field Inspector (inspector)');
    fireEvent.change(screen.getByLabelText(/^Inspector/), { target: { value: 'u9' } });
    fireEvent.click(screen.getByRole('button', { name: /Assign inspector$/ }));

    await waitFor(() =>
      expect(assignMock).toHaveBeenCalledWith('i1', {
        inspectorId: 'u9',
        note: undefined,
        reassign: undefined,
      }),
    );
    // The success notice names the assigned inspector; the assignment is audited.
    expect(await screen.findByText(/Inspector assigned — Field Inspector/i)).toBeTruthy();
    expect(screen.getByText(/assignment is audited/i)).toBeTruthy();
  });

  it('requires an explicit reassignment confirmation once an inspector is assigned', async () => {
    renderPage();
    await screen.findByText('Source complaint CMP-00042');

    // inspection.inspectorName is set in the fixture → reassignment checkbox.
    expect(screen.getByLabelText(/Confirm reassignment/i)).toBeTruthy();
  });

  it('INSPECTOR does not see the department assignment card', async () => {
    mockUser = { ...mockUser, role: 'INSPECTOR' };
    renderPage();
    await screen.findByText('Source complaint CMP-00042');
    expect(screen.queryByRole('button', { name: /Assign inspector$/ })).toBeNull();
  });

  it('finalized inspections cannot be assigned', async () => {
    getInspectionMock.mockResolvedValue(makeInspection({ status: 'COMPLETED' }));
    renderPage();
    await screen.findByText(/finalized/i);
    expect(screen.queryByRole('button', { name: /Assign inspector$/ })).toBeNull();
    expect(screen.getByText(/no further assignment is possible/i)).toBeTruthy();
  });

  it('surfaces the backend error when assignment fails', async () => {
    assignMock.mockRejectedValue(
      new ApiClientError(
        409,
        null,
        'Inspection LM-00012345 is already assigned to Field Inspector. Confirm the reassignment explicitly.',
      ),
    );
    renderPage();

    await screen.findByText('Field Inspector (inspector)');
    fireEvent.change(screen.getByLabelText(/^Inspector/), { target: { value: 'u9' } });
    fireEvent.click(screen.getByRole('button', { name: /Assign inspector$/ }));

    expect(await screen.findByText(/Confirm the reassignment explicitly/i)).toBeTruthy();
  });
});
