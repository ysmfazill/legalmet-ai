/**
 * Tests for the Evidence Graph trace algorithm (Prompt 12, requirement G).
 *
 * The graph fixtures mirror the REAL backend shape: node ids are
 * "<TYPE>:<uuid>" and edge ids are "<RELATION>:<source>-><target>" — the same
 * strings the API returns (see services/api/app/services/evidence_graph/
 * builder.py). No fabricated relationships: every fixture edge connects two
 * fixture nodes, exactly as the backend guarantees.
 */
import { describe, expect, it } from 'vitest';

import { describeChain, EMPTY_TRACE, traceFrom } from './tracePath';
import type { TraceableGraph } from './tracePath';

/** A real-shaped chain: FINDING → RULE → REQUIREMENT and FINDING → FIELD → OCR → REGION → IMAGE. */
const CHAIN: TraceableGraph = {
  nodes: [
    { id: 'FINDING:1', type: 'FINDING' },
    { id: 'RULE:1', type: 'RULE' },
    { id: 'REQUIREMENT:1', type: 'REQUIREMENT' },
    { id: 'EVALUATION:1', type: 'EVALUATION' },
    { id: 'EXTRACTED_FIELD:1', type: 'EXTRACTED_FIELD' },
    { id: 'OCR_RESULT:1', type: 'OCR_RESULT' },
    { id: 'IMAGE_REGION:1', type: 'IMAGE_REGION' },
    { id: 'IMAGE:1', type: 'IMAGE' },
    // An unrelated island that must NEVER enter the trace.
    { id: 'AUDIT_EVENT:99', type: 'AUDIT_EVENT' },
  ],
  edges: [
    {
      id: 'RULE_PRODUCED_FINDING:RULE:1->FINDING:1',
      source: 'RULE:1',
      target: 'FINDING:1',
    },
    {
      id: 'REQUIREMENT_EVALUATED_BY_RULE:REQUIREMENT:1->RULE:1',
      source: 'REQUIREMENT:1',
      target: 'RULE:1',
    },
    {
      id: 'FINDING_BELONGS_TO_EVALUATION:FINDING:1->EVALUATION:1',
      source: 'FINDING:1',
      target: 'EVALUATION:1',
    },
    {
      id: 'FINDING_SUPPORTED_BY_EVIDENCE:FINDING:1->EXTRACTED_FIELD:1',
      source: 'FINDING:1',
      target: 'EXTRACTED_FIELD:1',
    },
    {
      id: 'OCR_SUPPORTS_FIELD:OCR_RESULT:1->EXTRACTED_FIELD:1',
      source: 'OCR_RESULT:1',
      target: 'EXTRACTED_FIELD:1',
    },
    {
      id: 'REGION_HAS_OCR_RESULT:IMAGE_REGION:1->OCR_RESULT:1',
      source: 'IMAGE_REGION:1',
      target: 'OCR_RESULT:1',
    },
    {
      id: 'IMAGE_HAS_REGION:IMAGE:1->IMAGE_REGION:1',
      source: 'IMAGE:1',
      target: 'IMAGE_REGION:1',
    },
  ],
};

describe('traceFrom', () => {
  it('traces the FULL chain from a finding — both regulatory and evidence halves', () => {
    const trace = traceFrom(CHAIN, 'FINDING:1');
    expect([...trace.nodeIds].sort()).toEqual(
      [
        'FINDING:1',
        'RULE:1',
        'REQUIREMENT:1',
        'EVALUATION:1',
        'EXTRACTED_FIELD:1',
        'OCR_RESULT:1',
        'IMAGE_REGION:1',
        'IMAGE:1',
      ].sort(),
    );
    // Every one of the 7 connected edges is traced.
    expect(trace.edgeIds.size).toBe(7);
    expect(trace.edgeIds.has('FINDING_SUPPORTED_BY_EVIDENCE:FINDING:1->EXTRACTED_FIELD:1')).toBe(
      true,
    );
  });

  it('traces upstream from the image to the finding (reverse direction)', () => {
    const trace = traceFrom(CHAIN, 'IMAGE:1');
    expect(trace.nodeIds.has('FINDING:1')).toBe(true);
    expect(trace.nodeIds.has('REQUIREMENT:1')).toBe(true);
    expect(trace.nodeIds.has('AUDIT_EVENT:99')).toBe(false);
  });

  it('never includes the unrelated island node or its edges', () => {
    const trace = traceFrom(CHAIN, 'FINDING:1');
    expect(trace.nodeIds.has('AUDIT_EVENT:99')).toBe(false);
  });

  it('returns the selection itself with no edges for an isolated node (honest empty state)', () => {
    const trace = traceFrom(CHAIN, 'AUDIT_EVENT:99');
    expect(trace.nodeIds).toEqual(new Set(['AUDIT_EVENT:99']));
    expect(trace.edgeIds.size).toBe(0);
    expect(trace.order).toEqual(['AUDIT_EVENT:99']);
  });

  it('returns EMPTY_TRACE for an id that is not a node of the graph', () => {
    expect(traceFrom(CHAIN, 'FINDING:does-not-exist')).toEqual(EMPTY_TRACE);
    expect(traceFrom(CHAIN, null)).toEqual(EMPTY_TRACE);
  });

  it('deterministically orders the discovery with the selection first', () => {
    const trace = traceFrom(CHAIN, 'FINDING:1');
    expect(trace.order[0]).toBe('FINDING:1');
  });

  it('handles a cycle without infinite recursion', () => {
    const cyclic: TraceableGraph = {
      nodes: [
        { id: 'A', type: 'IMAGE' },
        { id: 'B', type: 'OCR_RESULT' },
      ],
      edges: [
        { id: 'e1', source: 'A', target: 'B' },
        { id: 'e2', source: 'B', target: 'A' },
      ],
    };
    const trace = traceFrom(cyclic, 'A');
    expect(trace.nodeIds).toEqual(new Set(['A', 'B']));
    expect(trace.edgeIds).toEqual(new Set(['e1', 'e2']));
  });
});

describe('describeChain', () => {
  it('lists the node types in discovery order, deduplicated', () => {
    const trace = traceFrom(CHAIN, 'FINDING:1');
    const label = describeChain(CHAIN, trace);
    expect(label).toContain('FINDING');
    expect(label).toContain('RULE');
    expect(label).toContain('IMAGE');
    expect(label.startsWith('FINDING →')).toBe(true);
  });

  it('returns an empty label for an empty trace', () => {
    expect(describeChain(CHAIN, EMPTY_TRACE)).toBe('');
  });
});
