import { fileURLToPath } from 'node:url';

import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

/**
 * Vite config for @legalmet/web.
 *
 * The shared workspace packages ship raw TypeScript (their `main`/`exports`
 * point at `src/index.ts`), so we alias them to source. This mirrors the path
 * aliases in `tsconfig.base.json` and lets Vite transpile them as first-class
 * project source instead of treating them as opaque `node_modules`.
 *
 * `/api` is proxied to the FastAPI backend in dev so the browser talks to the
 * frontend origin only (no CORS juggling during development).
 */
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@legalmet/types': fileURLToPath(
        new URL('../../packages/types/src/index.ts', import.meta.url),
      ),
      '@legalmet/config': fileURLToPath(
        new URL('../../packages/config/src/index.ts', import.meta.url),
      ),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
});
