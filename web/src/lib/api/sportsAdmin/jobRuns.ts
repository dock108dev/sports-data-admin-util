import { request } from "./client";

export interface JobRunResponse {
  id: number;
  phase: string;
  leagues: string[];
  status: string;
  startedAt: string;
  finishedAt: string | null;
  durationSeconds: number | null;
  errorSummary: string | null;
  summaryData: Record<string, unknown> | null;
  celeryTaskId: string | null;
  createdAt: string;
}

export interface JobRunFilters {
  phase?: string;
  status?: string;
  limit?: number;
}

export async function listJobRuns(filters: JobRunFilters = {}): Promise<JobRunResponse[]> {
  const query = new URLSearchParams();
  if (filters.phase) query.append("phase", filters.phase);
  if (filters.status) query.append("status", filters.status);
  if (typeof filters.limit === "number") query.append("limit", String(filters.limit));
  const qs = query.toString();
  return request(`/api/admin/sports/jobs${qs ? `?${qs}` : ""}`);
}

export async function cancelJobRun(runId: number): Promise<JobRunResponse> {
  return request(`/api/admin/sports/jobs/${runId}/cancel`, { method: "POST" });
}
