/**
 * Perception data hook (Prompt 4).
 *
 * Owns the real-perception read model for one inspection: analysis summary,
 * OCR lines, visual regions, extracted declaration fields and the processing
 * run history — plus the actions that start / re-run perception.
 *
 * Contract notes:
 * - The backend's perception endpoints answer "what did the system SEE". None
 *   of this data carries a compliance verdict; the UI must never present it
 *   as one.
 * - While `analysis.active` is true (a run is in a non-terminal stage) the
 *   hook polls until every latest run settles.
 * - Reads always target the LATEST run per image; run history is available
 *   separately so reanalysis never hides prior evidence.
 */
import { useCallback, useEffect, useRef, useState } from 'react';

import { api } from '../api/client';
import type {
  ExtractedField,
  ImageRegion,
  OcrTextResult,
  PerceptionAnalysis,
  ProcessingRun,
} from '@legalmet/types';

const POLL_INTERVAL_MS = 2500;

export interface PerceptionState {
  loading: boolean;
  error: string | null;
  analysis: PerceptionAnalysis | null;
  ocr: OcrTextResult[];
  regions: ImageRegion[];
  fields: ExtractedField[];
  runs: ProcessingRun[];
  starting: boolean;
  /** Kick off perception for every usable image on the inspection. */
  start: () => Promise<void>;
  /** Queue a NEW run for one image (prior runs stay in history). */
  reanalyze: (imageId: string) => Promise<void>;
}

export function usePerception(inspectionId: string): PerceptionState {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [analysis, setAnalysis] = useState<PerceptionAnalysis | null>(null);
  const [ocr, setOcr] = useState<OcrTextResult[]>([]);
  const [regions, setRegions] = useState<ImageRegion[]>([]);
  const [fields, setFields] = useState<ExtractedField[]>([]);
  const [runs, setRuns] = useState<ProcessingRun[]>([]);
  const [starting, setStarting] = useState(false);

  const alive = useRef(true);
  const reloadToken = useRef(0);

  const load = useCallback(async () => {
    const token = ++reloadToken.current;
    try {
      const [nextAnalysis, nextOcr, nextRegions, nextFields, nextRuns] = await Promise.all([
        api.getPerceptionAnalysis(inspectionId),
        api.listOcrResults(inspectionId),
        api.listRegions(inspectionId),
        api.listFields(inspectionId),
        api.listProcessingRuns(inspectionId),
      ]);
      if (!alive.current || token !== reloadToken.current) return;
      setAnalysis(nextAnalysis);
      setOcr(nextOcr);
      setRegions(nextRegions);
      setFields(nextFields);
      setRuns(nextRuns);
      setError(null);
    } catch (err) {
      if (!alive.current || token !== reloadToken.current) return;
      setError(err instanceof Error ? err.message : 'Failed to load perception data');
    } finally {
      if (alive.current && token === reloadToken.current) setLoading(false);
    }
  }, [inspectionId]);

  // Initial load + poll while any latest run is still in flight.
  useEffect(() => {
    alive.current = true;
    setLoading(true);
    load();
    return () => {
      alive.current = false;
    };
  }, [load]);

  useEffect(() => {
    if (!analysis?.active) return;
    const timer = window.setInterval(load, POLL_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [analysis?.active, load]);

  const start = useCallback(async () => {
    setStarting(true);
    try {
      await api.startPerception(inspectionId);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start perception');
    } finally {
      setStarting(false);
    }
  }, [inspectionId, load]);

  const reanalyze = useCallback(
    async (imageId: string) => {
      setStarting(true);
      try {
        await api.reanalyzeImage(imageId);
        await load();
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to queue re-analysis');
      } finally {
        setStarting(false);
      }
    },
    [load],
  );

  return { loading, error, analysis, ocr, regions, fields, runs, starting, start, reanalyze };
}
