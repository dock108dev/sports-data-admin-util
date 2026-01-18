/**
 * API client for frontend payload version endpoints.
 *
 * Frontend payloads are immutable and versioned:
 * - Each pipeline run creates a NEW version (if content changed)
 * - Previous versions are preserved forever
 * - Only one version is "active" at any time
 */

import { request } from "./client";

// =============================================================================
// TYPES
// =============================================================================

export interface PayloadVersionSummary {
  version_number: number;
  is_active: boolean;
  payload_hash: string;
  event_count: number;
  moment_count: number;
  pipeline_run_id: number | null;
  generation_source: string | null;
  created_at: string;
  diff_summary: Record<string, unknown> | null;
}

export interface PayloadVersionDetail {
  version_number: number;
  is_active: boolean;
  payload_hash: string;
  event_count: number;
  moment_count: number;
  pipeline_run_id: number | null;
  generation_source: string | null;
  generation_notes: string | null;
  created_at: string;
  diff_from_previous: Record<string, unknown> | null;
  timeline: Array<Record<string, unknown>>;
  moments: Array<Record<string, unknown>>;
  summary: Record<string, unknown>;
}

export interface GamePayloadResponse {
  game_id: number;
  game_info: Record<string, unknown> | null;
  version: PayloadVersionSummary;
  timeline: Array<Record<string, unknown>>;
  moments: Array<Record<string, unknown>>;
  summary: Record<string, unknown>;
}

export interface PayloadVersionListResponse {
  game_id: number;
  total_versions: number;
  active_version: number | null;
  versions: PayloadVersionSummary[];
}

export interface PayloadComparisonResponse {
  game_id: number;
  version_a: Record<string, unknown>;
  version_b: Record<string, unknown>;
  hashes_match: boolean;
  diff: Record<string, unknown>;
}

export interface PayloadDiagnosticsResponse {
  game_id: number;
  status?: string;
  message?: string;
  total_versions?: number;
  unique_payloads?: number;
  active_version?: number | null;
  latest_version?: number | null;
  active_payload_hash?: string | null;
  version_history?: Array<{
    version: number;
    changed: boolean;
    source: string | null;
    moment_count: number;
    event_count: number;
    created_at: string;
  }>;
  sources?: string[];
}

export interface DiffTimelineChange {
  version: number;
  created_at: string;
  source: string | null;
  pipeline_run_id: number | null;
  event_count: number;
  moment_count: number;
  diff: Record<string, unknown>;
}

export interface DiffTimelineResponse {
  game_id: number;
  total_changes: number;
  changes: DiffTimelineChange[];
}

// =============================================================================
// API FUNCTIONS
// =============================================================================

/**
 * Get the currently active frontend payload for a game.
 * This is exactly what the frontend would receive.
 */
export async function fetchActivePayload(
  gameId: number
): Promise<GamePayloadResponse> {
  return request(`/api/admin/sports/frontend-payload/game/${gameId}`);
}

/**
 * List all payload versions for a game.
 */
export async function fetchPayloadVersions(
  gameId: number,
  limit: number = 50
): Promise<PayloadVersionListResponse> {
  const params = new URLSearchParams();
  params.set("limit", limit.toString());
  return request(`/api/admin/sports/frontend-payload/game/${gameId}/versions?${params.toString()}`);
}

/**
 * Get a specific payload version by number.
 */
export async function fetchPayloadVersion(
  gameId: number,
  versionNumber: number
): Promise<PayloadVersionDetail> {
  return request(`/api/admin/sports/frontend-payload/game/${gameId}/version/${versionNumber}`);
}

/**
 * Get the payload created by a specific pipeline run.
 */
export async function fetchPayloadByPipelineRun(
  runId: number
): Promise<PayloadVersionDetail> {
  return request(`/api/admin/sports/frontend-payload/pipeline-run/${runId}`);
}

/**
 * Compare two payload versions.
 */
export async function comparePayloadVersions(
  gameId: number,
  versionA: number,
  versionB: number
): Promise<PayloadComparisonResponse> {
  const params = new URLSearchParams();
  params.set("version_a", versionA.toString());
  params.set("version_b", versionB.toString());
  return request(`/api/admin/sports/frontend-payload/game/${gameId}/compare?${params.toString()}`);
}

/**
 * Get diagnostic information about payload versions.
 */
export async function fetchPayloadDiagnostics(
  gameId: number
): Promise<PayloadDiagnosticsResponse> {
  return request(`/api/admin/sports/frontend-payload/game/${gameId}/diagnostics`);
}

/**
 * Get a timeline of all changes across versions.
 */
export async function fetchDiffTimeline(
  gameId: number
): Promise<DiffTimelineResponse> {
  return request(`/api/admin/sports/frontend-payload/game/${gameId}/diff-timeline`);
}
