/**
 * Human-in-the-loop review data hook (Prompt 8).
 *
 * Owns the HITL read/write model for one inspection:
 *
 * - review-status (per-state counts, critical unresolved, decision gate)
 * - the current + historical final decisions
 * - the actions: correct a field, review a finding, submit a decision
 *
 * CONTRACT: every write here is an AUTHORISED HUMAN action. The engine has no
 * counterpart to any of these calls. The backend enforces roles, the review
 * state machine, the decision gate and immutability — this hook only surfaces
 * the results (and the rejections) honestly, then reloads the read model.
 */
import { useCallback, useEffect, useRef, useState } from 'react';

import { api } from '../api/client';
import type {
  DecisionRequest,
  DecisionHistory,
  FieldCorrectRequest,
  FindingReview,
  FindingReviewActionRequest,
  InspectionDecision,
  ReviewStatus,
} from '@legalmet/types';

export interface HitlState {
  loading: boolean;
  error: string | null;
  status: ReviewStatus | null;
  decisions: DecisionHistory | null;
  submitting: boolean;
  /** Correct one extracted field (append-only — the AI original survives). */
  correctField: (fieldId: string, body: FieldCorrectRequest) => Promise<boolean>;
  /** Apply one review action to a finding. Returns the review on success. */
  reviewFinding: (
    findingId: string,
    body: FindingReviewActionRequest,
  ) => Promise<FindingReview | null>;
  /** Record the final human decision (the only legal conclusion). */
  submitDecision: (body: DecisionRequest) => Promise<InspectionDecision | null>;
  /** Reload the read model (called automatically after every write). */
  reload: () => Promise<void>;
}

export function useHitl(inspectionId: string, enabled: boolean): HitlState {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<ReviewStatus | null>(null);
  const [decisions, setDecisions] = useState<DecisionHistory | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const alive = useRef(true);
  const loadToken = useRef(0);

  const load = useCallback(async () => {
    if (!enabled) {
      setLoading(false);
      return;
    }
    const token = ++loadToken.current;
    try {
      const [nextStatus, nextDecisions] = await Promise.all([
        api.getReviewStatus(inspectionId),
        api.getDecisionHistory(inspectionId).catch(() => null),
      ]);
      if (!alive.current || token !== loadToken.current) return;
      setStatus(nextStatus);
      setDecisions(nextDecisions);
      setError(null);
    } catch (err) {
      if (!alive.current || token !== loadToken.current) return;
      setError(err instanceof Error ? err.message : 'Failed to load review status');
    } finally {
      if (alive.current && token === loadToken.current) setLoading(false);
    }
  }, [inspectionId, enabled]);

  useEffect(() => {
    alive.current = true;
    setLoading(enabled);
    void load();
    return () => {
      alive.current = false;
    };
  }, [load, enabled]);

  const correctField = useCallback(
    async (fieldId: string, body: FieldCorrectRequest): Promise<boolean> => {
      setSubmitting(true);
      try {
        await api.correctField(fieldId, body);
        await load();
        return true;
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Correction failed');
        return false;
      } finally {
        if (alive.current) setSubmitting(false);
      }
    },
    [load],
  );

  const reviewFinding = useCallback(
    async (
      findingId: string,
      body: FindingReviewActionRequest,
    ): Promise<FindingReview | null> => {
      setSubmitting(true);
      try {
        const review = await api.reviewFinding(findingId, body);
        await load();
        return review;
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Review action failed');
        return null;
      } finally {
        if (alive.current) setSubmitting(false);
      }
    },
    [load],
  );

  const submitDecision = useCallback(
    async (body: DecisionRequest): Promise<InspectionDecision | null> => {
      setSubmitting(true);
      try {
        const decision = await api.submitDecision(inspectionId, body);
        await load();
        return decision;
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Decision failed');
        return null;
      } finally {
        if (alive.current) setSubmitting(false);
      }
    },
    [inspectionId, load],
  );

  return {
    loading,
    error,
    status,
    decisions,
    submitting,
    correctField,
    reviewFinding,
    submitDecision,
    reload: load,
  };
}
