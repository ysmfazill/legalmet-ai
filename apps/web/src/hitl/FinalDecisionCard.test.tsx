// @vitest-environment jsdom
//
// UI-06 — Final-decision card gate tests: the gate must distinguish FINDING
// blockers from REQUIRED-VERIFICATION blockers, show verification progress,
// and keep REQUIRES_FURTHER_REVIEW always available. The card is the real
// implementation; only its `hitl` prop is a fixture.

import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { ReviewStatus } from '@legalmet/types';

import { FinalDecisionCard } from './FinalDecisionCard';
import type { HitlState } from './useHitl';

function makeStatus(overrides: Partial<ReviewStatus> = {}): ReviewStatus {
  return {
    totalFindings: 2,
    pendingReview: 0,
    unreviewed: 0,
    confirmed: 2,
    corrected: 0,
    rejected: 0,
    overridden: 0,
    escalated: 0,
    criticalUnresolved: 0,
    decisionAllowed: true,
    decisionBlockers: [],
    verificationTotal: 0,
    verificationOpenRequired: 0,
    verificationInProgress: 0,
    verificationCompleted: 0,
    ...overrides,
  } as ReviewStatus;
}

function makeHitl(overrides: Partial<HitlState> = {}): HitlState {
  return {
    loading: false,
    error: null,
    status: makeStatus(),
    decisions: null,
    submitting: false,
    correctField: vi.fn(async () => true),
    reviewFinding: vi.fn(async () => null),
    submitDecision: vi.fn(async () => null),
    reload: vi.fn(async () => {}),
    ...overrides,
  };
}

function renderCard(hitl: HitlState, hasFindings = true) {
  return render(<FinalDecisionCard hitl={hitl} hasFindings={hasFindings} />);
}

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(cleanup);

describe('FinalDecisionCard decision gate (UI-06)', () => {
  it('blocks on open REQUIRED verification tasks and names them separately from findings', () => {
    renderCard(
      makeHitl({
        status: makeStatus({
          verificationTotal: 1,
          verificationOpenRequired: 1,
          decisionAllowed: false,
          decisionBlockers: [
            'Required verification task 3f2a (MEASUREMENT) is PENDING — record the measurement before deciding',
          ],
        }),
      }),
    );

    // The verification gate is labelled distinctly from the finding gate.
    expect(screen.getByText(/decision gate — evidence incomplete/i)).toBeTruthy();
    expect(screen.getAllByText(/REQUIRED verification task/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/RECOMMENDED verifications never block/i)).toBeTruthy();
    // The blocker itself is listed.
    expect(screen.getByText(/3f2a \(MEASUREMENT\) is PENDING/i)).toBeTruthy();
    // REQUIRES_FURTHER_REVIEW stays available; the deferral is honest.
    expect(screen.getByRole('button', { name: /requires further review/i })).toBeTruthy();
  });

  it('labels finding blockers as findings, not evidence gaps', () => {
    renderCard(
      makeHitl({
        status: makeStatus({
          decisionAllowed: false,
          decisionBlockers: ['CRITICAL finding f9 is PENDING_REVIEW'],
        }),
      }),
    );

    expect(screen.getByText(/decision gate — findings/i)).toBeTruthy();
    expect(screen.queryByText(/decision gate — evidence incomplete/i)).toBeNull();
  });

  it('shows verification progress counts while tasks exist', () => {
    renderCard(
      makeHitl({
        status: makeStatus({
          verificationTotal: 3,
          verificationOpenRequired: 1,
          verificationInProgress: 1,
          verificationCompleted: 1,
        }),
      }),
    );

    expect(screen.getByText('Verification tasks')).toBeTruthy();
    expect(screen.getByText('Required, still open')).toBeTruthy();
    expect(screen.getByText('In progress')).toBeTruthy();
    expect(screen.getByText('Completed')).toBeTruthy();
  });

  it('confirms the gate opens when every required task is complete', () => {
    renderCard(
      makeHitl({
        status: makeStatus({
          verificationTotal: 2,
          verificationOpenRequired: 0,
          verificationInProgress: 0,
          verificationCompleted: 2,
          decisionAllowed: true,
        }),
      }),
    );

    expect(screen.getByText(/all required verification tasks are complete/i)).toBeTruthy();
    // Both decisive choices are reachable.
    expect(screen.getByRole('button', { name: /record compliant/i})).toBeTruthy();
    expect(screen.getByRole('button', { name: /record non-compliant/i})).toBeTruthy();
  });

  it('a RECOMMENDED-only task never blocks the decisive choices', () => {
    renderCard(
      makeHitl({
        status: makeStatus({
          verificationTotal: 1,
          verificationOpenRequired: 0,
          decisionAllowed: true,
        }),
      }),
    );

    expect(screen.getByRole('button', { name: /record compliant/i})).toBeTruthy();
    expect(screen.getByRole('button', { name: /record non-compliant/i})).toBeTruthy();
  });

  it('hides the verification progress block when no tasks exist', () => {
    renderCard(makeHitl());
    expect(screen.queryByText('Verification tasks')).toBeNull();
  });

  it('submitting a gated COMPLIANT choice stays disabled and explains both blocker kinds', () => {
    renderCard(
      makeHitl({
        status: makeStatus({
          decisionAllowed: false,
          decisionBlockers: [
            'CRITICAL finding f9 is PENDING_REVIEW',
            'Required verification task 3f2a (MEASUREMENT) is PENDING',
          ],
        }),
      }),
    );

    // The gate DISABLES the decisive choices (they render greyed out, not
    // hidden) — only the honest deferral is clickable.
    const compliant = screen.getByRole('button', { name: /record compliant/i });
    expect(compliant.hasAttribute('disabled')).toBe(true);
    expect(screen.getByRole('button', { name: /requires further review/i }).hasAttribute('disabled')).toBe(false);
  });

  it('requires a reason for NON_COMPLIANT and REQUIRES_FURTHER_REVIEW', () => {
    renderCard(makeHitl());

    fireEvent.click(screen.getByRole('button', { name: /record non-compliant/i }));
    const continueBtn = screen.getByRole('button', { name: /continue/i });
    // No reason yet → cannot continue to the confirm step.
    expect(continueBtn.hasAttribute('disabled')).toBe(true);
    fireEvent.change(screen.getByLabelText(/reason \(mandatory\)/i), {
      target: { value: 'MRP mismatch confirmed on site' },
    });
    expect(continueBtn.hasAttribute('disabled')).toBe(false);
  });
});
