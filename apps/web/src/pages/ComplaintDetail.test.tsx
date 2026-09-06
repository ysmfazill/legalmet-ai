// @vitest-environment jsdom
//
// UI-05 — ComplaintDetail page tests: the complaint → targeted inspection
// conversion surface. The api client, app context and object-url fetcher are
// mocked at the module boundary; the page itself (action gating, confirmation
// panel, transition lifecycle, linked-inspection protection, role gating) is
// the real implementation.

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { ComplaintDetail, User } from '@legalmet/types';

import { MemoryRouter, Route, Routes } from 'react-router-dom';

// --- module mocks (specifiers exactly as the page imports them) -------------

vi.mock('../api/client', () => ({
  api: {
    complaintGet: vi.fn(),
    complaintTransition: vi.fn(),
    complaintInspectors: vi.fn(async () => []),
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
  fullName: 'Officer',
  email: 'x@y.z',
  role: 'INSPECTOR',
  isActive: true,
  createdAt: '2026-01-01T00:00:00Z',
};

vi.mock('../app/AppContext', () => ({
  useApp: () => ({ user: mockUser }),
}));

vi.mock('../intake/useObjectUrl', () => ({
  // Source photos stay in their loading state — the panel's real fetch is not
  // under test here.
  useObjectUrl: () => ({ status: 'loading' }),
}));

import { api, ApiClientError } from '../api/client';
import { ComplaintDetailPage } from './ComplaintDetail';

const getMock = vi.mocked(api.complaintGet);
const transitionMock = vi.mocked(api.complaintTransition);

// --- fixtures ----------------------------------------------------------------

function makeDetail(overrides: Partial<ComplaintDetail> = {}): ComplaintDetail {
  return {
    id: 'c1',
    reference: 'CMP-00042',
    status: 'ACCEPTED',
    product: 'DEMO Tea 250g',
    location: 'Pune',
    issue: 'MRP appears inconsistent',
    screeningRisk: 'HIGH',
    officialPriority: null,
    assignedInspectorId: null,
    assignedInspectorName: null,
    inspectionId: null,
    inspectionReference: null,
    hasImageEvidence: true,
    evidenceCompleteness: 80,
    pendingInfoRequest: null,
    createdAt: '2026-09-01T10:00:00Z',
    updatedAt: '2026-09-02T10:00:00Z',
    shop: 'Test Store',
    description: 'The printed MRP looks tampered with',
    reporterName: 'A. Citizen',
    reporterContact: null,
    evidence: {
      imageUrl: '/api/v1/storage/citizen-photo.png',
      scanReference: 'SCN-0001',
      detectedFields: [],
      citizenFollowUps: [],
    },
    events: [],
    inspection: null,
    ...overrides,
  };
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/complaints/c1']}>
      <Routes>
        <Route path="/complaints/:id" element={<ComplaintDetailPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  mockUser = {
    id: 'u1',
    fullName: 'Officer',
    email: 'x@y.z',
    role: 'INSPECTOR',
    isActive: true,
    createdAt: '2026-01-01T00:00:00Z',
  };
  getMock.mockReset();
  transitionMock.mockReset();
  getMock.mockResolvedValue(makeDetail());
});

afterEach(cleanup);

describe('ComplaintDetail (UI-05 targeted inspection)', () => {
  it('offers Create Targeted Inspection on an ACCEPTED complaint', async () => {
    renderPage();
    expect(await screen.findByRole('button', { name: 'Create Targeted Inspection' })).toBeTruthy();
    expect(getMock).toHaveBeenCalledWith('c1');
  });

  it('summarizes the complaint in the confirmation panel; Cancel creates nothing', async () => {
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Create Targeted Inspection' }));

    // The pre-flight summary the spec requires.
    expect(screen.getByText('Create a targeted inspection')).toBeTruthy();
    // The reference appears both in the page header and the panel summary.
    expect(screen.getAllByText('CMP-00042').length).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByText('MRP appears inconsistent').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('DEMO Tea 250g').length).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByText('Pune').length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText('1 photo')).toBeTruthy();
    // Priority badge in the panel distinguishes system screening from an
    // official decision (the status card shows the screening badge too).
    expect(screen.getAllByText(/system screening/i).length).toBeGreaterThanOrEqual(2);
    // Honesty copy — a targeted inspection is not a violation finding.
    expect(screen.getByText(/inspector\s+independently verifies/i)).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(transitionMock).not.toHaveBeenCalled();
    expect(screen.queryByText('Create a targeted inspection')).toBeNull();
  });

  it('creates the inspection on confirm and surfaces the linked inspection', async () => {
    transitionMock.mockResolvedValue(
      makeDetail({
        status: 'INSPECTION_SCHEDULED',
        inspectionId: 'i1',
        inspectionReference: 'LM-00012345',
        inspection: { id: 'i1', referenceNo: 'LM-00012345', status: 'CREATED' },
      }),
    );
    renderPage();

    fireEvent.click(await screen.findByRole('button', { name: 'Create Targeted Inspection' }));
    fireEvent.click(screen.getByRole('button', { name: /Create inspection$/ }));

    await waitFor(() =>
      expect(transitionMock).toHaveBeenCalledWith('c1', {
        action: 'CREATE_INSPECTION',
        officialPriority: undefined,
      }),
    );
    // Success notice + the linked inspection card with an Open action.
    expect(await screen.findByText(/Targeted inspection created/i)).toBeTruthy();
    expect(await screen.findByText('LM-00012345')).toBeTruthy();
    expect(screen.getByRole('button', { name: /Open inspection/i })).toBeTruthy();
    // The complaint has moved past the convertible statuses — no second create.
    expect(screen.queryByRole('button', { name: 'Create Targeted Inspection' })).toBeNull();
  });

  it('shows the backend error when creation is rejected', async () => {
    transitionMock.mockRejectedValue(
      new ApiClientError(422, null, 'Additional information required: the complaint has no verifiable evidence'),
    );
    renderPage();

    fireEvent.click(await screen.findByRole('button', { name: 'Create Targeted Inspection' }));
    fireEvent.click(screen.getByRole('button', { name: /Create inspection$/ }));

    expect(
      await screen.findByText(/Additional information required: the complaint has no verifiable/i),
    ).toBeTruthy();
    expect(transitionMock).toHaveBeenCalledTimes(1);
  });

  it('hides all complaint actions from the read-only AUDITOR role', async () => {
    mockUser = { ...mockUser, id: 'u2', role: 'AUDITOR' };
    renderPage();
    await screen.findByText('CMP-00042');
    expect(screen.queryByRole('button', { name: 'Create Targeted Inspection' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Assign inspector' })).toBeNull();
    expect(screen.getByText(/read-only/i)).toBeTruthy();
  });

  it('duplicate protection: a linked inspection offers Open, not Create', async () => {
    getMock.mockResolvedValue(
      makeDetail({
        status: 'INSPECTION_SCHEDULED',
        inspectionId: 'i1',
        inspectionReference: 'LM-00012345',
        inspection: { id: 'i1', referenceNo: 'LM-00012345', status: 'ANALYZED' },
      }),
    );
    renderPage();
    await screen.findByText('LM-00012345');
    expect(screen.getByRole('button', { name: /Open inspection/i })).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Create Targeted Inspection' })).toBeNull();
  });

  it('finalized protection: a completed inspection is View, not Open', async () => {
    getMock.mockResolvedValue(
      makeDetail({
        status: 'INSPECTION_COMPLETED',
        inspectionId: 'i1',
        inspectionReference: 'LM-00012345',
        inspection: { id: 'i1', referenceNo: 'LM-00012345', status: 'COMPLETED' },
      }),
    );
    renderPage();
    expect(await screen.findByRole('button', { name: /View inspection/i })).toBeTruthy();
  });
});
