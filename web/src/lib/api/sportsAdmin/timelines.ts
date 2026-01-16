import { request } from "./client";

export interface MissingTimelineGame {
  game_id: number;
  game_date: string;
  league: string;
  home_team: string;
  away_team: string;
  status: string;
  has_pbp: boolean;
}

export interface MissingTimelinesResponse {
  games: MissingTimelineGame[];
  total_count: number;
}

export interface TimelineGenerationResponse {
  game_id: number;
  timeline_version: string;
  success: boolean;
  message: string;
}

export interface BatchGenerationResponse {
  games_processed: number;
  games_successful: number;
  games_failed: number;
  failed_game_ids: number[];
  message: string;
}

export interface ExistingTimelineGame {
  game_id: number;
  game_date: string;
  league: string;
  home_team: string;
  away_team: string;
  status: string;
  timeline_generated_at: string;
  last_social_at: string | null;
  is_stale: boolean;
}

export interface ExistingTimelinesResponse {
  games: ExistingTimelineGame[];
  total_count: number;
  stale_count: number;
}

export async function listMissingTimelines(params: {
  leagueCode?: string;
  daysBack?: number;
}): Promise<MissingTimelinesResponse> {
  const searchParams = new URLSearchParams();
  if (params.leagueCode) searchParams.set("league_code", params.leagueCode);
  if (params.daysBack) searchParams.set("days_back", params.daysBack.toString());

  return request(`/api/admin/sports/timelines/missing?${searchParams.toString()}`);
}

export async function generateTimelineForGame(
  gameId: number,
  timelineVersion: string = "v1"
): Promise<TimelineGenerationResponse> {
  return request(`/api/admin/sports/timelines/generate/${gameId}`, {
    method: "POST",
    body: JSON.stringify({ timeline_version: timelineVersion }),
  });
}

export async function generateMissingTimelines(params: {
  leagueCode: string;
  daysBack?: number;
  maxGames?: number;
}): Promise<BatchGenerationResponse> {
  return request("/api/admin/sports/timelines/generate-batch", {
    method: "POST",
    body: JSON.stringify({
      league_code: params.leagueCode,
      days_back: params.daysBack || 7,
      max_games: params.maxGames || null,
    }),
  });
}

export async function listExistingTimelines(params: {
  leagueCode?: string;
  daysBack?: number;
  onlyStale?: boolean;
}): Promise<ExistingTimelinesResponse> {
  const searchParams = new URLSearchParams();
  if (params.leagueCode) searchParams.set("league_code", params.leagueCode);
  if (params.daysBack) searchParams.set("days_back", params.daysBack.toString());
  if (params.onlyStale) searchParams.set("only_stale", "true");

  return request(`/api/admin/sports/timelines/existing?${searchParams.toString()}`);
}

export async function regenerateTimelines(params: {
  gameIds?: number[];
  leagueCode?: string;
  daysBack?: number;
  onlyStale?: boolean;
}): Promise<BatchGenerationResponse> {
  return request("/api/admin/sports/timelines/regenerate-batch", {
    method: "POST",
    body: JSON.stringify({
      game_ids: params.gameIds || null,
      league_code: params.leagueCode || "NBA",
      days_back: params.daysBack || 7,
      only_stale: params.onlyStale || false,
    }),
  });
}
