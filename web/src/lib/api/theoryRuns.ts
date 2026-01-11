import { TheoryRunRequest, TheoryRunResult } from "../types/theoryRuns";

import { getApiBase } from "./apiBase";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const apiBase = getApiBase({
    serverInternalBaseEnv: process.env.SPORTS_API_INTERNAL_URL,
    serverPublicBaseEnv: process.env.NEXT_PUBLIC_THEORY_ENGINE_URL,
    localhostPort: 8000,
  });
  const res = await fetch(`${apiBase}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Request failed (${res.status}): ${body}`);
  }
  return res.json();
}

export async function createTheoryRun(payload: TheoryRunRequest): Promise<TheoryRunResult> {
  return request<TheoryRunResult>("/api/theory-runs", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function getTheoryRun(runId: string): Promise<TheoryRunResult> {
  return request<TheoryRunResult>(`/api/theory-runs/${runId}`);
}

