import { request } from "./client";
import type { AdminGameDetail, GameFilters, GameListResponse, JobResponse } from "./types";
import type { GameStoryResponse } from "./storyTypes";

export async function listGames(filters: GameFilters): Promise<GameListResponse> {
  const query = new URLSearchParams();
  const leagues = filters?.leagues ?? [];
  if (leagues.length) {
    leagues.forEach((lg) => query.append("league", lg));
  }
  if (filters?.season) query.append("season", String(filters.season));
  if (filters?.team) query.append("team", filters.team);
  if (filters?.startDate) query.append("startDate", filters.startDate);
  if (filters?.endDate) query.append("endDate", filters.endDate);
  if (filters?.missingBoxscore) query.append("missingBoxscore", "true");
  if (filters?.missingPlayerStats) query.append("missingPlayerStats", "true");
  if (filters?.missingOdds) query.append("missingOdds", "true");
  if (filters?.missingSocial) query.append("missingSocial", "true");
  if (filters?.missingAny) query.append("missingAny", "true");
  if (typeof filters?.limit === "number") query.append("limit", String(filters.limit));
  if (typeof filters?.offset === "number") query.append("offset", String(filters.offset));
  const qs = query.toString();
  return request(`/api/admin/sports/games${qs ? `?${qs}` : ""}`);
}

export async function fetchGame(gameId: number | string): Promise<AdminGameDetail> {
  const idStr = String(gameId);
  if (!/^\d+$/.test(idStr)) {
    throw new Error(`Invalid game id: ${idStr}`);
  }
  return request(`/api/admin/sports/games/${idStr}`);
}

export async function rescrapeGame(gameId: number): Promise<JobResponse> {
  return request(`/api/admin/sports/games/${gameId}/rescrape`, { method: "POST" });
}

export async function resyncOdds(gameId: number): Promise<JobResponse> {
  return request(`/api/admin/sports/games/${gameId}/resync-odds`, { method: "POST" });
}

/**
 * Fetch the v2-moments story for a game.
 * Returns null if no story exists (404).
 */
export async function fetchGameStory(gameId: number): Promise<GameStoryResponse | null> {
  try {
    return await request(`/api/admin/sports/games/${gameId}/story`);
  } catch (err) {
    // Return null for 404 (no story exists)
    // Error format is: "Request failed (404): {...}"
    if (err instanceof Error && err.message.startsWith("Request failed (404)")) {
      return null;
    }
    throw err;
  }
}
