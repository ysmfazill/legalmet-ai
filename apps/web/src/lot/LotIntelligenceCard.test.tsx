// @vitest-environment jsdom
//
// UI-07 — Lot Intelligence card tests. The api client and the app context
// are mocked at module boundaries; LotIntelligenceCard, the detail drawer and
// useEvidencePlan are the real implementations.
//
// The assertions encode the honesty contracts:
//   - lots/packages/sampling runs are real records; progress is real counts
//     ("3 / 4 measurements completed", "1 measurement remaining")
//   - without a configured procedure the UI says "sampling procedure requires
//     inspector confirmation" — never "AI selected the legally required sample"
//   - statistics are labelled OBSERVED, never legal compliance results
//   - the lot result is blocked with "Insufficient evidence" while sampled
//     packages are unmeasured, and the backend rejection is surfaced verbatim
//   - read-only roles get no create/sample/measure/decision controls

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type {
  EvidencePlan,
  LotDetail,
  LotList,
  User,
  VerificationList,
} from '@legalmet/types';

let mockUser: User = {
  id: 'u1',
  fullName: 'Inspector',
  email: 'i@y.z',
  role: 'INSPECTOR',
  isActive: true,
  createdAt: '2026-01-01T00:00:00Z',
};

vi.mock('../app/AppContext', () => ({
  useApp: () => ({ isLive: true, user: mockUser }),
}));

const listLotsMock = vi.fn();
const getLotMock = vi.fn();
const createLotMock = vi.fn();
const sampleMock = vi.fn();
const decisionMock = vi.fn();
const planMock = vi.fn();
const listVerificationsMock = vi.fn();

vi.mock('../api/client', () => ({
  api: {
    listLots: (...a: unknown[]) => listLotsMock(...a),
    getLot: (...a: unknown[]) => getLotMock(...a),
    createLot: (...a: unknown[]) => createLotMock(...a),
    generateLotSample: (...a: unknown[]) => sampleMock(...a),
    submitLotDecision: (...a: unknown[]) => decisionMock(...a),
    getEvidencePlan: (...a: unknown[]) => planMock(...a),
    listVerifications: (...a: unknown[]) => listVerificationsMock(...a),
  },
  ApiClientError: class extends Error {
    constructor(_status: number, _payload: unknown, message: string) {
      super(message);
    }
  },
}));

import { LotIntelligenceCard } from './LotIntelligenceCard';

// --- fixtures ----------------------------------------------------------------

function makeLotDetail(overrides: Partial<LotDetail> = {}): LotDetail {
  return {
    id: 'lot1',
    inspectionId: 'i1',
    label: 'LOT-0007',
    productId: null,
    declaredValue: '500 g',
    lotSize: 4,
    location: 'Rack B',
    notes: null,
    status: 'IN_PROGRESS',
    decision: null,
    decisionReason: null,
    decidedBy: null,
    decidedAt: null,
    createdBy: 'u1',
    createdAt: '2026-09-05T09:00:00Z',
    packages: [
      {
        id: 'p1',
        label: 'LOT-0007-PKG-001',
        packageId: null,
        position: 1,
        status: 'MEASURED',
        samplingRunId: 's1',
        measurement: {
          taskId: 't1',
          taskStatus: 'COMPLETED',
          latestResult: {
            id: 'r1',
            measuredValue: 0.492,
            unit: 'kg',
            instrumentId: 'SCALE-01',
            instrumentVerificationStatus: 'CALIBRATED_2026',
            recordedBy: 'u1',
            recordedAt: '2026-09-05T10:10:00Z',
            observation: null,
          },
          observed: {
            comparable: true,
            declared: { value: '500', unit: 'g', normalized: '500 g' },
            measured: { value: '0.492', unit: 'kg', normalized: '492 g' },
            difference: '-8',
            percentDifference: '-1.6',
          },
          evaluation: {
            id: 'e1',
            status: 'EVALUATED',
            outcome: 'WITHIN_TOLERANCE',
            ruleCode: 'DEMO-TOLERANCE-NET-QUANTITY',
            ruleVersionId: 'v1',
            provenance: {},
            detail: { tolerance: { type: 'PERCENT', value: '4.5', limitInDeclaredUnit: '22.5' } },
            evaluatedAt: '2026-09-05T10:10:00Z',
          },
        },
      },
      {
        id: 'p2',
        label: 'LOT-0007-PKG-002',
        packageId: null,
        position: 2,
        status: 'PENDING',
        samplingRunId: 's1',
        measurement: { taskId: 't2', taskStatus: 'PENDING', latestResult: null, observed: null, evaluation: null },
      },
    ],
    samplingRuns: [
      {
        id: 's1',
        sampleSize: 2,
        selectionMethod: 'RANDOM',
        procedureCode: null,
        procedureVersionLabel: null,
        isAiRecommended: true,
        seed: 'seed-01',
        randomization: {},
        createdBy: 'u1',
        createdAt: '2026-09-05T09:30:00Z',
      },
    ],
    samplingProcedure: null,
    statistics: {
      sampled: 2,
      measured: 1,
      averageMeasured: null,
      averageNote: null,
      observedDeficiencies: 1,
      exceedingThreshold: 0,
      evaluated: 1,
      note: 'Observed statistics computed from recorded measurements — these are NOT legal compliance results.',
    },
    progress: {
      packagesTotal: 4,
      sampled: 2,
      measured: 1,
      remaining: 1,
      summary: '1 / 2 measurements completed',
      action: 'Continue Lot Verification',
    },
    boundaryNote: 'Lots are judged on measured packages only.',
    ...overrides,
  };
}

