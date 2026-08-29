/**
 * Evidence-graph data hook (Prompt 7).
 *
 * Loads a read-only traceability graph from the backend and exposes selection
 * state for the node detail panel. The hook never mutates anything — the graph
 * is a view over what the system already recorded.
 *
 * The loader is injectable so callers can trace any of the three roots
 * (inspection / finding / field) with the same hook.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { api } from '../api/client';
import type { EvidenceTraceGraph, TraceEdge, TraceNode } from '@legalmet/types';

export type EvidenceGraphLoader = (signal?: AbortSignal) => Promise<EvidenceTraceGraph>;

export interface EvidenceGraphState {
  loading: boolean;
  error: string | null;
  graph: EvidenceTraceGraph | null;
  /** Node → incoming + outgoing edges (for the detail panel + highlighting). */
  adjacency: Map<string, TraceEdge[]>;
  selectedId: string | null;
  select: (id: string | null) => void;
  /** The selected node object (null when nothing is selected). */
  selectedNode: TraceNode | null;
  reload: () => void;
}

export function useEvidenceGraph(loader: EvidenceGraphLoader): EvidenceGraphState {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [graph, setGraph] = useState<EvidenceTraceGraph | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  const alive = useRef(true);
  const loaderRef = useRef(loader);
  loaderRef.current = loader;

  useEffect(() => {
    alive.current = true;
    const controller = new AbortController();
    setLoading(true);
    loaderRef
      .current(controller.signal)
      .then((result) => {
        if (!alive.current) return;
        setGraph(result);
        setError(null);
      })
      .catch((err: unknown) => {
        if (!alive.current || controller.signal.aborted) return;
        setError(err instanceof Error ? err.message : 'Failed to load evidence graph');
      })
      .finally(() => {
        if (alive.current) setLoading(false);
      });
    return () => {
      alive.current = false;
      controller.abort();
    };
  }, [reloadToken]);

  const adjacency = useMemo(() => {
    const map = new Map<string, TraceEdge[]>();
    if (!graph) return map;
    for (const edge of graph.edges) {
      for (const endpoint of [edge.source, edge.target]) {
        const list = map.get(endpoint);
        if (list) list.push(edge);
        else map.set(endpoint, [edge]);
      }
    }
    return map;
  }, [graph]);

  const selectedNode = useMemo(
    () => graph?.nodes.find((n) => n.id === selectedId) ?? null,
    [graph, selectedId],
  );

  const select = useCallback((id: string | null) => setSelectedId(id), []);
  const reload = useCallback(() => setReloadToken((t) => t + 1), []);

  return {
    loading,
    error,
    graph,
    adjacency,
    selectedId,
    selectedNode,
    select,
    reload,
  };
}

/** Loader factories for the three trace roots. */
export const evidenceLoaders = {
  inspection: (inspectionId: string, evaluationId?: string): EvidenceGraphLoader =>
    (signal) =>
      api.getInspectionEvidenceGraph(inspectionId, evaluationId).then((g) => {
        signal?.throwIfAborted();
        return g;
      }),
  finding: (findingId: string): EvidenceGraphLoader =>
    (signal) =>
      api.getFindingEvidenceGraph(findingId).then((g) => {
        signal?.throwIfAborted();
        return g;
      }),
  field: (fieldId: string): EvidenceGraphLoader =>
    (signal) =>
      api.getFieldEvidenceGraph(fieldId).then((g) => {
        signal?.throwIfAborted();
        return g;
      }),
};
