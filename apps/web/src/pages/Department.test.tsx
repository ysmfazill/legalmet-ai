// @vitest-environment jsdom
//
// UI-04 — Department Command Center page tests.
//
// The api client and app context are mocked at the module boundary; everything
// inside the page (useAsync lifecycle, deep links, role-gated actions, honest
// empty/error states) is the real implementation.

import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { DepartmentDashboard, User } from '@legalmet/types';

import { MemoryRouter } from 'react-router-dom';

// --- module mocks (specifiers exactly as the page imports them) -------------
vi.mock('../api/client', () => ({
  api: { departmentDashboard: vi.fn() },
}));

let mockUser: User = { id: 'u1', fullName: 'Officer', isActive: true, createdAt: '2026-01-01T00:00:00Z', email: 'x@y.z', role: 'INSPECTOR' };

vi.mock('../app/AppContext', () => ({
  useApp: () => ({ user: mockUser }),
}));

import { api } from '../api/client';
import { DepartmentPage } from './Department';

const dashboardMock = vi.mocked(api.departmentDashboard);

// --- fixtures ----------------------------------------------------------------

function makeDashboard(overrides: Partial<DepartmentDashboard> = {}): DepartmentDashboard {
  return {
    generatedAt: '2026-09-05T10:00:00Z',
    windowDays: 30,
    windowComplaints: 4,
    kpis: {
      totalComplaints: 10,
      pendingReview: 3,
      highPriority: 2,
      convertedToInspection: 4,
      underInvestigation: 2,
      resolved: 2,
      rejected: 1,
      unassignedOpen: 1,
    },
    statusDistribution: { SUBMITTED: 3, ACCEPTED: 2, REJECTED: 1 },
    trend: [
      { date: '2026-09-01', count: 2 },
      { date: '2026-09-02', count: 0 },
      { date: '2026-09-03', count: 1 },
    ],
    riskDistribution: { HIGH: 2, MEDIUM: 1, LOW: 1, UNSET: 0 },
    evidence: { average: 72, scored: 4, complete: 1, partial: 2, minimal: 1 },
    physicalVerification: {
      inspectionsRequiringVerification: 2,
      measurementsCompleted: 5,
      lotsUnderVerification: 1,
      lotsAwaitingMeasurement: 1,
      lotsCompleted: 0,
    },
    needsAttention: [
      {
        kind: 'HIGH_PRIORITY_AWAITING_REVIEW',
        label: 'High-priority complaints awaiting review',
        description: 'open with effective priority HIGH',
        count: 2,
        filters: { risk: 'HIGH' },
      },
      {
        kind: 'ACCEPTED_AWAITING_ASSIGNMENT',
        label: 'Accepted, awaiting inspector assignment',
        description: 'accepted but no inspector yet',
        count: 0,
        filters: { status: 'ACCEPTED' },
      },
    ],
    pipeline: {
      citizenReports: 10,
      departmentReview: 6,
      accepted: 4,
      inspectionAssigned: 3,
      inspectionCompleted: 2,
      decision: 2,
    },
    locations: [
      { area: 'Pune', complaints: 6, highPriority: 2, inspections: 3 },
      { area: 'Mumbai', complaints: 4, highPriority: 0, inspections: 1 },
    ],
    recentActivity: [
      {
        id: 'a1',
        event: 'COMPLAINT_ACCEPTED',
        actorName: 'Insp. Rao',
        createdAt: '2026-09-04T09:00:00Z',
        reference: 'CMP-0004',
        reportId: 'r-0004',
      },
    ],
    priorityQueue: [
      {
        id: 'r-0001',
        reference: 'CMP-0001',
        status: 'ACCEPTED',
        product: 'Sunflower Oil 1L',
        issue: 'Suspected underweight',
        location: 'Pune',
        priority: 'HIGH',
        prioritySource: 'SYSTEM_SCREENING',
        evidenceCompleteness: 90,
        createdAt: '2026-08-28T09:00:00Z',
      },
      {
        id: 'r-0002',
        reference: 'CMP-0002',
        status: 'ASSIGNED',
        product: 'Wheat Flour 5kg',
        issue: 'MRP mismatch',
        location: 'Mumbai',
        priority: 'MEDIUM',
        prioritySource: 'OFFICIAL_DECISION',
        evidenceCompleteness: 60,
        createdAt: '2026-08-20T09:00:00Z',
      },
    ],
    ...overrides,
  };
}

function renderPage() {
  return render(
    <MemoryRouter>
      <DepartmentPage />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  mockUser = { id: 'u1', fullName: 'Officer', isActive: true, createdAt: '2026-01-01T00:00:00Z', email: 'x@y.z', role: 'INSPECTOR' };
  dashboardMock.mockReset();
});

afterEach(cleanup);

// --- tests --------------------------------------------------------------------

