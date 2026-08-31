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
import { EMPTY_TRACE, traceFrom, type TracePath } from './tracePath';

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
  /** --- Trace mode (Prompt 12) ------------------------------------------- */
  /** True while trace mode is armed — the selected node's chain is highlighted. */
  tracing: boolean;
  /** The node the active trace started from (null when not tracing). */
  traceRootId: string | null;
  /** The traced node/edge id sets + discovery order. */
  trace: TracePath;
  /** Arm trace mode. With no argument, traces the current selection. */
  startTrace: (nodeId?: string | null) => void;
  /** Disarm trace mode and restore the normal graph. */
  clearTrace: () => void;
  /** True when trace mode is armed but the traced node has no connected path. */
  traceEmpty: boolean;
}

export function useEvidenceGraph(loader: EvidenceGraphLoader): EvidenceGraphState {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [graph, setGraph] = useState<EvidenceTraceGraph | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);
  const [tracing, setTracing] = useState(false);
  const [traceRootId, setTraceRootId] = useState<string | null>(null);

  const alive = useRef(true);
  const loaderRef = useRef(loader);
  loaderRef.current = loader;
  // Latest selection without re-creating startTrace (avoids stale-closure bugs
  // when the Trace button is armed before any node is selected).
  const selectedIdRef = useRef<string | null>(null);
  selectedIdRef.current = selectedId;

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

  // A reloaded graph invalidates the old trace root: the node ids may no
  // longer exist, so trace mode resets rather than highlighting a stale id.
  useEffect(() => {
    if (tracing && traceRootId && graph && !graph.nodes.some((n) => n.id === traceRootId)) {
      setTracing(false);
      setTraceRootId(null);
    }
  }, [graph, tracing, traceRootId]);

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

  const trace = useMemo(
    () => (tracing && graph ? traceFrom(graph, traceRootId) : EMPTY_TRACE),
    [tracing, traceRootId, graph],
  );

  const traceEmpty = tracing && trace.order.length <= 1;

  const select = useCallback((id: string | null) => setSelectedId(id), []);

  const startTrace = useCallback((nodeId?: string | null) => {
    const target = nodeId !== undefined ? nodeId : selectedIdRef.current;
    if (!target) return;
    setSelectedId(target);
    setTraceRootId(target);
    setTracing(true);
  }, []);

  const clearTrace = useCallback(() => {
    setTracing(false);
    setTraceRootId(null);
  }, []);

  const reload = useCallback(() => setReloadToken((t) => t + 1), []);

  return {
    loading,
    error,
    graph,
    adjacency,
    selectedId,
    select,
    selectedNode,
    reload,
    tracing,
    traceRootId,
    trace,
    startTrace,
    clearTrace,
    traceEmpty,
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
