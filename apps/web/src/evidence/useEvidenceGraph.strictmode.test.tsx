// @vitest-environment jsdom
//
// Regression tests for the "touch evidence → blank app" crash
// (Cannot read properties of null (reading 'nodeCount')):
//
// Root cause — React 18 StrictMode double-invokes effects. useEvidenceGraph
// used a SHARED `alive` ref: run 2 reset it to true, so run 1's (aborted)
// .finally() still executed setLoading(false) while run 2's fetch was in
// flight. The panel then rendered graph=null + loading=false + error=null,
// read `graph.nodeCount`, threw, and React unmounted the entire app.
//
// These tests pin: (1) the StrictMode race leaves loading=true until the
// LIVE run settles; (2) a nullish graph payload becomes an honest error;
// (3) the panel itself can never crash on a missing graph.

import { StrictMode, act } from 'react';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { EvidenceTraceGraph, TraceNode } from '@legalmet/types';

import { useEvidenceGraph } from './useEvidenceGraph';
import { EvidenceTracePanel } from './EvidenceTracePanel';

function makeGraph(id: string): EvidenceTraceGraph {
  const node: TraceNode = {
    id,
    type: 'INSPECTION',
    label: id,
    metadata: {},
  } as TraceNode;
  return {
    rootType: 'INSPECTION',
    rootId: id,
    inspectionId: 'i1',
    nodes: [node],
    edges: [],
    nodeCount: 1,
    edgeCount: 0,
    truncated: false,
    boundaryNote: '',
  };
}

function StateProbe({ loader }: { loader: Parameters<typeof useEvidenceGraph>[0] }) {
  const state = useEvidenceGraph(loader);
  return (
    <div>
      <span data-testid="loading">{String(state.loading)}</span>
      <span data-testid="error">{state.error ?? 'none'}</span>
      <span data-testid="graph">{state.graph ? state.graph.rootId : 'null'}</span>
    </div>
  );
}

afterEach(cleanup);

describe('useEvidenceGraph (StrictMode race regression)', () => {
  it('never exposes graph=null + loading=false while a run is still in flight', async () => {
    // Controlled promises matching the REAL loaders: the aborted run 1
    // REJECTS (signal.throwIfAborted()), the live run 2 resolves later.
    // The old code let run 1's .finally() flip loading=false while run 2
    // was still pending → graph=null + loading=false → panel crash.
    let rejectFirst!: (err: Error) => void;
    let resolveSecond!: (g: EvidenceTraceGraph) => void;
    const loader = vi
      .fn()
      .mockImplementationOnce(
        () => new Promise<EvidenceTraceGraph>((_r, rej) => (rejectFirst = rej)),
      )
      .mockImplementationOnce(
        () => new Promise<EvidenceTraceGraph>((r) => (resolveSecond = r)),
      );

    render(
      <StrictMode>
        <StateProbe loader={loader} />
      </StrictMode>,
    );
    // StrictMode fired the effect twice (two loader calls).
    expect(loader).toHaveBeenCalledTimes(2);

    // The aborted first run REJECTS — loading must STAY true (no graph, no
    // error): the dead run may not speak for the live one. The act() flush
    // matters: without it React never re-renders the old code's erroneous
    // setLoading(false), and the assertion would pass vacuously.
    await act(async () => {
      rejectFirst(new Error('Aborted'));
    });
    expect(screen.getByTestId('loading').textContent).toBe('true');
    expect(screen.getByTestId('graph').textContent).toBe('null');
    expect(screen.getByTestId('error').textContent).toBe('none');

    // The live run lands — now loading=false with the real graph.
    await act(async () => {
      resolveSecond(makeGraph('second-run'));
    });
    await waitFor(() => expect(screen.getByTestId('graph').textContent).toBe('second-run'));
    expect(screen.getByTestId('loading').textContent).toBe('false');
    expect(screen.getByTestId('error').textContent).toBe('none');
  });

  it('turns a nullish graph payload into an honest error (never a silent null)', async () => {
    // Typed as a lying backend would be: a payload that is present but null.
    const loader = vi.fn(
      async () => null as unknown as EvidenceTraceGraph,
    );

    render(<StateProbe loader={loader} />);

    await waitFor(() => expect(screen.getByTestId('loading').textContent).toBe('false'));
    expect(screen.getByTestId('graph').textContent).toBe('null');
    expect(screen.getByTestId('error').textContent).toMatch(
      /no evidence graph/i,
    );
  });
});

describe('EvidenceTracePanel (un-crashable on missing graph)', () => {
  it('renders an honest empty state instead of throwing when the graph is null', async () => {
    const loader = vi.fn(
      async () => null as unknown as EvidenceTraceGraph,
    );

    render(<EvidenceTracePanel loader={loader} inspectionId="i1" />);

    expect(
      await screen.findByText('Evidence trace unavailable'),
    ).toBeTruthy();
    // The crash was `graph.nodeCount` — assert the panel never rendered a
    // node count from a null graph (it would have thrown before this line).
    expect(screen.queryByText(/nodes · /i)).toBeNull();
  });

  it('renders the real graph normally after loading', async () => {
    const loader = vi.fn(async () => makeGraph('g1'));

    render(<EvidenceTracePanel loader={loader} inspectionId="i1" />);

    expect(await screen.findByText(/1 nodes · 0 relationships/i)).toBeTruthy();
  });
});
