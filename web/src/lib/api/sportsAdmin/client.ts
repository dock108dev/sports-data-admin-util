/**
 * API client for sports admin endpoints.
 *
 * Handles both browser and server-side (SSR) requests. In Docker environments,
 * server-side requests use SPORTS_API_INTERNAL_URL to reach the API container
 * directly, while browser requests use NEXT_PUBLIC_SPORTS_API_URL.
 */

import { getApiBase } from "../apiBase";

/** Build headers including API key if configured. */
function buildHeaders(init?: RequestInit): HeadersInit {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init?.headers as Record<string, string> ?? {}),
  };

  // Add API key for authentication (server-side only, not exposed to browser)
  const apiKey = process.env.SPORTS_API_KEY;
  if (apiKey) {
    headers["X-API-Key"] = apiKey;
  }

  return headers;
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const apiBase = getApiBase({
    serverInternalBaseEnv: process.env.SPORTS_API_INTERNAL_URL,
    serverPublicBaseEnv: process.env.NEXT_PUBLIC_SPORTS_API_URL,
    localhostPort: 8000,
  });
  const url = `${apiBase}${path}`;

  try {
    const res = await fetch(url, {
      ...init,
      headers: buildHeaders(init),
      cache: "no-store",
    });

    if (!res.ok) {
      const body = await res.text();
      throw new Error(`Request failed (${res.status}): ${body}`);
    }

    return await res.json();
  } catch (err) {
    if (err instanceof TypeError && err.message.includes("fetch")) {
      throw new Error(`Failed to connect to backend at ${apiBase}. Is the server running?`);
    }
    throw err;
  }
}

export async function requestBlob(path: string, init?: RequestInit): Promise<Blob> {
  const apiBase = getApiBase({
    serverInternalBaseEnv: process.env.SPORTS_API_INTERNAL_URL,
    serverPublicBaseEnv: process.env.NEXT_PUBLIC_SPORTS_API_URL,
    localhostPort: 8000,
  });
  const url = `${apiBase}${path}`;
  const res = await fetch(url, {
    ...init,
    headers: buildHeaders(init),
    cache: "no-store",
  });

  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Request failed (${res.status}): ${body}`);
  }
  return await res.blob();
}
