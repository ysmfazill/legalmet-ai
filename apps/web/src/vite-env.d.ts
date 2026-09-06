/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Base URL the API client prepends to requests. See `src/api/client.ts`. */
  readonly VITE_API_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
