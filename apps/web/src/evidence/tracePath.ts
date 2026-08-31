/**
 * Trace-path algorithm for the Evidence Graph (Prompt 12).
 *
 * Given a selected node, walk the graph's REAL edges (source → target, both
 * directions) and collect every node and edge reachable from the selection —
 * the full evidence chain, not just immediate neighbours. Pure data over the
 * API graph: no hard-coded node ids, no fabricated relationships.
 *
 * Traversal is a deterministic BFS (queue order follows the API's edge order,
 * so the same graph + selection always produces the same trace).
 */

export interface TraceableGraph {
  nodes: ReadonlyArray<{ id: string; type?: string }>;
  edges: ReadonlyArray<{ id: string; source: string; target: string }>;
}

export interface TracePath {
  /** Every node id reachable from the selected node (selection included). */
  nodeIds: Set<string>;
  /** Every edge id whose both endpoints are reachable from the selection. */
  edgeIds: Set<string>;
  /** Node ids in BFS discovery order — the chain, selection first. */
  order: string[];
}

export const EMPTY_TRACE: TracePath = {
  nodeIds: new Set(),
  edgeIds: new Set(),
  order: [],
};

/**
 * Traverse the connected evidence chain from `startId`, following edges in
 * BOTH directions (upstream to the regulatory source and downstream to the
 * image pixels — the UX requires both halves of the chain).
 *
 * Returns EMPTY_TRACE when `startId` is not a node of the graph or when the
 * node has no connected edges at all (the caller renders the honest
 * "No trace path available" state).
 */
export function traceFrom(graph: TraceableGraph, startId: string | null): TracePath {
  if (!startId) return EMPTY_TRACE;
  if (!graph.nodes.some((n) => n.id === startId)) return EMPTY_TRACE;

  // Undirected adjacency: every edge is walkable both ways.
  const neighbors = new Map<string, Array<{ edgeId: string; other: string }>>();
  for (const edge of graph.edges) {
    push(neighbors, edge.source, edge.id, edge.target);
    push(neighbors, edge.target, edge.id, edge.source);
  }

  const connected = neighbors.get(startId);
  if (!connected || connected.length === 0) {
    // Isolated node: the selection itself, but no trace path.
    return { nodeIds: new Set([startId]), edgeIds: new Set(), order: [startId] };
  }

  const nodeIds = new Set<string>([startId]);
  const edgeIds = new Set<string>();
  const order: string[] = [startId];
  const queue: string[] = [startId];

  while (queue.length > 0) {
    const current = queue.shift()!;
    for (const { edgeId, other } of neighbors.get(current) ?? []) {
      edgeIds.add(edgeId);
      if (!nodeIds.has(other)) {
        nodeIds.add(other);
        order.push(other);
        queue.push(other);
      }
    }
  }

  return { nodeIds, edgeIds, order };
}

function push(
  map: Map<string, Array<{ edgeId: string; other: string }>>,
  key: string,
  edgeId: string,
  other: string,
): void {
  const list = map.get(key);
  if (list) list.push({ edgeId, other });
  else map.set(key, [{ edgeId, other }]);
}

/** Human-readable chain label, e.g. "Finding → Rule → Requirement → …". */
export function describeChain(
  graph: TraceableGraph,
  trace: TracePath,
): string {
  if (trace.order.length === 0) return '';
  const typeOf = new Map(graph.nodes.map((n) => [n.id, n.type ?? 'NODE'] as const));
  const seen = new Set<string>();
  const parts: string[] = [];
  for (const id of trace.order) {
    const type = typeOf.get(id) ?? 'NODE';
    if (seen.has(type)) continue;
    seen.add(type);
    parts.push(type);
  }
  return parts.join(' → ');
}
