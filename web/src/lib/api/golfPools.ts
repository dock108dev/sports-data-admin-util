/** API client functions for golf pool endpoints. */

import { request } from "./sportsAdmin/client";
import type {
  GolfPool,
  GolfPoolEntry,
  GolfPoolLeaderboardEntry,
} from "./golfPoolTypes";
import type { GolfFieldEntry } from "./golfTypes";
import type { TriggerTaskResponse } from "./sportsAdmin/taskControl";

// ── Pool listing ──

export interface PoolFilters {
  club_code?: string;
  status?: string;
  limit?: number;
}

export async function listPools(
  params?: PoolFilters
): Promise<GolfPool[]> {
  const query = new URLSearchParams();
  if (params?.club_code) query.append("club_code", params.club_code);
  if (params?.status) query.append("status", params.status);
  if (params?.limit != null) query.append("limit", String(params.limit));
  const qs = query.toString();
  return request(`/api/golf/pools${qs ? `?${qs}` : ""}`);
}

// ── Pool detail ──

export async function fetchPool(poolId: number | string): Promise<GolfPool> {
  return request(`/api/golf/pools/${poolId}`);
}

// ── Pool field (available golfers) ──

export async function fetchPoolField(
  poolId: number | string
): Promise<GolfFieldEntry[]> {
  return request(`/api/golf/pools/${poolId}/field`);
}

// ── Pool leaderboard (materialized scores) ──

export async function fetchPoolLeaderboard(
  poolId: number | string
): Promise<GolfPoolLeaderboardEntry[]> {
  return request(`/api/golf/pools/${poolId}/leaderboard`);
}

// ── Pool entries ──

export async function fetchPoolEntries(
  poolId: number | string
): Promise<GolfPoolEntry[]> {
  return request(`/api/golf/pools/${poolId}/entries`);
}

// ── Submit entry ──

export interface SubmitEntryPayload {
  email: string;
  entry_name?: string;
  picks: { dg_id: number; player_name: string; pick_slot: number; bucket_number?: number }[];
}

export async function submitPoolEntry(
  poolId: number | string,
  payload: SubmitEntryPayload
): Promise<GolfPoolEntry> {
  return request(`/api/golf/pools/${poolId}/entries`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

// ── Create pool ──

export interface CreatePoolPayload {
  name: string;
  club_code: string;
  tournament_id: number;
  entry_deadline?: string;
  max_entries_per_email?: number;
  rules?: Record<string, unknown>;
}

export async function createPool(
  payload: CreatePoolPayload
): Promise<GolfPool> {
  return request("/api/golf/pools", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

// ── Admin operations ──

export async function rescorePool(
  poolId: number | string
): Promise<TriggerTaskResponse> {
  return request(`/api/golf/pools/${poolId}/rescore`, {
    method: "POST",
  });
}

export async function lockPool(
  poolId: number | string
): Promise<GolfPool> {
  return request(`/api/golf/pools/${poolId}/lock`, {
    method: "POST",
  });
}
