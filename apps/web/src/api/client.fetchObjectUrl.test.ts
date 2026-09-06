// @vitest-environment jsdom
//
// fetchObjectUrl is the ONLY way stored package images reach the UI (the
// /storage route is bearer-authenticated; a plain <img src> gets a 401). These
// tests pin the honest per-status messages the image components surface.

import { afterEach, describe, expect, it, vi } from 'vitest';

import { ApiClientError, fetchObjectUrl, setToken } from './client';

function jsonResponse(status: number, message?: string): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () =>
      message ? { error: { code: 'X', message } } : {},
  } as unknown as Response;
}

afterEach(() => {
  vi.unstubAllGlobals();
  setToken(null);
});

describe('fetchObjectUrl (authenticated image loading + error matrix)', () => {
  it('sends the bearer token with the storage request', async () => {
    setToken('tok-123');
    const fetchMock = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({}),
      blob: async () => new Blob(['png'], { type: 'image/png' }),
    }) as unknown as Response);
    vi.stubGlobal('fetch', fetchMock);
    vi.stubGlobal('URL', {
      ...URL,
      createObjectURL: () => 'blob:fake',
      revokeObjectURL: () => {},
    });

    await fetchObjectUrl('packages/photo.png');

    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toContain('/storage/packages/photo.png');
    expect((init.headers as Record<string, string>).Authorization).toBe('Bearer tok-123');
  });

  it('401 → "Session expired. Please sign in again."', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(401, 'Not authenticated')));
    vi.stubGlobal('URL', { ...URL, createObjectURL: () => 'blob:fake', revokeObjectURL: () => {} });

    await expect(fetchObjectUrl('k')).rejects.toMatchObject({
      name: 'ApiClientError',
      status: 401,
      message: 'Session expired. Please sign in again.',
    });
  });

  it('404 → "Source image unavailable."', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(404, 'Not found')));
    vi.stubGlobal('URL', { ...URL, createObjectURL: () => 'blob:fake', revokeObjectURL: () => {} });

    await expect(fetchObjectUrl('k')).rejects.toMatchObject({
      status: 404,
      message: 'Source image unavailable.',
    });
  });

  it('other failures keep the backend message (never an empty-image look)', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(503, 'Database unavailable')));
    vi.stubGlobal('URL', { ...URL, createObjectURL: () => 'blob:fake', revokeObjectURL: () => {} });

    const err = await fetchObjectUrl('k').catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiClientError);
    expect((err as ApiClientError).status).toBe(503);
    expect((err as ApiClientError).message).toBe('Database unavailable');
  });

  it('success returns a blob object URL for the stored bytes', async () => {
    const blob = new Blob(['png-bytes'], { type: 'image/png' });
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({ ok: true, status: 200, blob: async () => blob }) as unknown as Response),
    );
    let created: Blob | null = null;
    vi.stubGlobal('URL', {
      ...URL,
      createObjectURL: (b: Blob) => {
        created = b;
        return 'blob:created';
      },
      revokeObjectURL: () => {},
    });

    await expect(fetchObjectUrl('k')).resolves.toBe('blob:created');
    expect(created).toBe(blob);
  });
});
