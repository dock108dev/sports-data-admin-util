import { request } from "./sportsAdmin/client";
import type {
  GolfTournament,
  GolfPlayer,
  GolfFieldEntry,
  GolfLeaderboardEntry,
  GolfRound,
  GolfOddsEntry,
  GolfDFSProjection,
  GolfPlayerStats,
} from "./golfTypes";
import type { TriggerTaskResponse } from "./sportsAdmin/taskControl";

// ── Tournaments ──

export interface TournamentFilters {
  tour?: string;
  season?: number;
  status?: string;
  limit?: number;
}

export async function listTournaments(
  params?: TournamentFilters
): Promise<GolfTournament[]> {
  const query = new URLSearchParams();
  if (params?.tour) query.append("tour", params.tour);
  if (params?.season != null) query.append("season", String(params.season));
  if (params?.status) query.append("status", params.status);
  if (params?.limit != null) query.append("limit", String(params.limit));
  const qs = query.toString();
  return request(`/api/golf/tournaments${qs ? `?${qs}` : ""}`);
}

export async function fetchTournament(
  eventId: string
): Promise<GolfTournament> {
  return request(`/api/golf/tournaments/${eventId}`);
}

export async function fetchTournamentField(
  eventId: string
): Promise<GolfFieldEntry[]> {
  return request(`/api/golf/tournaments/${eventId}/field`);
}

export async function fetchTournamentLeaderboard(
  eventId: string
): Promise<GolfLeaderboardEntry[]> {
  return request(`/api/golf/tournaments/${eventId}/leaderboard`);
}

export async function fetchTournamentRounds(
  eventId: string,
  roundNum?: number
): Promise<GolfRound[]> {
  const query = new URLSearchParams();
  if (roundNum != null) query.append("round", String(roundNum));
  const qs = query.toString();
  return request(`/api/golf/tournaments/${eventId}/rounds${qs ? `?${qs}` : ""}`);
}

// ── Players ──

export async function searchPlayers(
  q: string,
  limit?: number
): Promise<GolfPlayer[]> {
  const query = new URLSearchParams({ q });
  if (limit != null) query.append("limit", String(limit));
  return request(`/api/golf/players?${query.toString()}`);
}

export async function fetchPlayer(dgId: number): Promise<GolfPlayer> {
  return request(`/api/golf/players/${dgId}`);
}

export async function fetchPlayerStats(
  dgId: number
): Promise<GolfPlayerStats[]> {
  return request(`/api/golf/players/${dgId}/stats`);
}

// ── Odds ──

export interface OddsFilters {
  tournament_id?: number;
  market?: string;
  book?: string;
}

export async function fetchOutrightOdds(
  params?: OddsFilters
): Promise<GolfOddsEntry[]> {
  const query = new URLSearchParams();
  if (params?.tournament_id != null)
    query.append("tournament_id", String(params.tournament_id));
  if (params?.market) query.append("market", params.market);
  if (params?.book) query.append("book", params.book);
  const qs = query.toString();
  return request(`/api/golf/odds${qs ? `?${qs}` : ""}`);
}

// ── DFS ──

export interface DFSFilters {
  tournament_id?: number;
  site?: string;
}

export async function fetchDFSProjections(
  params?: DFSFilters
): Promise<GolfDFSProjection[]> {
  const query = new URLSearchParams();
  if (params?.tournament_id != null)
    query.append("tournament_id", String(params.tournament_id));
  if (params?.site) query.append("site", params.site);
  const qs = query.toString();
  return request(`/api/golf/dfs${qs ? `?${qs}` : ""}`);
}

// ── Admin triggers ──

export async function triggerGolfSync(
  taskName: string
): Promise<TriggerTaskResponse> {
  return request("/api/admin/tasks/trigger", {
    method: "POST",
    body: JSON.stringify({ task_name: taskName, args: [] }),
  });
}