describe('DepartmentPage (UI-04)', () => {
  it('renders the loading state before data arrives (never fake values)', () => {
    dashboardMock.mockReturnValue(new Promise(() => {}));
    renderPage();
    expect(screen.getByText('Loading complaints…')).toBeTruthy();
    // KPI values must not be fabricated while loading.
    expect(screen.queryByText('Total complaints')).toBeNull();
  });

  it('renders KPI cards, pipeline counts and activity from real data', async () => {
    dashboardMock.mockResolvedValue(makeDashboard());
    renderPage();

    await waitFor(() => {
      expect(screen.getByText('Priority complaints')).toBeTruthy();
    });

    // Header.
    expect(screen.getByRole('heading', { level: 1, name: 'Department Command Center' })).toBeTruthy();

    // KPI values (real counts from the payload).
    expect(screen.getByText('Total complaints')).toBeTruthy();
    const total = screen.getByText('Total complaints').closest('a');
    expect(total?.textContent).toContain('10');

    // Pipeline — real counts, actor-labelled.
    expect(screen.getAllByText('10').length).toBeGreaterThan(0);
    expect(screen.getByText('Citizen reports')).toBeTruthy();
    expect(screen.getByText('Decisions recorded')).toBeTruthy();

    // Recent activity uses the audit event label, links to the complaint.
    const activity = screen.getByText('Complaint accepted').closest('a');
    expect(activity?.getAttribute('href')).toBe('/complaints/r-0004');

    // Priority queue rows are present with their references.
    expect(screen.getByText('CMP-0001')).toBeTruthy();
  });

  it('deep-links KPI cards and needs-attention items into the filtered queue', async () => {
    dashboardMock.mockResolvedValue(makeDashboard());
    renderPage();
    await waitFor(() => screen.getByText('Priority complaints'));

    const pending = screen.getByText('Pending review').closest('a');
    expect(pending?.getAttribute('href')).toBe(
      '/complaints?status=SUBMITTED,UNDER_REVIEW,REQUEST_INFORMATION',
    );

    const rejected = screen
      .getAllByText('Rejected')
      .map((el) => el.closest('a'))
      .find((a) => a?.getAttribute('href') === '/complaints?status=REJECTED');
    expect(rejected).toBeTruthy();

    // Needs attention: only actionable (count > 0) items are links.
    const high = screen.getByText('High-priority complaints awaiting review').closest('a');
    expect(high?.getAttribute('href')).toBe('/complaints?risk=HIGH');
    const zeroed = screen.getByText('Accepted, awaiting inspector assignment').closest('a');
    expect(zeroed).toBeNull();
  });

  it('shows the honest empty state when the database has no complaints', async () => {
    dashboardMock.mockResolvedValue(
      makeDashboard({
        windowComplaints: 0,
        kpis: {
          totalComplaints: 0,
          pendingReview: 0,
          highPriority: 0,
          convertedToInspection: 0,
          underInvestigation: 0,
          resolved: 0,
          rejected: 0,
          unassignedOpen: 0,
        },
        trend: [],
        locations: [],
        priorityQueue: [],
        recentActivity: [],
        needsAttention: [],
        riskDistribution: {},
        evidence: { average: 0, scored: 0, complete: 0, partial: 0, minimal: 0 },
        physicalVerification: {
          inspectionsRequiringVerification: 0,
          measurementsCompleted: 0,
          lotsUnderVerification: 0,
          lotsAwaitingMeasurement: 0,
          lotsCompleted: 0,
        },
        pipeline: {
          citizenReports: 0,
          departmentReview: 0,
          accepted: 0,
          inspectionAssigned: 0,
          inspectionCompleted: 0,
          decision: 0,
        },
      }),
    );
    renderPage();

    await waitFor(() => screen.getByText('No complaints yet'));
    expect(screen.getByText(/Citizen complaint analytics appear/i)).toBeTruthy();
    // The analytics sections must not render for an empty database.
    expect(screen.queryByText('Priority complaints')).toBeNull();
  });

  it('shows the error state with Retry when the dashboard API fails', async () => {
    dashboardMock
      .mockRejectedValueOnce(new Error('Network down'))
      .mockResolvedValueOnce(makeDashboard());
    renderPage();

    await waitFor(() => screen.getByText('Unable to load dashboard'));
    expect(screen.getByText('Network down')).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: /retry/i }));
    await waitFor(() => screen.getByText('Priority complaints'));
    expect(dashboardMock).toHaveBeenCalledTimes(2);
  });

  it('re-queries when the trend window changes (7 / 30 / 90 days)', async () => {
    dashboardMock.mockResolvedValue(makeDashboard());
    renderPage();
    await waitFor(() => screen.getByText('Priority complaints'));

    fireEvent.click(screen.getByRole('button', { name: '7 Days' }));
    await waitFor(() => expect(dashboardMock).toHaveBeenLastCalledWith(7));
  });

  it('hides write actions from read-only roles (AUDITOR)', async () => {
    mockUser = {
      id: 'u2',
      fullName: 'Auditor',
      email: 'a@y.z',
      role: 'AUDITOR',
      isActive: true,
      createdAt: '2026-01-01T00:00:00Z',
    };
    dashboardMock.mockResolvedValue(makeDashboard());
    renderPage();
    await waitFor(() => screen.getByText('CMP-0001'));

    expect(screen.queryByText('Assign')).toBeNull();
    expect(screen.queryByText('Convert to inspection')).toBeNull();
    // Read actions remain available to everyone.
    expect(screen.getAllByText('View complaint').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Review evidence').length).toBeGreaterThan(0);
  });

  it('shows only legal write actions for INSPECTOR', async () => {
    dashboardMock.mockResolvedValue(makeDashboard());
    renderPage();
    await waitFor(() => screen.getByText('CMP-0001'));

    // ACCEPTED row: Assign + Convert are both legal.
    const acceptedRow = screen.getByText('CMP-0001').closest('li') as HTMLElement;
    expect(within(acceptedRow).getByText('Assign')).toBeTruthy();
    expect(within(acceptedRow).getByText('Convert to inspection')).toBeTruthy();

    // ASSIGNED row: only Convert (Assign is not a legal edge from ASSIGNED).
    const assignedRow = screen.getByText('CMP-0002').closest('li') as HTMLElement;
    expect(within(assignedRow).queryByRole('link', { name: 'Assign' })).toBeNull();
    expect(within(assignedRow).getByText('Convert to inspection')).toBeTruthy();

    // The queue actions deep-link into the complaint with the action preset.
    const convert = within(acceptedRow).getByText('Convert to inspection');
    expect(convert?.closest('a')?.getAttribute('href')).toBe('/complaints/r-0001?action=inspect');
  });
});
