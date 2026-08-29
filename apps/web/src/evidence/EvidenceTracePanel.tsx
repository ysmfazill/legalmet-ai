/**
 * Evidence trace panel (Prompt 7) — the composite traceability surface.
 *
 * Binds together the four trace primitives:
 * - WHY chain (the six-step narrative — Phase 8)
 * - Evidence graph view (deterministic layered SVG — Phase 9)
 * - Node detail panel (per-type whitelisted metadata — Phase 10)
 * - Image evidence modal (real pixels with overlays — Phase 11)
 *
 * The panel is read-only and stateless about compliance: it renders whatever
 * the backend traced, and the mandated boundary note is always visible.
 */
import { useState } from 'react';

import { EVIDENCE_GRAPH_BOUNDARY_NOTE } from '@legalmet/types';
import type { Json, TraceNode } from '@legalmet/types';

import { Badge } from '../components/Badge';
import { Icon } from '../components/Icon';
import { EmptyState } from '../components/states';
import { EvidenceGraphView } from './EvidenceGraphView';
import { ImageEvidenceModal } from './ImageEvidenceModal';
import { NodeDetailPanel } from './NodeDetailPanel';
import { WhyChain } from './WhyChain';
import { useEvidenceGraph, type EvidenceGraphLoader } from './useEvidenceGraph';

type TraceTab = 'why' | 'graph';

export function EvidenceTracePanel({
  loader,
  inspectionId,
}: {
  loader: EvidenceGraphLoader;
  /** Needed to open the image evidence modal against real images. */
  inspectionId: string;
}) {
  const state = useEvidenceGraph(loader);
  const [tab, setTab] = useState<TraceTab>('why');
  const [imageNode, setImageNode] = useState<{ imageId: string; regionId: string | null } | null>(
    null,
  );

  if (state.loading) {
    return (
      <div className="stack stack--sm">
        <p style={{ color: 'var(--text-muted)' }}>Tracing evidence chain…</p>
        <span className="spinner" aria-hidden />
      </div>
    );
  }

  if (state.error) {
    return (
      <EmptyState
        icon="alert"
        title="Evidence trace unavailable"
        message={state.error}
      />
    );
  }

  const graph = state.graph!;

  const onShowOnImage = (node: TraceNode) => {
    const m = (node.metadata ?? {}) as Record<string, Json>;
    if (typeof m.imageId !== 'string') return;
    const regionId = node.type === 'IMAGE_REGION' && typeof m.regionId === 'string' ? m.regionId : null;
    setImageNode({ imageId: m.imageId, regionId });
  };

  return (
    <div className="stack">
      <div className="row row--wrap" style={{ gap: 6, alignItems: 'center' }}>
        <Badge tone="neutral" dot>
          {graph.nodeCount} nodes · {graph.edgeCount} relationships
        </Badge>
        {graph.truncated && <Badge tone="warning">Bounded view (truncated)</Badge>}
        <span className="spacer" />
        <button
          type="button"
          className={tab === 'why' ? 'btn btn--subtle btn--sm' : 'btn btn--ghost btn--sm'}
          aria-pressed={tab === 'why'}
          onClick={() => setTab('why')}
        >
          Why chain
        </button>
        <button
          type="button"
          className={tab === 'graph' ? 'btn btn--subtle btn--sm' : 'btn btn--ghost btn--sm'}
          aria-pressed={tab === 'graph'}
          onClick={() => setTab('graph')}
        >
          Graph view
        </button>
      </div>

      {tab === 'why' ? <WhyChain graph={graph} /> : null}
      {tab === 'graph' ? (
        <div className="egraph-layout">
          <EvidenceGraphView
            graph={graph}
            selectedId={state.selectedId}
            onSelect={state.select}
          />
          {state.selectedNode ? (
            <div className="egraph-detail">
              <NodeDetailPanel
                node={state.selectedNode}
                edges={state.adjacency.get(state.selectedNode.id) ?? []}
              />
              {nodeHasImage(state.selectedNode) && (
                <button
                  type="button"
                  className="btn btn--subtle btn--sm"
                  onClick={() => onShowOnImage(state.selectedNode!)}
                >
                  <Icon name="eye" size={15} />
                  Show on the real image
                </button>
              )}
            </div>
          ) : (
            <p style={{ color: 'var(--text-muted)', fontSize: 'var(--fs-sm)' }}>
              Select a node to inspect its recorded metadata and relationships.
            </p>
          )}
        </div>
      ) : null}

      <p style={{ fontSize: 'var(--fs-xs)', color: 'var(--text-faint)', margin: 0 }}>
        {graph.boundaryNote || EVIDENCE_GRAPH_BOUNDARY_NOTE}
      </p>

      {imageNode && (
        <ImageEvidenceModal
          inspectionId={inspectionId}
          imageId={imageNode.imageId}
          highlightRegionId={imageNode.regionId}
          onClose={() => setImageNode(null)}
        />
      )}
    </div>
  );
}

function nodeHasImage(node: TraceNode): boolean {
  const m = (node.metadata ?? {}) as Record<string, Json>;
  return (
    typeof m.imageId === 'string' &&
    ['IMAGE', 'IMAGE_REGION', 'OCR_RESULT', 'EXTRACTED_FIELD'].includes(node.type)
  );
}