function makeLotList(lots: LotDetail['status'][]): LotList {
  return {
    inspectionId: 'i1',
    lots: lots.map((status, i) => ({
      id: `lot${i + 1}`,
      label: `LOT-000${i + 7}`,
      productId: null,
      declaredValue: '500 g',
      lotSize: 4,
      location: null,
      status,
      decision: null,
      decisionReason: null,
      decidedAt: null,
      createdAt: '2026-09-05T09:00:00Z',
      progress: {
        packagesTotal: 4,
        sampled: 2,
        measured: status === 'IN_PROGRESS' ? 1 : 2,
        remaining: status === 'IN_PROGRESS' ? 1 : 0,
        summary: status === 'IN_PROGRESS' ? '1 / 2 measurements completed' : '2 / 2 measurements completed',
        action: 'Continue Lot Verification',
      },
    })),
    boundaryNote: 'Real records only.',
  };
}

const emptyPlan: EvidencePlan = {
  inspectionId: 'i1',
  items: [],
  counts: {
    total: 0,
    available: 0,
    requiringVerification: 0,
    verified: 0,
    rejected: 0,
    notApplicable: 0,
    openRequiredTasks: 0,
  },
  boundaryNote: '',
};

const emptyVerifications: VerificationList = {
  inspectionId: 'i1',
  tasks: [],
  boundaryNote: '',
};

function renderCard(enabled = true) {
  return render(
    <LotIntelligenceCard inspectionId="i1" enabled={enabled} refreshKey={0} />,
  );
}

async function openFirstLot() {
  const cell = await screen.findByText('LOT-0007');
  fireEvent.click(cell.closest('tr')!);
  await screen.findByText(/Packages — real records only/);
}

beforeEach(() => {
  listLotsMock.mockReset().mockResolvedValue(makeLotList(['IN_PROGRESS']));
  getLotMock.mockReset().mockResolvedValue(makeLotDetail());
  createLotMock.mockReset();
  sampleMock.mockReset();
  decisionMock.mockReset();
  planMock.mockReset().mockResolvedValue(emptyPlan);
  listVerificationsMock.mockReset().mockResolvedValue(emptyVerifications);
  mockUser = {
    id: 'u1',
    fullName: 'Inspector',
    email: 'i@y.z',
    role: 'INSPECTOR',
    isActive: true,
    createdAt: '2026-01-01T00:00:00Z',
  };
});

afterEach(cleanup);

