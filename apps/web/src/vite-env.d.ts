/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Base URL the API client prepends to requests. See `src/api/client.ts`. */
  readonly VITE_API_BASE_URL?: string;
  /**
   * DEV ONLY — seeded inspector account the SPA silently signs in as so real
   * package intake can call the authenticated API. Never a real credential.
   */
  readonly VITE_DEMO_EMAIL?: string;
  readonly VITE_DEMO_PASSWORD?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
