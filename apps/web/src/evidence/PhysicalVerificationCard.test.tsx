// @vitest-environment jsdom
//
// UI-07 §14 — measurement history card tests. The api client and the app
// context are mocked at module boundaries; PhysicalVerificationCard is the
// real implementation.
//
// The assertions encode the honesty contracts:
//   - every column is a real persisted field (ID · DECLARED · MEASURED ·
//     UNIT · INSTRUMENT · INSPECTOR · TIMESTAMP · STATUS)
//   - the difference column is labelled OBSERVED, never a legal deficiency
//   - instrument status is shown only when recorded, never invented
//   - an absent regulatory evaluation reads "Evaluation unavailable —
//     inspector review", never a guessed tolerance
//   - history is append-only and every row is openable

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { MeasurementHistory, MeasurementHistoryRow, User } from '@legalmet/types';

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

const historyMock = vi.fn();

vi.mock('../api/client', () => ({
  api: {
    getMeasurementHistory: (...a: unknown[]) => historyMock(...a),
  },
  ApiClientError: class extends Error {
    constructor(_status: number, _payload: unknown, message: string) {
      super(message);
    }
  },
}));

import { PhysicalVerificationCard } from './PhysicalVerificationCard';

// --- fixtures ----------------------------------------------------------------

function historyRow(overrides: Partial<MeasurementHistoryRow> = {}): MeasurementHistoryRow {
  return {
    measurementId: 'm1',
    taskId: 't1',
    taskStatus: 'COMPLETED',
    anchor: { kind: 'LOT_PACKAGE', lotPackageId: 'p1' },
    declaredValue: '500 g',
    measuredValue: 0.492,
    unit: 'kg',
    observed: {
      comparable: true,
      declared: { value: '500', unit: 'g', normalized: '500 g' },
      measured: { value: '0.492', unit: 'kg', normalized: '492 g' },
      difference: '-8',
      percentDifference: '-1.6',
      note: 'Observed difference — arithmetic only.',
    },
    instrumentId: 'SCALE-LM-0142',
    instrumentVerificationStatus: null,
    recordedBy: 'u1',
    recordedByName: 'Inspector',
    recordedAt: '2026-09-05T10:10:00Z',
    observation: null,
    notes: null,
    evaluation: {
      id: 'e1',
      status: 'UNAVAILABLE',
      outcome: null,
      ruleCode: null,
      ruleVersionId: null,
      provenance: {},
      detail: {
        reason: 'Applicable permissible error/procedure is not configured.',
        note: 'Inspector review required.',
      },
      evaluatedAt: '2026-09-05T10:10:00Z',
    },
    ...overrides,
  };
}

function makeHistory(rows: MeasurementHistoryRow[]): MeasurementHistory {
  return {
    inspectionId: 'i1',
    measurements: rows,
    boundaryNote: 'History is append-only.',
  };
}

function renderCard(enabled = true) {
  return render(
    <PhysicalVerificationCard inspectionId="i1" enabled={enabled} refreshKey={0} />,
  );
}

beforeEach(() => {
  historyMock.mockReset();
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

describe('PhysicalVerificationCard (UI-07 §14)', () => {
  it('shows every real column: declared, measured, instrument, inspector, timestamp, status', async () => {
    historyMock.mockResolvedValue(makeHistory([historyRow()]));
    renderCard();

    expect(await screen.findByText('500 g')).toBeTruthy();
    expect(screen.getByText('0.492 kg')).toBeTruthy();
    const row = screen.getByText('500 g').closest('tr')!;
    expect(row.textContent).toContain('SCALE-LM-0142');
    expect(row.textContent).toContain('Inspector');
    // The observed difference is labelled OBSERVED, in the declared unit.
    expect(row.textContent).toContain('-8');
    expect(row.textContent).toContain('(-1.6%)');
    expect(screen.getByText('Observed difference')).toBeTruthy();
    // Instrument verification status was not recorded — and is not invented.
    expect(screen.queryByText(/verified/i)).toBeNull();
  });

  it('labels an absent evaluation "unavailable — inspector review", never a guessed tolerance', async () => {
    historyMock.mockResolvedValue(makeHistory([historyRow()]));
    renderCard();

    expect(
      await screen.findByText(/Evaluation unavailable — inspector review/),
    ).toBeTruthy();
    expect(screen.queryByText(/within permissible error/i)).toBeNull();
    expect(screen.queryByText(/non.?compliant/i)).toBeNull();
  });

  it('shows the frozen EVALUATED outcome with its rule code', async () => {
    historyMock.mockResolvedValue(
      makeHistory([
        historyRow({
          evaluation: {
            id: 'e2',
            status: 'EVALUATED',
            outcome: 'EXCEEDS_TOLERANCE',
            ruleCode: 'DEMO-TOLERANCE-NET-QUANTITY',
            ruleVersionId: 'v1',
            provenance: {},
            detail: {
              tolerance: { type: 'PERCENT', value: '4.5', limitInDeclaredUnit: '22.5', observedMagnitude: '8' },
            },
            evaluatedAt: '2026-09-05T10:10:00Z',
          },
        }),
      ]),
    );
    renderCard();

    expect(
      await screen.findByText(/Exceeds permissible error · DEMO-TOLERANCE-NET-QUANTITY/),
    ).toBeTruthy();
  });

  it('opens a row with the full record (anchor, instrument honesty, evaluation note)', async () => {
    historyMock.mockResolvedValue(makeHistory([historyRow()]));
    renderCard();

    const cell = await screen.findByText('500 g');
    fireEvent.click(cell.closest('tr')!);

    expect(await screen.findByText(/Measurement m1/)).toBeTruthy();
    expect(screen.getByText(/verification status NOT RECORDED/)).toBeTruthy();
    expect(screen.getByText(/Regulatory evaluation unavailable/)).toBeTruthy();
    expect(screen.getByText(/Inspector review required/)).toBeTruthy();
    expect(screen.getByText(/never edited in place/)).toBeTruthy();
  });

  it('renders the honest empty state — no fabricated measurements', async () => {
    historyMock.mockResolvedValue(makeHistory([]));
    renderCard();

    expect(await screen.findByText(/No measurements recorded yet/)).toBeTruthy();
    expect(screen.getByText('0 recorded')).toBeTruthy();
  });

  it('renders nothing while disabled (no perception runs yet)', async () => {
    historyMock.mockResolvedValue(makeHistory([historyRow()]));
    const { container } = renderCard(false);
    expect(container.textContent).toBe('');
    expect(historyMock).not.toHaveBeenCalled();
  });

  it('reloads when the workspace bumps the refresh key after a write', async () => {
    historyMock.mockResolvedValue(makeHistory([historyRow()]));
    const { rerender } = renderCard(true);
    await screen.findByText('500 g');
    expect(historyMock).toHaveBeenCalledTimes(1);

    historyMock.mockResolvedValue(makeHistory([historyRow(), historyRow({ measurementId: 'm2' })]));
    rerender(<PhysicalVerificationCard inspectionId="i1" enabled={true} refreshKey={1} />);

    await waitFor(() => expect(historyMock).toHaveBeenCalledTimes(2));
    expect(await screen.findByText(/2 recorded/)).toBeTruthy();
  });
});
