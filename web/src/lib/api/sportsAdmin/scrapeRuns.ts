import { request } from "./client";
import type { ScrapeRunResponse } from "./types";

export async function listScrapeRuns(params?: { league?: string; status?: string }): Promise<ScrapeRunResponse[]> {
  const query = new URLSearchParams();
  if (params?.league) query.append("league", params.league);
  if (params?.status) query.append("status", params.status);
  const qs = query.toString();
  return request(`/api/admin/sports/scraper/runs${qs ? `?${qs}` : ""}`);
}

export type DockerLogsResponse = {
  container: string;
  lines: number;
  logs: string;
};

export async function fetchDockerLogs(container: string, lines = 1000): Promise<DockerLogsResponse> {
  return request(`/api/admin/sports/logs?container=${container}&lines=${lines}`);
}
