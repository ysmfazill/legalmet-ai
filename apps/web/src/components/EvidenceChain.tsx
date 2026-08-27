import { Icon } from './Icon';
import type { ChainNode } from '../mock/types';

const TYPE_LABEL: Record<ChainNode['type'], string> = {
  PACKAGE: 'Package',
  IMAGE: 'Image',
  IMAGE_REGION: 'Region',
  EXTRACTED_FIELD: 'Field',
  RULE: 'Rule',
  VALIDATION_RESULT: 'Validation',
  FINDING: 'Finding',
};

/**
 * Human-readable evidence chain:
 * PACKAGE → IMAGE → REGION → FIELD → RULE → VALIDATION → FINDING.
 * This is the provenance a judge follows from "AI detected" to "why flagged".
 */
export function EvidenceChain({ nodes }: { nodes: ChainNode[] }) {
  return (
    <div className="chain">
      {nodes.map((node, i) => (
        <div key={`${node.type}-${i}`} className="row" style={{ gap: 'var(--space-2)' }}>
          <div className="chain__node">
            <span className="chain__node-type">{TYPE_LABEL[node.type]}</span>
            <span className="chain__node-label">{node.label}</span>
            {node.detail && (
              <span className="chain__node-label" style={{ color: 'var(--text-faint)', fontSize: 11 }}>
                {node.detail}
              </span>
            )}
          </div>
          {i < nodes.length - 1 && (
            <span className="chain__arrow" aria-hidden>
              <Icon name="chevronRight" size={14} />
            </span>
          )}
        </div>
      ))}
    </div>
  );
}
