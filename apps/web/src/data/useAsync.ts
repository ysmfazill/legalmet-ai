import { useCallback, useEffect, useState } from 'react';

/** Discriminated async state so components render loading/error/success exhaustively. */
export type AsyncState<T> =
  | { status: 'loading'; data: undefined; error: undefined }
  | { status: 'success'; data: T; error: undefined }
  | { status: 'error'; data: undefined; error: Error };

/**
 * Run an async producer and track its lifecycle. `deps` controls re-fetching;
 * `reload()` forces a refresh (used by error-state "Retry" buttons).
 */
export function useAsync<T>(
  fn: () => Promise<T>,
  deps: readonly unknown[] = [],
): AsyncState<T> & { reload: () => void } {
  const [state, setState] = useState<AsyncState<T>>({
    status: 'loading',
    data: undefined,
    error: undefined,
  });
  const [nonce, setNonce] = useState(0);
  const reload = useCallback(() => setNonce((n) => n + 1), []);

  useEffect(() => {
    let cancelled = false;
    setState({ status: 'loading', data: undefined, error: undefined });
    fn().then(
      (data) => {
        if (!cancelled) setState({ status: 'success', data, error: undefined });
      },
      (error: unknown) => {
        if (cancelled) return;
        setState({
          status: 'error',
          data: undefined,
          error: error instanceof Error ? error : new Error(String(error)),
        });
      },
    );
    return () => {
      cancelled = true;
    };
    // fn is intentionally excluded; `deps` + `nonce` drive re-fetching.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce]);

  return { ...state, reload };
}
