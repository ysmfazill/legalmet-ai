// @vitest-environment jsdom
//
// UI-06 — Evidence Planner + Verification panel tests. The api client and the
// app context are mocked at module boundaries; EvidencePlannerLive,
// VerificationPanel and useEvidencePlan are the real implementations.
//
// The assertions encode the honesty contracts:
//   - DECLARED and MEASURED are shown side by side and never merged
//   - a gap is NOT a compliance verdict
//   - measurement entry is labelled MANUAL (no hardware integration)
//   - instrument status is never invented
//   - results are append-only (a completed task cannot be reopened)
//   - read-only roles get no write controls

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type {
  AuditEvent,
  EvidencePlan,
  EvidencePlanItem,
  User,
  VerificationList,
  VerificationResult,
  VerificationTask,
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

const planMock = vi.fn();
const listMock = vi.fn();
const createMock = vi.fn();
const startMock = vi.fn();
const resultMock = vi.fn();
const cancelMock = vi.fn();
const auditMock = vi.fn();

vi.mock('../api/client', () => ({
  api: {
    getEvidencePlan: (...a: unknown[]) => planMock(...a),
    listVerifications: (...a: unknown[]) => listMock(...a),
    createVerification: (...a: unknown[]) => createMock(...a),
    startVerification: (...a: unknown[]) => startMock(...a),
    recordVerificationResult: (...a: unknown[]) => resultMock(...a),
    cancelVerification: (...a: unknown[]) => cancelMock(...a),
    getInspectionAudit: (...a: unknown[]) => auditMock(...a),
  },
  ApiClientError: class extends Error {
    constructor(_status: number, _payload: unknown, message: string) {
      super(message);
    }
  },
}));

import { EvidencePlannerLive } from './EvidencePlannerLive';
import { EvidenceTimelineCard } from './EvidenceTimelineCard';

// --- fixtures ----------------------------------------------------------------

function makeResult(overrides: Partial<VerificationResult> = {}): VerificationResult {
  return {
    id: 'r1',
    taskId: 't1',
    recordedBy: 'u1',
    recordedByName: 'Inspector',
    measuredValue: 492,
    unit: 'g',
    observation: null,
    instrumentId: 'SCALE-LM-0142',
    instrumentVerificationStatus: null,
    notes: null,
    recordedAt: '2026-09-05T10:10:00Z',
    createdAt: '2026-09-05T10:10:00Z',
    ...overrides,
  };
}

function makeTask(overrides: Partial<VerificationTask> = {}): VerificationTask {
  return {
    id: 't1',
    inspectionId: 'i1',
    findingId: 'f1',
    extractedFieldId: null,
    taskType: 'MEASUREMENT',
    requirementLevel: 'REQUIRED',
    reason: 'Verify the physical net quantity with a calibrated scale',
    status: 'PENDING',
    createdBy: 'u1',
    createdByName: 'Inspector',
    startedAt: null,
    completedAt: null,
    cancelledReason: null,
    results: [],
    createdAt: '2026-09-05T10:00:00Z',
    boundaryNote: 'The system never converts a declared-vs-measured difference into a violation.',
    ...overrides,
  };
}

function netQuantityRow(overrides: Partial<EvidencePlanItem> = {}): EvidencePlanItem {
  return {
    findingId: 'f1',
    fieldId: 'fl1',
    title: 'Net quantity declaration',
    declaredValue: '500',
    unit: 'g',
    confidence: 0.94,
    requirementCode: 'LMPC-4.2',
    requirementTitle: 'Net quantity declaration',
    ruleCode: 'NET_QTY_DECLARED',
    versionLabel: 'LMPC 2011 (2023 amendment)',
    findingStatus: 'COMPLIANT',
    severity: 'INFO',
    applicability: 'YES',
    reviewState: 'PENDING_REVIEW',
    evidence: [
      { kind: 'IMAGE', status: 'AVAILABLE', label: 'Front label image' },
      { kind: 'OCR', status: 'AVAILABLE', label: 'OCR text' },
      { kind: 'FIELD', status: 'AVAILABLE', label: 'Extracted field' },
      { kind: 'MEASUREMENT', status: 'MISSING', label: 'Physical measurement' },
    ],
    gaps: [
      {
        kind: 'MEASUREMENT',
        reason:
          'Physical net quantity is not verified — the system can only read the value DECLARED on the package; it cannot weigh the contents.',
        required: true,
        defaultLevel: 'REQUIRED',
        taskId: null,
        taskStatus: null,
      },
    ],
    status: 'REQUIRES_VERIFICATION',
    summary:
      'The declared value was read from the label. Evidence completeness is NOT a compliance verdict.',
    verification: null,
    ...overrides,
  };
}

function mrpRow(): EvidencePlanItem {
  return {
    findingId: 'f2',
    fieldId: 'fl2',
    title: 'MRP declaration',
    declaredValue: '45',
    unit: '₹',
    confidence: 0.42,
    requirementCode: 'LMPC-4.1',
    requirementTitle: 'MRP declaration',
    findingStatus: 'REVIEW_REQUIRED',
    severity: 'MINOR',
    applicability: 'YES',
    reviewState: 'PENDING_REVIEW',
    evidence: [{ kind: 'OCR', status: 'AVAILABLE', label: 'OCR text' }],
    gaps: [
      {
        kind: 'INSPECTOR_OBSERVATION',
        reason: 'Low-confidence extraction (42%) — an inspector should re-read the marking in person.',
        required: false,
        defaultLevel: 'RECOMMENDED',
        taskId: null,
        taskStatus: null,
      },
    ],
    status: 'REQUIRES_VERIFICATION',
    summary: 'Perception confidence is low. Verify before relying on the extracted value.',
    verification: null,
  };
}

function makePlan(overrides: Partial<EvidencePlan> = {}): EvidencePlan {
  const items = overrides.items ?? [netQuantityRow(), mrpRow()];
  return {
    inspectionId: 'i1',
    items,
    counts: {
      total: items.length,
      available: items.filter((i) => i.status === 'AVAILABLE').length,
      requiringVerification: items.filter((i) => i.status === 'REQUIRES_VERIFICATION').length,
      verified: items.filter((i) => i.status === 'VERIFIED').length,
      rejected: items.filter((i) => i.status === 'REJECTED').length,
      notApplicable: items.filter((i) => i.status === 'NOT_APPLICABLE').length,
      openRequiredTasks: items.filter(
        (i) => i.gaps.some((g) => g.required) && i.gaps.some((g) => g.taskId),
      ).length,
    },
    boundaryNote: 'The system never converts a declared-vs-measured difference into a violation.',
    ...overrides,
  };
}

/** A plan whose net-quantity row carries the given live task. */
function planWithTask(task: VerificationTask): EvidencePlan {
  const open = task.status === 'PENDING' || task.status === 'IN_PROGRESS';
  return makePlan({
    items: [
      netQuantityRow({
        gaps: open
          ? [
              {
                kind: 'MEASUREMENT',
                reason: 'Physical net quantity is not verified.',
                required: true,
                defaultLevel: 'REQUIRED',
                taskId: task.id,
                taskStatus: task.status,
              },
            ]
          : [],
        status: task.status === 'COMPLETED' ? 'VERIFIED' : 'REQUIRES_VERIFICATION',
        summary:
          'A measurement was recorded. The system does not evaluate the measured value against the declaration.',
        verification: {
          id: task.id,
          taskType: task.taskType,
          status: task.status,
          requirementLevel: task.requirementLevel,
          reason: task.reason,
          createdAt: task.createdAt,
          startedAt: task.startedAt,
          completedAt: task.completedAt,
          latestResult: task.results[task.results.length - 1] ?? null,
        },
      }),
      mrpRow(),
    ],
  });
}

function makeList(tasks: VerificationTask[]): VerificationList {
  return { inspectionId: 'i1', tasks, boundaryNote: 'append-only' };
}

function renderPlanner(enabled = true) {
  return render(<EvidencePlannerLive inspectionId="i1" enabled={enabled} onChanged={() => {}} />);
}

beforeEach(() => {
  planMock.mockReset().mockResolvedValue(makePlan());
  listMock.mockReset().mockResolvedValue(makeList([]));
  createMock.mockReset();
  startMock.mockReset();
  resultMock.mockReset();
  cancelMock.mockReset();
  auditMock.mockReset();
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

describe('EvidencePlannerLive (UI-06)', () => {
  it('renders existing evidence, open gaps and the declared value — all from the server plan', async () => {
    renderPlanner();

    expect(await screen.findByText('Net quantity declaration')).toBeTruthy();
    // Declared value is shown exactly as read.
    expect(screen.getByText('500 g')).toBeTruthy();
    // Measured is honestly NOT VERIFIED — the system never fills it itself.
    expect(screen.getAllByText('NOT VERIFIED').length).toBeGreaterThan(0);
    // The gap is labelled REQUIRED and explains WHY (the camera cannot weigh).
    expect(screen.getByText('REQUIRED')).toBeTruthy();
    expect(screen.getByText(/cannot weigh the contents/i)).toBeTruthy();
    // The honesty banner: a gap is not a verdict.
    expect(screen.getAllByText(/NOT a compliance verdict/i).length).toBeGreaterThan(0);
    // Existing evidence chips — the real OCR/field/image are ✓, the
    // measurement is honestly absent.
    expect(screen.getAllByTitle('OCR text').length).toBeGreaterThan(0);
    expect(screen.getAllByTitle('Physical measurement').length).toBeGreaterThan(0);
  });

  it('marks low-confidence extractions as LOW CONFIDENCE without claiming a violation probability', async () => {
    renderPlanner();

    expect(await screen.findByText('MRP declaration')).toBeTruthy();
    expect(screen.getByText(/LOW CONFIDENCE/i)).toBeTruthy();
    expect(screen.getByText(/42% reading confidence/i)).toBeTruthy();
    // RECOMMENDED gaps are visibly advisory.
    expect(screen.getByText('RECOMMENDED')).toBeTruthy();
    // Perception confidence is never a violation probability — the planner
    // never phrases confidence as a chance of violation.
    expect(screen.queryByText(/probability/i)).toBeNull();
    expect(screen.queryByText(/chance of violation/i)).toBeNull();
  });

  it('creates a verification task only with a mandatory reason (explicit human action)', async () => {
    renderPlanner();
    await screen.findByText('Net quantity declaration');

    fireEvent.click(screen.getByRole('button', { name: /start measurement/i }));

    const reason = screen.getByLabelText(/Reason \(mandatory/i);
    // The create button stays disabled until the reason has content.
    const create = screen.getByRole('button', { name: /create verification task/i });
    expect(create.hasAttribute('disabled')).toBe(true);
    fireEvent.change(reason, { target: { value: 'Verify with the shop scale' } });
    expect(create.hasAttribute('disabled')).toBe(false);

    createMock.mockResolvedValue(makeTask());
    fireEvent.click(create);

    await waitFor(() =>
      expect(createMock).toHaveBeenCalledWith('i1', {
        findingId: 'f1',
        fieldId: 'fl1',
        type: 'MEASUREMENT',
        reason: 'Verify with the shop scale',
        requirementLevel: 'REQUIRED',
      }),
    );
  });

  it('AUDITOR sees the plan but no write controls', async () => {
    mockUser = { ...mockUser, role: 'AUDITOR' };
    renderPlanner();
    await screen.findByText('Net quantity declaration');

    expect(screen.queryByRole('button', { name: /start measurement/i })).toBeNull();
    expect(
      screen.getByText(/Your role can view the plan but not create verification tasks/i),
    ).toBeTruthy();
  });

  it('renders nothing until perception data exists (enabled=false)', async () => {
    const { container } = renderPlanner(false);
    await Promise.resolve();
    expect(container.textContent).toBe('');
    expect(planMock).not.toHaveBeenCalled();
  });
});

describe('VerificationPanel (UI-06)', () => {
  it('labels measurement entry as MANUAL and shows DECLARED beside MEASURED without judging', async () => {
    planMock.mockResolvedValue(planWithTask(makeTask()));
    listMock.mockResolvedValue(makeList([makeTask()]));
    renderPlanner();

    fireEvent.click(await screen.findByRole('button', { name: /record measurement/i }));

    expect(await screen.findByText('Measurement verification')).toBeTruthy();
    // MANUAL entry, honestly labelled — no hardware integration is pretended.
    expect(screen.getByText('Manual measurement entry')).toBeTruthy();
    expect(screen.getByText(/not connected to a physical scale/i)).toBeTruthy();
    // DECLARED (from the label) and MEASURED (inspector-only) side by side —
    // once in the plan row and once in the panel, never merged.
    expect(screen.getAllByText('Declared value').length).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByText('Measured value').length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText(/Read from the label — never modified here/i)).toBeTruthy();
    expect(screen.getAllByText(/Only an inspector can record a measurement/i).length).toBeGreaterThan(0);
  });

  it('validates the measurement form: positive value and unit are mandatory', async () => {
    planMock.mockResolvedValue(planWithTask(makeTask()));
    listMock.mockResolvedValue(makeList([makeTask()]));
    renderPlanner();

    fireEvent.click(await screen.findByRole('button', { name: /record measurement/i }));
    await screen.findByText('Measurement verification');

    const submit = screen.getByRole('button', { name: /record result & complete task/i });
    fireEvent.click(submit);
    expect(await screen.findByText(/positive number/i)).toBeTruthy();
    expect(resultMock).not.toHaveBeenCalled();

    // Value present but the unit field cleared → the unit is mandatory too.
    fireEvent.change(screen.getByLabelText(/measured value \(mandatory\)/i), {
      target: { value: '492' },
    });
    fireEvent.change(screen.getByLabelText(/unit \(mandatory\)/i), { target: { value: '' } });
    fireEvent.click(submit);
    expect(await screen.findByText(/unit is mandatory/i)).toBeTruthy();
    expect(resultMock).not.toHaveBeenCalled();
  });

  it('submits the measurement with instrument metadata, stored separately from the declaration', async () => {
    const task = makeTask({ status: 'IN_PROGRESS', startedAt: '2026-09-05T10:05:00Z' });
    planMock.mockResolvedValue(planWithTask(task));
    listMock.mockResolvedValue(makeList([task]));
    renderPlanner();

    fireEvent.click(await screen.findByRole('button', { name: /record measurement/i }));
    await screen.findByText('Measurement verification');

    fireEvent.change(screen.getByLabelText(/measured value \(mandatory\)/i), {
      target: { value: '492' },
    });
    fireEvent.change(screen.getByLabelText(/unit \(mandatory\)/i), { target: { value: 'g' } });
    fireEvent.change(screen.getByLabelText(/instrument id \(optional\)/i), {
      target: { value: 'SCALE-LM-0142' },
    });
    // Instrument verification status deliberately left blank — the backend
    // records "not recorded", never "verified".

    resultMock.mockResolvedValue(
      makeTask({
        status: 'COMPLETED',
        startedAt: '2026-09-05T10:05:00Z',
        completedAt: '2026-09-05T10:10:00Z',
        results: [makeResult()],
      }),
    );
    fireEvent.click(screen.getByRole('button', { name: /record result & complete task/i }));

    await waitFor(() =>
      expect(resultMock).toHaveBeenCalledWith('t1', {
        measuredValue: 492,
        unit: 'g',
        observation: undefined,
        instrumentId: 'SCALE-LM-0142',
        instrumentVerificationStatus: undefined,
        notes: undefined,
      }),
    );
  });

  it('shows the append-only history and refuses to reopen a completed task', async () => {
    const task = makeTask({
      status: 'COMPLETED',
      startedAt: '2026-09-05T10:05:00Z',
      completedAt: '2026-09-05T10:10:00Z',
      results: [makeResult()],
    });
    planMock.mockResolvedValue(planWithTask(task));
    listMock.mockResolvedValue(makeList([task]));
    renderPlanner();

    fireEvent.click(await screen.findByRole('button', { name: /view recorded verification/i }));
    expect(await screen.findByText('Measurement verification')).toBeTruthy();

    // The recorded result appears in the append-only history — with the
    // instrument status honestly "not recorded", never invented as "verified".
    expect(screen.getAllByText(/492 g/).length).toBeGreaterThan(0);
    expect(screen.getByText(/instrument verification status not recorded/i)).toBeTruthy();
    // The panel says the task cannot be reopened.
    expect(screen.getByText(/append-only and the task cannot be reopened/i)).toBeTruthy();
    expect(screen.queryByRole('button', { name: /record result/i })).toBeNull();
  });

  it('requires a cancellation reason before cancelling a task', async () => {
    planMock.mockResolvedValue(planWithTask(makeTask()));
    listMock.mockResolvedValue(makeList([makeTask()]));
    renderPlanner();

    fireEvent.click(await screen.findByRole('button', { name: /record measurement/i }));
    await screen.findByText('Measurement verification');

    fireEvent.click(screen.getByRole('button', { name: /cancel task/i }));
    const confirm = screen.getByRole('button', { name: /confirm cancellation/i });
    fireEvent.click(confirm);
    expect(await screen.findByText(/cancellation reason is mandatory/i)).toBeTruthy();
    expect(cancelMock).not.toHaveBeenCalled();
  });
});

describe('EvidenceTimelineCard (UI-06)', () => {
  it('renders the chronological audit trail with real timestamps only', async () => {
    auditMock.mockResolvedValue([
      {
        id: 'a2',
        inspectionId: 'i1',
        entityType: 'VERIFICATION_TASK',
        entityId: 't1',
        actorId: 'u1',
        eventType: 'VERIFICATION_RESULT_RECORDED',
        payload: { measuredValue: 492, unit: 'g' },
        createdAt: '2026-09-05T10:10:00Z',
      },
      {
        id: 'a1',
        inspectionId: 'i1',
        entityType: 'INSPECTION',
        entityId: 'i1',
        actorId: null,
        eventType: 'INSPECTION_CREATED',
        payload: null,
        createdAt: '2026-09-05T09:00:00Z',
      },
    ] satisfies AuditEvent[]);

    render(<EvidenceTimelineCard inspectionId="i1" />);

    expect(await screen.findByText('Inspection Created')).toBeTruthy();
    expect(screen.getByText('Verification Result Recorded')).toBeTruthy();
    // Oldest first — creation precedes the measurement in the DOM.
    const items = Array.from(document.querySelectorAll('.timeline__item'));
    expect(items[0].textContent).toContain('Inspection Created');
    expect(items[1].textContent).toContain('Verification Result Recorded');
    // System actions are labelled System (no fabricated actor).
    expect(screen.getByText(/by System/)).toBeTruthy();
  });

  it('surfaces load failures instead of failing silently', async () => {
    auditMock.mockRejectedValue(new Error('network down'));
    render(<EvidenceTimelineCard inspectionId="i1" />);

    expect(await screen.findByText(/could not load the audit trail/i)).toBeTruthy();
  });
});
