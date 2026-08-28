/// <reference types="vite/client" />

/**
 * Types for this app's environment variables.
 *
 * Vite exposes only `VITE_`-prefixed variables to client code. Declaring them
 * here means `import.meta.env` is typed instead of `any`, which type-aware lint
 * rules (no-unsafe-assignment) would otherwise flag.
 */
interface ViteTypeOptions {
  strictImportMetaEnv: unknown
}

interface ImportMetaEnv {
  /** Backend base URL. Defaults to `/api` (proxied to the backend in dev). */
  readonly VITE_API_BASE_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
