import { request } from "./client";
import type { TeamDetail, TeamListResponse } from "./types";

export async function listTeams(params?: {
  league?: string;
  search?: string;
  limit?: number;
  offset?: number;
}): Promise<TeamListResponse> {
  const query = new URLSearchParams();
  if (params?.league) query.append("league", params.league);
  if (params?.search) query.append("search", params.search);
  if (params?.limit) query.append("limit", String(params.limit));
  if (params?.offset) query.append("offset", String(params.offset));
  const qs = query.toString();
  return request(`/api/admin/sports/teams${qs ? `?${qs}` : ""}`);
}

export async function fetchTeam(teamId: number): Promise<TeamDetail> {
  return request(`/api/admin/sports/teams/${teamId}`);
}