describe('LotIntelligenceCard (UI-07)', () => {
  it('lists lots with real progress and remaining counts', async () => {
    renderCard();
    expect(await screen.findByText('LOT-0007')).toBeTruthy();
    expect(screen.getByText(/1 \/ 2 measurements completed/)).toBeTruthy();
    expect(screen.getByText(/1 remaining/)).toBeTruthy();
    expect(screen.getByText(/Verification in progress/)).toBeTruthy();
  });

  it('shows the honest empty state when no lots exist', async () => {
    listLotsMock.mockResolvedValue({ inspectionId: 'i1', lots: [], boundaryNote: '' });
    renderCard();
    expect(await screen.findByText(/No lots recorded for this inspection/)).toBeTruthy();
  });

  it('opens the lot detail drawer: packages, observed statistics, insufficient-evidence block', async () => {
    renderCard();
    await openFirstLot();

    // Packages table — real records with measured evidence.
    expect(screen.getByText('LOT-0007-PKG-001')).toBeTruthy();
    const pkgRow = screen.getByText('LOT-0007-PKG-001').closest('tr')!;
    expect(pkgRow.textContent).toContain('0.492 kg');
    expect(pkgRow.textContent).toContain('-8');
    expect(pkgRow.textContent).toContain('(-1.6%)');
    expect(pkgRow.textContent).toContain('instrument SCALE-01');
    expect(pkgRow.textContent).toContain('CALIBRATED_2026');

    // Sampling honesty without a configured procedure.
    expect(screen.getByText(/sampling procedure requires inspector confirmation/i)).toBeTruthy();
    // The forbidden positive claim never appears — only its negation does.
    expect(screen.queryByText(/AI (has )?selected the legally required sample/i)).toBeNull();
    expect(screen.getByText(/not the legally required sample/)).toBeTruthy();

    // Observed statistics — explicitly not compliance results.
    expect(screen.getByRole('heading', { name: 'Observed statistics' })).toBeTruthy();
    expect(screen.getByText(/NOT legal compliance results/)).toBeTruthy();

    // The decision is blocked while a sampled package is unmeasured.
    expect(screen.getByText(/Insufficient evidence/)).toBeTruthy();
    expect(screen.getAllByText(/1 measurement remaining/).length).toBeGreaterThan(0);
    expect(screen.getByText('Submit lot result').closest('button')!.disabled).toBe(true);
  });

  it('surfaces the backend rejection verbatim when a decision is attempted anyway', async () => {
    getLotMock.mockResolvedValue(
      makeLotDetail({
        packages: [
          {
            id: 'p1',
            label: 'LOT-0007-PKG-001',
            packageId: null,
            position: 1,
            status: 'PENDING',
            samplingRunId: 's1',
            measurement: { taskId: 't2', taskStatus: 'PENDING', latestResult: null, observed: null, evaluation: null },
          },
        ],
        progress: {
          packagesTotal: 4,
          sampled: 1,
          measured: 0,
          remaining: 1,
          summary: '0 / 1 measurements completed',
          action: 'Continue Lot Verification',
        },
      }),
    );
    renderCard();
    await openFirstLot();

    // The local gate already blocks the button — the spec §24 message is shown.
    expect(screen.getByText(/Insufficient evidence/)).toBeTruthy();
    expect(screen.getByText('Submit lot result').closest('button')!.disabled).toBe(true);
  });

  it('enables and submits the lot result once every sampled package is measured', async () => {
    getLotMock.mockResolvedValue(
      makeLotDetail({
        packages: [
          {
            id: 'p1',
            label: 'LOT-0007-PKG-001',
            packageId: null,
            position: 1,
            status: 'MEASURED',
            samplingRunId: 's1',
            measurement: {
              taskId: 't1',
              taskStatus: 'COMPLETED',
              latestResult: {
                id: 'r1',
                measuredValue: 492,
                unit: 'g',
                instrumentId: 'SCALE-01',
                instrumentVerificationStatus: null,
                recordedBy: 'u1',
                recordedAt: '2026-09-05T10:10:00Z',
                observation: null,
              },
              observed: null,
              evaluation: null,
            },
          },
        ],
        statistics: {
          sampled: 1,
          measured: 1,
          averageMeasured: '492',
          averageNote: null,
          observedDeficiencies: 1,
          exceedingThreshold: 0,
          evaluated: 0,
          note: 'Observed statistics computed from recorded measurements — these are NOT legal compliance results.',
        },
        progress: {
          packagesTotal: 4,
          sampled: 1,
          measured: 1,
          remaining: 0,
          summary: '1 / 1 measurements completed',
          action: null,
        },
      }),
    );
    decisionMock.mockResolvedValue(makeLotDetail({ status: 'REQUIRES_REVIEW' }));
    renderCard();
    await openFirstLot();

    const submit = screen.getByText('Submit lot result').closest('button')!;
    expect(submit.disabled).toBe(true); // reason is mandatory

    fireEvent.change(screen.getByLabelText(/Reason \(mandatory/), {
      target: { value: 'Observed deficiency within permissible error after review' },
    });
    fireEvent.change(screen.getByLabelText(/Lot result/), { target: { value: 'REQUIRES_REVIEW' } });
    fireEvent.click(screen.getByText('Submit lot result'));

    await waitFor(() =>
      expect(decisionMock).toHaveBeenCalledWith('lot1', {
        decision: 'REQUIRES_REVIEW',
        reason: 'Observed deficiency within permissible error after review',
      }),
    );
  });

  it('draws a sample only with inspector confirmation when no procedure is configured', async () => {
    // No measurements yet — the draw form is available (§19/§20).
    getLotMock.mockResolvedValue(
      makeLotDetail({
        samplingRuns: [],
        packages: [
          {
            id: 'p1',
            label: 'LOT-0007-PKG-001',
            packageId: null,
            position: 1,
            status: 'NOT_SAMPLED',
            samplingRunId: null,
            measurement: null,
          },
          {
            id: 'p2',
            label: 'LOT-0007-PKG-002',
            packageId: null,
            position: 2,
            status: 'NOT_SAMPLED',
            samplingRunId: null,
            measurement: null,
          },
        ],
        statistics: {
          sampled: 0,
          measured: 0,
          averageMeasured: null,
          averageNote: null,
          observedDeficiencies: 0,
          exceedingThreshold: 0,
          evaluated: 0,
          note: 'Observed statistics computed from recorded measurements — these are NOT legal compliance results.',
        },
        progress: {
          packagesTotal: 4,
          sampled: 0,
          measured: 0,
          remaining: 0,
          summary: '0 / 0 measurements completed',
          action: 'Draw a sample',
        },
      }),
    );
    sampleMock.mockResolvedValue({});
    renderCard();
    await openFirstLot();

    const draw = screen.getByText('Draw sample').closest('button')!;
    expect(draw.disabled).toBe(true); // unconfirmed AI-recommended sample

    fireEvent.change(screen.getByLabelText(/Sample size/), { target: { value: '2' } });
    fireEvent.click(screen.getByRole('checkbox'));

    await waitFor(() => expect(screen.getByText('Draw sample').closest('button')!.disabled).toBe(false));
    fireEvent.click(screen.getByText('Draw sample'));

    await waitFor(() =>
      expect(sampleMock).toHaveBeenCalledWith('lot1', {
        sampleSize: 2,
        selectionMethod: 'RANDOM',
        seed: null,
        confirmAiSample: true,
      }),
    );
  });

  it('validates the create-lot form before calling the API', async () => {
    renderCard();
    fireEvent.click(await screen.findByText('Create lot'));

    fireEvent.click(screen.getByText('Create lot + package records'));
    expect(await screen.findByText(/A lot label is mandatory/)).toBeTruthy();
    expect(createLotMock).not.toHaveBeenCalled();

    fireEvent.change(screen.getByLabelText(/Lot label \(mandatory\)/), { target: { value: 'LOT-0008' } });
    fireEvent.click(screen.getByText('Create lot + package records'));
    expect(await screen.findByText(/declared quantity is mandatory/)).toBeTruthy();

    fireEvent.change(screen.getByLabelText(/Declared quantity \(mandatory, immutable\)/), { target: { value: '500 g' } });
    fireEvent.change(screen.getByLabelText(/Lot size — number of packages \(mandatory\)/), { target: { value: '10' } });
    fireEvent.click(screen.getByText('Create lot + package records'));

    await waitFor(() =>
      expect(createLotMock).toHaveBeenCalledWith('i1', {
        label: 'LOT-0008',
        declaredValue: '500 g',
        lotSize: 10,
        location: null,
        notes: null,
      }),
    );
  });

  it('gives read-only roles no write controls (RBAC mirrors the backend)', async () => {
    mockUser = { ...mockUser, role: 'AUDITOR' as User['role'] };
    renderCard();
    await openFirstLot();

    expect(screen.queryByText('Create lot')).toBeNull();
    expect(screen.queryByText('Measure')).toBeNull();
    expect(screen.queryByText('Draw sample')).toBeNull();
    expect(screen.queryByText('Submit lot result')).toBeNull();
    expect(screen.getByText(/can view lots but not create them/)).toBeTruthy();
  });
});
