/**
 * Centralized API base resolution for the admin UI.
 *
 * Why this exists:
 * - Next.js inlines `NEXT_PUBLIC_*` variables at build time into the browser bundle.
 * - Our CI builds the `web` image without production-specific build args, so defaults like
 *   `http://localhost:8000` can get baked into the client and break production.
 *
 * Approach:
 * - In the browser: prefer same-origin requests (`/api/...`) in production, and auto-target
 *   `http://localhost:8000` when developing on localhost.
 * - On the server (SSR): use an internal base URL to reach the API container.
 */

type ApiBaseOptions = {
  /**
   * Used only when rendering on the server.
   * Example (docker): http://api:8000
   */
  serverInternalBaseEnv?: string;
  /**
   * Used only when rendering on the server as a fallback.
   * Example (non-docker SSR): http://localhost:8000
   */
  serverPublicBaseEnv?: string;
  /**
   * Used only in the browser on localhost.
   */
  localhostPort?: number;
};

export function getApiBase(options?: ApiBaseOptions): string {
  const isBrowser = typeof window !== "undefined";

  if (isBrowser) {
    // Browser requests go through the Next.js proxy to add the API key
    // The proxy is at /api/proxy/... and forwards to the backend
    return "/api/proxy";
  }

  // Server-side requests can call the backend directly with the API key
  const serverInternalBase = options?.serverInternalBaseEnv;
  if (serverInternalBase) return serverInternalBase;

  const serverPublicBase = options?.serverPublicBaseEnv;
  if (serverPublicBase) return serverPublicBase;

  // Local dev SSR fallback (e.g. `pnpm dev` running on the host).
  return "http://localhost:8000";
}

