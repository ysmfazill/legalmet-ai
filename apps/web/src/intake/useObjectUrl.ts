import { useEffect, useState } from 'react';

import { fetchObjectUrl } from '../api/client';

export type ObjectUrlState =
  | { status: 'loading' }
  | { status: 'ready'; url: string }
  | { status: 'error'; message: string };

/**
 * Load a bearer-authenticated stored object as a blob URL, revoking it on
 * unmount / key change. Used to render real intake images (a plain `<img src>`
 * can't attach the Authorization header the `/storage` route requires).
 */
export function useObjectUrl(storageKey?: string | null): ObjectUrlState {
  const [state, setState] = useState<ObjectUrlState>(
    storageKey ? { status: 'loading' } : { status: 'error', message: 'No image available' },
  );

  useEffect(() => {
    if (!storageKey) {
      setState({ status: 'error', message: 'No image available' });
      return;
    }
    let disposed = false;
    let created: string | null = null;
    const controller = new AbortController();
    setState({ status: 'loading' });

    fetchObjectUrl(storageKey, controller.signal).then(
      (url) => {
        if (disposed) {
          URL.revokeObjectURL(url);
          return;
        }
        created = url;
        setState({ status: 'ready', url });
      },
      (error: unknown) => {
        if (disposed) return;
        setState({
          status: 'error',
          message: error instanceof Error ? error.message : 'Failed to load image',
        });
      },
    );

    return () => {
      disposed = true;
      controller.abort();
      if (created) URL.revokeObjectURL(created);
    };
  }, [storageKey]);

  return state;
}
