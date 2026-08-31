/**
 * @vitest-environment jsdom
 *
 * Tests for the evidence-graph trace interaction state (Prompt 12, G).
 *
 * Covers the hook that drives the graph view: arming trace mode, the traced
 * node/edge id sets, re-tracing on another node, clearing the trace, the
 * honest empty state for an isolated node, evaluationId preservation through
 * the loader, and trace invalidation on graph reload.
 */
import { renderHook, act } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { EvidenceTraceGraph } from '@legalmet/types';

import { useEvidenceGraph } from './useEvidenceGraph';

function graphFixture(overrides: Partial<EvidenceTraceGraph> = {}): EvidenceTraceGraph {
  return {
    rootType: 'FINDING',
    rootId: '00000000-0000-0000-0000-000000000001',
    inspectionId: '00000000-0000-0000-0000-000000000002',
    evaluationId: '00000000-0000-0000-0000-000000000003',
    nodes: [
      { id: 'FINDING:1', type: 'FINDING', label: 'f' },
      { id: 'EXTRACTED_FIELD:1', type: 'EXTRACTED_FIELD', label: 'field' },
      { id: 'OCR_RESULT:1', type: 'OCR_RESULT', label: 'ocr' },
      { id: 'IMAGE:1', type: 'IMAGE', label: 'img' },
    ],
    edges: [
      { id: 'e1', source: 'FINDING:1', target: 'EXTRACTED_FIELD:1', type: 'FINDING_SUPPORTED_BY_EVIDENCE' },
      { id: 'e2', source: 'OCR_RESULT:1', target: 'EXTRACTED_FIELD:1', type: 'OCR_SUPPORTS_FIELD' },
    ],
    nodeCount: 4,
    edgeCount: 2,
    truncated: false,
    boundaryNote: 'note',
    ...overrides,
  } as EvidenceTraceGraph;
}

function makeLoader(fixture: EvidenceTraceGraph) {
  return vi.fn(async () => fixture);
}

describe('useEvidenceGraph — trace interaction', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('starts with trace mode off and an empty trace', async () => {
    const { result } = renderHook(() => useEvidenceGraph(makeLoader(graphFixture())));
    await waitForLoad(result);
    expect(result.current.tracing).toBe(false);
    expect(result.current.trace.nodeIds.size).toBe(0);
    expect(result.current.traceEmpty).toBe(false);
  });

  it('arming trace on a selected node highlights the connected chain', async () => {
    const { result } = renderHook(() => useEvidenceGraph(makeLoader(graphFixture())));
    await waitForLoad(result);

    act(() => result.current.select('FINDING:1'));
    expect(result.current.selectedId).toBe('FINDING:1');

    act(() => result.current.startTrace());
    expect(result.current.tracing).toBe(true);
    expect(result.current.traceRootId).toBe('FINDING:1');
    expect(result.current.trace.nodeIds.has('FINDING:1')).toBe(true);
    expect(result.current.trace.nodeIds.has('EXTRACTED_FIELD:1')).toBe(true);
    expect(result.current.trace.nodeIds.has('OCR_RESULT:1')).toBe(true);
    expect(result.current.trace.nodeIds.has('IMAGE:1')).toBe(false); // not connected in the fixture
    expect(result.current.trace.edgeIds.has('e1')).toBe(true);
    expect(result.current.trace.edgeIds.has('e2')).toBe(true);
  });

  it('startTrace without an explicit node uses the current selection (no stale closure)', async () => {
    const { result } = renderHook(() => useEvidenceGraph(makeLoader(graphFixture())));
    await waitForLoad(result);

    act(() => result.current.select('OCR_RESULT:1'));
    act(() => result.current.startTrace());
    expect(result.current.traceRootId).toBe('OCR_RESULT:1');
    expect(result.current.trace.nodeIds.has('FINDING:1')).toBe(true); // connected through e2→e1
  });

  it('selecting another node while tracing re-traces from that node', async () => {
    const { result } = renderHook(() => useEvidenceGraph(makeLoader(graphFixture())));
    await waitForLoad(result);

    act(() => result.current.startTrace('FINDING:1'));
    expect(result.current.traceRootId).toBe('FINDING:1');

    act(() => result.current.startTrace('OCR_RESULT:1'));
    expect(result.current.traceRootId).toBe('OCR_RESULT:1');
    expect(result.current.tracing).toBe(true);
  });

  it('clearTrace restores the normal graph state', async () => {
    const { result } = renderHook(() => useEvidenceGraph(makeLoader(graphFixture())));
    await waitForLoad(result);

    act(() => result.current.startTrace('FINDING:1'));
    expect(result.current.tracing).toBe(true);

    act(() => result.current.clearTrace());
    expect(result.current.tracing).toBe(false);
    expect(result.current.traceRootId).toBe(null);
    expect(result.current.trace.nodeIds.size).toBe(0);
    // The selection itself survives — the detail panel stays usable.
    expect(result.current.selectedId).toBe('FINDING:1');
  });

  it('an isolated node reports the honest empty trace state', async () => {
    const fixture = graphFixture({
      nodes: [
        { id: 'FINDING:1', type: 'FINDING', label: 'f' },
        { id: 'AUDIT_EVENT:9', type: 'AUDIT_EVENT', label: 'audit' },
      ],
      edges: [],
      nodeCount: 2,
      edgeCount: 0,
    });
    const { result } = renderHook(() => useEvidenceGraph(makeLoader(fixture)));
    await waitForLoad(result);

    act(() => result.current.startTrace('AUDIT_EVENT:9'));
    expect(result.current.tracing).toBe(true);
    expect(result.current.traceEmpty).toBe(true);
    expect(result.current.trace.edgeIds.size).toBe(0);
  });

  it('startTrace with no selection is a no-op (button stays disabled in the UI)', async () => {
    const { result } = renderHook(() => useEvidenceGraph(makeLoader(graphFixture())));
    await waitForLoad(result);

    act(() => result.current.startTrace());
    expect(result.current.tracing).toBe(false);
  });

  it('preserves the evaluationId returned by the loader', async () => {
    const evaluationId = '00000000-0000-0000-0000-000000000abc';
    const { result } = renderHook(() =>
      useEvidenceGraph(makeLoader(graphFixture({ evaluationId }))),
    );
    await waitForLoad(result);
    expect(result.current.graph?.evaluationId).toBe(evaluationId);
  });

  it('invalidates the trace when a reloaded graph no longer contains the trace root', async () => {
    let fixture = graphFixture();
    const loader = vi.fn(async () => fixture);
    const { result } = renderHook(() => useEvidenceGraph(loader));
    await waitForLoad(result);

    act(() => result.current.startTrace('FINDING:1'));
    expect(result.current.tracing).toBe(true);

    // Reload with a graph whose node ids are all different.
    fixture = graphFixture({
      nodes: [{ id: 'FINDING:other', type: 'FINDING', label: 'f2' }],
      edges: [],
      nodeCount: 1,
      edgeCount: 0,
    });
    await act(async () => {
      result.current.reload();
    });
    await waitForLoad(result);
    expect(result.current.tracing).toBe(false);
    expect(result.current.traceRootId).toBe(null);
  });
});

// The hook flips loading→loaded asynchronously; settle real timers inside
// act, bounded (100 × 10 ms) so a regression can never hang the suite.
async function waitForLoad(result: { current: ReturnType<typeof useEvidenceGraph> }) {
  for (let i = 0; i < 100 && result.current.loading; i += 1) {
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 10));
    });
  }
  expect(result.current.loading).toBe(false);
  expect(result.current.error).toBeNull();
}
