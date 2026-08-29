/**
 * Evidence Graph view (Prompt 7, Phases 9–11).
 *
 * Renders the read-only traceability graph as an SVG diagram with a
 * deterministic layered layout (see graphLayout.ts — same input, same picture,
 * every time). Every node and edge shown corresponds to a REAL persisted
 * record returned by the backend: nothing here is hard-coded or invented.
 *
 * Interaction model:
 * - Click a node → it becomes the selection; its edges highlight; the detail
 *   panel (rendered by the parent) shows its whitelisted metadata.
 * - Hover → highlight the node's immediate relationships.
 * - The view is read-only. There is no compliance action anywhere in it.
 */
import { useMemo, useState } from 'react';

import {
  EVIDENCE_GRAPH_EDGE_META,
  EVIDENCE_GRAPH_NODE_META,
} from '@legalmet/config';
import type { EvidenceTraceGraph, TraceEdge } from '@legalmet/types';

import { cn } from '../lib/cn';
import { toneColor } from '../lib/tone';
import { GRAPH_NODE_SIZE, layoutGraph } from './graphLayout';

const { width: NODE_W, height: NODE_H } = GRAPH_NODE_SIZE;

function truncate(text: string, max = 22): string {
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

export function EvidenceGraphView({
  graph,
  selectedId,
  onSelect,
  maxHeight = 520,
}: {
  graph: EvidenceTraceGraph;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  maxHeight?: number;
}) {
  const [hoveredId, setHoveredId] = useState<string | null>(null);

  const layout = useMemo(() => layoutGraph(graph), [graph]);

  const positions = useMemo(() => {
    const map = new Map<string, { x: number; y: number }>();
    for (const p of layout.nodes) map.set(p.node.id, { x: p.x, y: p.y });
    return map;
  }, [layout]);

  const focusId = hoveredId ?? selectedId;
  const related = useMemo(() => {
    if (!focusId) return null;
    const set = new Set<string>([focusId]);
    for (const e of graph.edges) {
      if (e.source === focusId) set.add(e.target);
      if (e.target === focusId) set.add(e.source);
    }
    return set;
  }, [focusId, graph.edges]);

  const pad = 24;
  const viewBoxWidth = layout.width + pad * 2;
  const viewBoxHeight = layout.height + pad * 2;

  return (
    <div className="egraph" style={{ maxHeight }}>
      {graph.truncated && (
        <div className="egraph__cap">
          Bounded view — the traversal hit a server-side cap. The oldest audit events / largest
          evidence sets are truncated, never silently dropped.
        </div>
      )}
      <div className="egraph__scroll">
        <svg
          role="img"
          aria-label={`Evidence traceability graph: ${graph.nodeCount} nodes, ${graph.edgeCount} relationships`}
          viewBox={`0 0 ${viewBoxWidth} ${viewBoxHeight}`}
          style={{ minWidth: Math.min(viewBoxWidth, 640), width: '100%', height: 'auto' }}
        >
          {/* Edges first so nodes sit on top. */}
          {layout.edges.map((edge: TraceEdge) => {
            const from = positions.get(edge.source);
            const to = positions.get(edge.target);
            if (!from || !to) return null;
            const active = focusId != null && (edge.source === focusId || edge.target === focusId);
            const x1 = from.x + NODE_W / 2 + pad;
            const y1 = from.y + NODE_H / 2 + pad;
            const x2 = to.x + NODE_W / 2 + pad;
            const y2 = to.y + NODE_H / 2 + pad;
            // Simple straight links between node centres; nodes render opaque
            // on top so the visible segment reads as edge-to-edge.
            return (
              <line
                key={edge.id}
                x1={x1}
                y1={y1}
                x2={x2}
                y2={y2}
                className={cn('egraph__edge', active && 'is-active')}
                stroke={active ? 'var(--tone-info)' : undefined}
              >
                <title>{`${
                  EVIDENCE_GRAPH_EDGE_META[edge.type]?.label ?? edge.type
                }: ${edge.source} → ${edge.target}`}</title>
              </line>
            );
          })}

          {/* Nodes */}
          {layout.nodes.map(({ node, x, y }) => {
            const meta = EVIDENCE_GRAPH_NODE_META[node.type];
            const isSelected = node.id === selectedId;
            const dimmed = related != null && !related.has(node.id);
            return (
              <g
                key={node.id}
                transform={`translate(${x + pad}, ${y + pad})`}
                className={cn(
                  'egraph__node',
                  isSelected && 'is-selected',
                  dimmed && 'is-dimmed',
                )}
                onClick={() => onSelect(isSelected ? null : node.id)}
                onMouseEnter={() => setHoveredId(node.id)}
                onMouseLeave={() => setHoveredId(null)}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    onSelect(isSelected ? null : node.id);
                  }
                }}
                aria-label={`${meta.label}: ${node.label}`}
              >
                <rect width={NODE_W} height={NODE_H} rx={8} />
                <circle
                  cx={12}
                  cy={NODE_H / 2}
                  r={4}
                  fill={toneColor(meta.tone)}
                  aria-hidden
                />
                <text x={24} y={NODE_H / 2 - 4} className="egraph__node-type">
                  {meta.label}
                </text>
                <text x={24} y={NODE_H / 2 + 12} className="egraph__node-label">
                  {truncate(node.label)}
                </text>
                <title>{`${meta.label}: ${node.label}\n${node.id}`}</title>
              </g>
            );
          })}
        </svg>
      </div>

      <div className="egraph__legend row row--wrap" style={{ gap: 'var(--space-2)' }}>
        {Object.entries(EVIDENCE_GRAPH_NODE_META).map(([kind, meta]) => (
          <span key={kind} className="egraph__legend-item">
            <span className="badge__dot" style={{ color: toneColor(meta.tone) }} aria-hidden />
            {meta.label}
          </span>
        ))}
      </div>
    </div>
  );
}
