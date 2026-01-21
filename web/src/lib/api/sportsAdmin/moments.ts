/**
 * API client for moment trace and explainability endpoints.
 *
 * These endpoints provide full visibility into how moments are generated,
 * including construction traces, rejected moments, merged moments, and signals.
 */

import { request } from "./client";

// =============================================================================
// TYPES
// =============================================================================

export interface MomentTraceSummary {
  moment_id: string;
  moment_type: string;
  trigger_type: string;
  trigger_description: string;
  play_range: string;
  play_count: number;
  is_final: boolean;
  was_rejected: boolean;
  was_merged: boolean;
  validation_passed: boolean;
  issues: string[];
}

export interface MomentTraceDetail {
  moment_id: string;
  moment_type: string;
  input_start_idx: number;
  input_end_idx: number;
  play_count: number;
  trigger_type: string;
  trigger_description: string;
  signals: Record<string, unknown>;
  validation: Record<string, unknown>;
  actions: Array<Record<string, unknown>>;
  is_final: boolean;
  final_moment_id: string | null;
  rejection_reason: string | null;
  merged_into_id: string | null;
  absorbed_moment_ids: string[];
  created_at: string;
  // Phase 2-4: Context fields
  phase_state?: Record<string, unknown>;
  narrative_context?: Record<string, unknown>;
}

export interface GenerationTraceSummary {
  game_id: number;
  pipeline_run_id: number | null;
  pbp_event_count: number;
  thresholds: number[];
  budget: number;
  sport: string;
  initial_moment_count: number;
  rejected_count: number;
  merged_count: number;
  final_moment_count: number;
  rejected_moment_ids: string[];
  merged_moment_ids: string[];
  final_moment_ids: Array<string | null>;
}

export interface GenerationTraceResponse {
  run_id: number;
  run_uuid: string;
  game_id: number;
  summary: GenerationTraceSummary;
  moment_traces: MomentTraceDetail[] | null;
}

export interface MomentExplainerResponse {
  moment_id: string;
  moment_type: string;
  explanation: string;
  trigger: Record<string, unknown>;
  signals_summary: string;
  validation_summary: string;
  play_range_summary: string;
}

export interface RejectedMoment {
  moment_id: string;
  moment_type: string;
  rejection_reason: string;
  play_range: string;
  play_count: number;
  trigger_type: string;
}

export interface RejectedMomentsResponse {
  run_id: number;
  game_id: number;
  rejected_moments: RejectedMoment[];
  total_count: number;
}

export interface MergedMoment {
  original_id: string;
  merged_into_id: string;
  moment_type: string;
  play_range: string;
  play_count: number;
  merge_reason: string;
}

export interface MergedMomentsResponse {
  run_id: number;
  game_id: number;
  merged_moments: MergedMoment[];
  total_count: number;
}

// LatestTraceResponse is the same as GenerationTraceResponse
export type LatestTraceResponse = GenerationTraceResponse;

// =============================================================================
// API FUNCTIONS
// =============================================================================

/**
 * Get full generation trace for a pipeline run.
 */
export async function fetchGenerationTrace(
  runId: number,
  includeFullTraces: boolean = true
): Promise<GenerationTraceResponse> {
  const params = new URLSearchParams();
  if (includeFullTraces) params.set("include_traces", "true");
  return request(`/api/admin/sports/moments/pipeline-run/${runId}/trace?${params.toString()}`);
}

/**
 * Get detailed trace for a specific moment.
 */
export async function fetchMomentTrace(
  runId: number,
  momentId: string
): Promise<MomentTraceDetail> {
  return request(`/api/admin/sports/moments/pipeline-run/${runId}/trace/${momentId}`);
}

/**
 * Get human-readable explanation for a moment.
 */
export async function fetchMomentExplain(
  runId: number,
  momentId: string
): Promise<MomentExplainerResponse> {
  return request(`/api/admin/sports/moments/pipeline-run/${runId}/trace/${momentId}/explain`);
}

/**
 * List rejected moments from a pipeline run.
 */
export async function fetchRejectedMoments(
  runId: number
): Promise<RejectedMomentsResponse> {
  return request(`/api/admin/sports/moments/pipeline-run/${runId}/rejected`);
}

/**
 * List merged moments from a pipeline run.
 */
export async function fetchMergedMoments(
  runId: number
): Promise<MergedMomentsResponse> {
  return request(`/api/admin/sports/moments/pipeline-run/${runId}/merged`);
}

/**
 * Get the latest moment trace for a game (from most recent pipeline run).
 */
export async function fetchLatestMomentTrace(
  gameId: number
): Promise<LatestTraceResponse> {
  return request(`/api/admin/sports/moments/game/${gameId}/latest-trace`);
}

// =============================================================================
// PIPELINE FUNCTIONS
// =============================================================================

export interface RunPipelineResponse {
  run_id: number;
  run_uuid: string;
  game_id: number;
  status: string;
  stages_completed: number;
  stages_failed: number;
  duration_seconds: number | null;
  artifact_id: number | null;
  message: string;
}

export interface BatchPipelineResponse {
  total: number;
  successful: number;
  failed: number;
  failed_game_ids: number[];
  results: RunPipelineResponse[];
}

/**
 * Run the full pipeline for a single game.
 * Creates pipeline run, traces, and payload version.
 */
export async function runPipeline(
  gameId: number,
  triggeredBy: string = "admin_ui"
): Promise<RunPipelineResponse> {
  return request(`/api/admin/sports/pipeline/${gameId}/run-full`, {
    method: "POST",
    body: JSON.stringify({ triggered_by: triggeredBy }),
  });
}

/**
 * Run pipeline for multiple games.
 */
export async function runPipelineBatch(
  gameIds: number[],
  triggeredBy: string = "admin_ui"
): Promise<BatchPipelineResponse> {
  const results: RunPipelineResponse[] = [];
  const failed: number[] = [];
  let successful = 0;

  for (const gameId of gameIds) {
    try {
      const result = await runPipeline(gameId, triggeredBy);
      results.push(result);
      if (result.status === "completed") {
        successful++;
      } else {
        failed.push(gameId);
      }
    } catch {
      failed.push(gameId);
    }
  }

  return {
    total: gameIds.length,
    successful,
    failed: failed.length,
    failed_game_ids: failed,
    results,
  };
}
