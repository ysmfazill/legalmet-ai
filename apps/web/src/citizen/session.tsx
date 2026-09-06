import { createContext, useCallback, useContext, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';

import type { CitizenReportDetail, CitizenReportResult, CitizenScanResult } from '@legalmet/types';

import { api } from '../api/client';
import { ApiClientError } from '../api/client';

/**
 * Citizen scan-session state, threaded across the sub-routes:
 *
 *   /citizen/scan  → upload/capture → POST /citizen/scans (REAL pipeline)
 *   /citizen/result ← the screening outcome + detected declarations
 *   /citizen/report ← form (auto-attached scan evidence) → review → submit
 *
 * The session holds only what the real backend returned. Nothing here is
 * fabricated: if the backend is unreachable the flow surfaces an honest error
 * with a retry, never a fake result.
 *
 * "My reports" persistence is honest: the backend offers no citizen-side
 * listing (reports are reachable only by UUID — no anonymous enumeration),
 * so submitted report references from THIS browser session are kept locally
 * and clearly labelled. Clearing browser storage clears the list — stated
 * in the UI, never hidden.
 */
export interface CitizenSessionReport extends CitizenReportResult {
  /** Where this entry came from — always stated in the UI. */
  source: 'submitted-this-device';
}

interface CitizenSessionValue {
  /** The live scan result from the real backend (null before first scan). */
  scan: CitizenScanResult | null;
  /** The submitted report (null until submission succeeds). */
  report: CitizenReportResult | null;
  /** Report records submitted from this browser, newest first. */
  myReports: CitizenSessionReport[];
  /** True while the real scan request is in flight. */
  scanning: boolean;
  /** Honest error string when the real pipeline failed. */
  error: string | null;

  startScan: (file: File | Blob) => Promise<void>;
  clearScan: () => void;
  clearError: () => void;
  submitReport: (input: CitizenReportInput) => Promise<CitizenReportResult>;
  /** Re-read one report from the backend; the stored entry is updated. */
  refreshReport: (reportId: string) => Promise<CitizenReportDetail>;
  reset: () => void;
}

export interface CitizenReportInput {
  product: string;
  shop?: string;
  location?: string;
  issue: string;
  description?: string;
  reporterName?: string;
  reporterContact?: string;
}

const CitizenSessionContext = createContext<CitizenSessionValue | null>(null);

const STORAGE_KEY = 'metrasight.citizen.myReports.v1';

/** Session + localStorage persistence for this device's submitted reports. */
function loadMyReports(): CitizenSessionReport[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (r): r is CitizenSessionReport =>
        r && typeof r.id === 'string' && typeof r.reference === 'string',
    );
  } catch {
    return [];
  }
}

function saveMyReports(reports: CitizenSessionReport[]): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(reports));
  } catch {
    // Private-browsing/quota — the in-memory list still works this session.
  }
}

export function CitizenSessionProvider({ children }: { children: ReactNode }) {
  const navigate = useNavigate();
  const [scan, setScan] = useState<CitizenScanResult | null>(null);
  const [report, setReport] = useState<CitizenReportResult | null>(null);
  const [myReports, setMyReports] = useState<CitizenSessionReport[]>(loadMyReports);
  const [scanning, setScanning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const startScan = useCallback(
    async (file: File | Blob) => {
      setScanning(true);
      setError(null);
      setReport(null);
      try {
        const result = await api.citizenScan(file);
        setScan(result);
        navigate('/citizen/result');
      } catch (err) {
        const message =
          err instanceof ApiClientError
            ? err.message
            : 'We could not reach the screening service. Check your connection and try again.';
        setError(message);
        // Stay on /citizen/scan — never show a blank or fake result screen.
      } finally {
        setScanning(false);
      }
    },
    [navigate],
  );

  const clearScan = useCallback(() => {
    setScan(null);
    setError(null);
  }, []);

  const clearError = useCallback(() => setError(null), []);

  const submitReport = useCallback(
    async (input: CitizenReportInput) => {
      if (!scan) throw new Error('No scan to attach.');
      const result = await api.citizenSubmitReport({ scanId: scan.id, ...input });
      setReport(result);
      const entry: CitizenSessionReport = {
        ...result,
        source: 'submitted-this-device',
      };
      setMyReports((prev) => {
        const next = [entry, ...prev];
        saveMyReports(next);
        return next;
      });
      return result;
    },
    [scan],
  );

  const refreshReport = useCallback(async (reportId: string) => {
    const detail = await api.citizenGetReport(reportId);
    setMyReports((prev) => {
      if (!prev.some((r) => r.id === reportId)) return prev;
      const next = prev.map((r) => (r.id === reportId ? { ...r, ...detail } : r));
      saveMyReports(next);
      return next;
    });
    return detail;
  }, []);

  const reset = useCallback(() => {
    setScan(null);
    setReport(null);
    setError(null);
  }, []);

  const value = useMemo(
    () => ({
      scan,
      report,
      myReports,
      scanning,
      error,
      startScan,
      clearScan,
      clearError,
      submitReport,
      refreshReport,
      reset,
    }),
    [scan, report, myReports, scanning, error, startScan, clearScan, clearError, submitReport, refreshReport, reset],
  );

  return <CitizenSessionContext.Provider value={value}>{children}</CitizenSessionContext.Provider>;
}

export function useCitizenSession(): CitizenSessionValue {
  const ctx = useContext(CitizenSessionContext);
  if (!ctx) throw new Error('useCitizenSession must be used inside CitizenSessionProvider');
  return ctx;
}
