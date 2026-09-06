/**
 * Report lifecycle hook (UI-08).
 *
 * Owns the read/write model for ONE report:
 *
 * - the full detail (snapshot, versions, evidence completeness)
 * - the gated actions: generate → review → finalize → export → amend
 *
 * CONTRACT: the finalization gate, versioning rules and honesty contracts all
 * live in the backend. This hook surfaces results and rejections honestly —
 * including the mandated error strings ("PDF generation failed. Your
 * inspection data has not been changed.", etc.) — and reloads the read model
 * after every write. It never fabricates success.
 */
import { useCallback, useEffect, useRef, useState } from 'react';

import { api, ApiClientError } from '../api/client';
import type { ReportDetail } from '@legalmet/types';

export interface UseReportState {
  loading: boolean;
  error: string | null;
  report: ReportDetail | null;
  /** One lifecycle action is running (buttons disable, spinner shows). */
  acting: boolean;
  /** The most recent action failure — shown inline, never swallowed. */
  actionError: string | null;
  /** The most recent action success message. */
  actionNotice: string | null;
  generate: () => Promise<ReportDetail | null>;
  review: () => Promise<ReportDetail | null>;
  finalize: () => Promise<ReportDetail | null>;
  amend: (reason: string) => Promise<ReportDetail | null>;
  /** Downloads the real file (blob URL) and triggers it. */
  export: (format: 'pdf' | 'docx') => Promise<boolean>;
  reload: () => Promise<void>;
}

function messageOf(err: unknown, fallback: string): string {
  return err instanceof ApiClientError ? err.message : err instanceof Error ? err.message : fallback;
}

export function useReport(reportId: string, enabled: boolean): UseReportState {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [report, setReport] = useState<ReportDetail | null>(null);
  const [acting, setActing] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionNotice, setActionNotice] = useState<string | null>(null);

  const alive = useRef(true);
  const loadToken = useRef(0);

  const load = useCallback(async () => {
    if (!enabled) {
      setLoading(false);
      return;
    }
    const token = ++loadToken.current;
    try {
      const next = await api.getReport(reportId);
      if (!alive.current || token !== loadToken.current) return;
      setReport(next);
      setError(null);
    } catch (err) {
      if (!alive.current || token !== loadToken.current) return;
      setError(messageOf(err, 'Failed to load report'));
    } finally {
      if (alive.current && token === loadToken.current) setLoading(false);
    }
  }, [reportId, enabled]);

  useEffect(() => {
    alive.current = true;
    void load();
    return () => {
      alive.current = false;
    };
  }, [load]);

  const runAction = useCallback(
    async (label: string, fn: () => Promise<ReportDetail>): Promise<ReportDetail | null> => {
      setActing(true);
      setActionError(null);
      setActionNotice(null);
      try {
        const next = await fn();
        if (alive.current) setReport(next);
        setActionNotice(label);
        return next;
      } catch (err) {
        // The backend's gate/conflict messages are user-facing by design.
        setActionError(messageOf(err, `${label} failed.`));
        return null;
      } finally {
        setActing(false);
      }
    },
    [],
  );

  const generate = useCallback(
    () =>
      runAction('Report generated successfully.', () => api.generateReport(reportId)),
    [reportId, runAction],
  );

  const review = useCallback(
    () =>
      runAction('Review recorded.', () => api.reviewReport(reportId)),
    [reportId, runAction],
  );

  const finalize = useCallback(
    () =>
      runAction('Report finalized.', () => api.finalizeReport(reportId)),
    [reportId, runAction],
  );

  const amend = useCallback(
    (reason: string) =>
      runAction('Amendment issued — a new report version was generated.', () =>
        api.amendReport(reportId, { reason }),
      ),
    [reportId, runAction],
  );

  const doExport = useCallback(
    async (format: 'pdf' | 'docx') => {
      setActing(true);
      setActionError(null);
      setActionNotice(null);
      try {
        const { url, filename } = await api.exportReport(reportId, format);
        const anchor = document.createElement('a');
        anchor.href = url;
        anchor.download = filename;
        document.body.appendChild(anchor);
        anchor.click();
        anchor.remove();
        // Revoke after the click has had time to consume the blob URL.
        window.setTimeout(() => URL.revokeObjectURL(url), 10_000);
        setActionNotice(
          format === 'pdf'
            ? 'Report exported as PDF.'
            : 'Report exported as DOCX (editable document).',
        );
        // The backend moved the status to EXPORTED — refresh the read model.
        await load();
        return true;
      } catch (err) {
        // Exact spec strings come from the backend envelope.
        setActionError(messageOf(err, 'Export failed.'));
        return false;
      } finally {
        setActing(false);
      }
    },
    [reportId, load],
  );

  return {
    loading,
    error,
    report,
    acting,
    actionError,
    actionNotice,
    generate,
    review,
    finalize,
    amend,
    export: doExport,
    reload: load,
  };
}
