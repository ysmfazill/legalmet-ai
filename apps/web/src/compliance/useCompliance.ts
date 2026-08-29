/**
 * Compliance-engine data hook (Prompt 6).
 *
 * Owns the real compliance read model for one inspection: the latest
 * evaluation (or an explicit NOT_EVALUATED), its findings, and the action
 * that runs a NEW evaluation (history is never overwritten — each run creates
 * a fresh evaluation row).
 *
 * Contract notes:
 * - Findings are SYSTEM decision-support outputs. The hook exposes them
 *   verbatim — no re-scoring, no aggregation into a percentage, no
 *   "legal confidence" number.
 * - `evaluate()` is a write: only INSPECTOR/SUPERVISOR/ADMIN roles may call
 *   it (the backend enforces this; the UI surfaces the error honestly).
 */
import { useCallback, useEffect, useRef, useState } from 'react';

import { api } from '../api/client';
import {
  FINDING_BOUNDARY_NOTE,
  type ComplianceEvaluation,
  type EngineFinding,
  type InspectionComplianceStatus,
} from '@legalmet/types';

export interface ComplianceState {
  loading: boolean;
  error: string | null;
  /** Latest evaluation status — NOT_EVALUATED when none has ever run. */
  status: InspectionComplianceStatus | null;
  /** The latest evaluation, findings included (null before the first run). */
  evaluation: ComplianceEvaluation | null;
  /** Findings of the latest evaluation (empty before the first run). */
  findings: EngineFinding[];
  evaluating: boolean;
  /** Run one evaluation. Creates a NEW run — history is preserved. */
  evaluate: () => Promise<void>;
  /** Fetch the latest state again (used after an evaluation completes). */
  reload: () => Promise<void>;
}

export function useCompliance(inspectionId: string, enabled: boolean): ComplianceState {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<InspectionComplianceStatus | null>(null);
  const [evaluation, setEvaluation] = useState<ComplianceEvaluation | null>(null);
  const [findings, setFindings] = useState<EngineFinding[]>([]);
  const [evaluating, setEvaluating] = useState(false);

  const alive = useRef(true);
  const loadToken = useRef(0);

  const load = useCallback(async () => {
    if (!enabled) {
      setLoading(false);
      return;
    }
    const token = ++loadToken.current;
    try {
      const [nextStatus, nextFindings] = await Promise.all([
        api.getComplianceStatus(inspectionId),
        api.listEngineFindings(inspectionId),
      ]);
      if (!alive.current || token !== loadToken.current) return;
      setStatus(nextStatus);
      setEvaluation(nextStatus.evaluation ?? null);
      setFindings(nextFindings);
      setError(null);
    } catch (err) {
      if (!alive.current || token !== loadToken.current) return;
      setError(err instanceof Error ? err.message : 'Failed to load compliance data');
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

  const evaluate = useCallback(async () => {
    setEvaluating(true);
    try {
      const next = await api.evaluateCompliance(inspectionId);
      if (!alive.current) return;
      setEvaluation(next);
      setFindings(next.findings ?? []);
      setStatus({ inspectionId, status: next.status, evaluation: next, boundaryNote: FINDING_BOUNDARY_NOTE });
      setError(null);
    } catch (err) {
      if (!alive.current) return;
      setError(err instanceof Error ? err.message : 'Evaluation failed');
    } finally {
      if (alive.current) setEvaluating(false);
    }
  }, [inspectionId]);

  return { loading, error, status, evaluation, findings, evaluating, evaluate, reload: load };
}
