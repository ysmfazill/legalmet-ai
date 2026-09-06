/**
 * Evidence Planner data hook (UI-06).
 *
 * Owns the evidence-plan + verification-task read/write model for one
 * inspection:
 *
 * - the evidence plan (per finding/declaration: existing evidence, open
 *   gaps, the verification task that closes them)
 * - the verification tasks + their append-only results
 * - the actions: create a task, start it, record a result, cancel it
 *
 * CONTRACT: every write here is an AUTHORISED HUMAN action. The engine has
 * no counterpart to any of these calls. The backend enforces roles, the
 * task state machine, the anchor/duplicate rules and the decision gate —
 * this hook only surfaces the results (and the rejections) honestly, then
 * reloads the read model.
 *
 * BOUNDARY: a recorded measurement is EVIDENCE. Nothing in this hook (or
 * anywhere in the frontend) compares it to the declared value or derives a
 * compliance verdict from the difference — the inspector does that.
 */
import { useCallback, useEffect, useRef, useState } from 'react';

import { api } from '../api/client';
import type {
  EvidencePlan,
  VerificationCreateRequest,
  VerificationList,
  VerificationResultRequest,
  VerificationTask,
} from '@legalmet/types';

export interface EvidencePlanState {
  loading: boolean;
  error: string | null;
  plan: EvidencePlan | null;
  tasks: VerificationTask[];
  /** True while a write is in flight (disables the action buttons). */
  busy: boolean;
  /** Create ONE verification task (explicit human action, reason mandatory). */
  createTask: (body: VerificationCreateRequest) => Promise<VerificationTask | null>;
  /** PENDING → IN_PROGRESS. */
  startTask: (taskId: string) => Promise<VerificationTask | null>;
  /** Record ONE outcome (append-only) and complete the task. */
  recordResult: (
    taskId: string,
    body: VerificationResultRequest,
  ) => Promise<VerificationTask | null>;
  /** Cancel a task (reason mandatory — audited). */
  cancelTask: (taskId: string, reason: string) => Promise<VerificationTask | null>;
  /** Reload the read model (called automatically after every write). */
  reload: () => Promise<void>;
}

export function useEvidencePlan(inspectionId: string, enabled: boolean): EvidencePlanState {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [plan, setPlan] = useState<EvidencePlan | null>(null);
  const [tasks, setTasks] = useState<VerificationTask[]>([]);
  const [busy, setBusy] = useState(false);

  const alive = useRef(true);
  const loadToken = useRef(0);

  const load = useCallback(async () => {
    if (!enabled) {
      setLoading(false);
      return;
    }
    const token = ++loadToken.current;
    try {
      const [nextPlan, nextTasks] = await Promise.all([
        api.getEvidencePlan(inspectionId),
        // The plan alone is enough to render; a failed task listing must not
        // take the whole planner down (tasks degrade to an empty list).
        api
          .listVerifications(inspectionId)
          .catch(
            () =>
              ({ inspectionId, tasks: [], boundaryNote: '' }) as VerificationList,
          ),
      ]);
      if (!alive.current || token !== loadToken.current) return;
      setPlan(nextPlan);
      setTasks(nextTasks.tasks);
      setError(null);
    } catch (err) {
      if (!alive.current || token !== loadToken.current) return;
      setError(err instanceof Error ? err.message : 'Failed to load the evidence plan');
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

  const write = useCallback(
    async (action: () => Promise<VerificationTask>): Promise<VerificationTask | null> => {
      setBusy(true);
      try {
        const task = await action();
        await load();
        return task;
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Verification action failed');
        return null;
      } finally {
        if (alive.current) setBusy(false);
      }
    },
    [load],
  );

  const createTask = useCallback(
    (body: VerificationCreateRequest) =>
      write(() => api.createVerification(inspectionId, body)),
    [inspectionId, write],
  );

  const startTask = useCallback(
    (taskId: string) => write(() => api.startVerification(taskId)),
    [write],
  );

  const recordResult = useCallback(
    (taskId: string, body: VerificationResultRequest) =>
      write(() => api.recordVerificationResult(taskId, body)),
    [write],
  );

  const cancelTask = useCallback(
    (taskId: string, reason: string) =>
      write(() => api.cancelVerification(taskId, { reason })),
    [write],
  );

  return {
    loading,
    error,
    plan,
    tasks,
    busy,
    createTask,
    startTask,
    recordResult,
    cancelTask,
    reload: load,
  };
}
