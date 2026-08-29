/**
 * Deterministic layered layout for the traceability graph (Prompt 7).
 *
 * No force-directed simulation, no randomness: every node lands in a fixed
 * column derived from its semantic category (input → transformation →
 * regulatory reference → conclusion → audit), and rows are assigned in the
 * order the server returned them. The same graph payload ALWAYS renders
 * identically — that determinism is what makes the view auditable.
 *
 * The layout is pure data: nodes get {x, y} positions, edges get polyline
 * anchor points. Rendering lives in EvidenceGraphView.
 */
import type { EvidenceGraphNodeKind, TraceEdge, TraceNode } from '@legalmet/types';

/** Semantic columns, left → right: evidence flows toward the finding. */
const COLUMN_ORDER: EvidenceGraphNodeKind[][] = [
  ['REGULATORY_SOURCE'],
  ['REGULATORY_DOCUMENT'],
  ['REGULATORY_VERSION'],
  ['REQUIREMENT'],
  ['RULE'],
  ['EVALUATION', 'INSPECTION'],
  ['FINDING'],
  ['EXTRACTED_FIELD'],
  ['OCR_RESULT', 'IMAGE_REGION'],
  ['IMAGE', 'PROCESSING_RUN'],
  ['AUDIT_EVENT'],
];

export interface PositionedNode {
  node: TraceNode;
  x: number;
  y: number;
  column: number;
}

export interface LayoutGraph {
  nodes: PositionedNode[];
  edges: TraceEdge[];
  width: number;
  height: number;
}

const NODE_W = 168;
const NODE_H = 44;
const GAP_X = 64;
const GAP_Y = 18;

function columnFor(type: EvidenceGraphNodeKind): number {
  const index = COLUMN_ORDER.findIndex((group) => group.includes(type));
  return index === -1 ? COLUMN_ORDER.length - 1 : index;
}

/**
 * Assign every node a deterministic position. Columns follow COLUMN_ORDER;
 * within a column nodes stack top-to-bottom in server order (which the backend
 * already emits in a stable, id-ordered sequence).
 */
export function layoutGraph(graph: { nodes: TraceNode[]; edges: TraceEdge[] }): LayoutGraph {
  const byColumn = new Map<number, TraceNode[]>();
  for (const node of graph.nodes) {
    const col = columnFor(node.type);
    const bucket = byColumn.get(col);
    if (bucket) bucket.push(node);
    else byColumn.set(col, [node]);
  }

  const columns = [...byColumn.keys()].sort((a, b) => a - b);
  // Remap to consecutive x slots so sparse graphs don't leave empty columns.
  const xSlot = new Map<number, number>();
  columns.forEach((col, i) => xSlot.set(col, i));

  const maxRows = Math.max(1, ...[...byColumn.values()].map((bucket) => bucket.length));

  const positioned: PositionedNode[] = [];
  for (const [col, bucket] of byColumn) {
    bucket.forEach((node, row) => {
      positioned.push({ node, column: col, x: xSlot.get(col)!, y: row });
    });
  }

  const width = columns.length * (NODE_W + GAP_X) - GAP_X;
  const height = maxRows * (NODE_H + GAP_Y) - GAP_Y;

  // Absolute pixel positions (view box coordinates).
  const withPixels: PositionedNode[] = positioned.map((p) => ({
    ...p,
    x: p.x * (NODE_W + GAP_X),
    y: p.y * (NODE_H + GAP_Y),
  }));

  return { nodes: withPixels, edges: graph.edges, width, height };
}

export const GRAPH_NODE_SIZE = { width: NODE_W, height: NODE_H };
