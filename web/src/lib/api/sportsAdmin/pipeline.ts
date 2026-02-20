import { request } from "./client";

export interface PipelineStageStatus {
  stage: string;
  stage_order: number;
  status: "pending" | "running" | "success" | "failed" | "skipped";
  started_at: string | null;
  finished_at: string | null;
  duration_seconds: number | null;
  error_details: string | null;
  has_output: boolean;
  output_summary: Record<string, unknown> | null;
  log_count: number;
  can_execute: boolean;
}

export interface PipelineRunSummary {
  run_id: number;
  run_uuid: string;
  game_id: number;
  triggered_by: string;
  status: "pending" | "running" | "completed" | "failed" | "paused";
  current_stage: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  stages_completed: number;
  stages_total: number;
  progress_percent: number;
  stages: PipelineStageStatus[];
}

export interface RunFullPipelineResponse {
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

export interface GamePipelineSummary {
  game_id: number;
  game_date: string;
  home_team: string;
  away_team: string;
  game_status: string;
  has_pbp: boolean;
  has_timeline_artifact: boolean;
  latest_artifact_at: string | null;
  total_pipeline_runs: number;
  latest_run: PipelineRunSummary | null;
  can_run_pipeline: boolean;
}

export interface GamePipelineRunsResponse {
  game_id: number;
  game_info: Record<string, unknown>;
  runs: PipelineRunSummary[];
  total_runs: number;
  has_successful_run: boolean;
  latest_artifact_at: string | null;
}

export async function runFullPipeline(
  gameId: number,
  triggeredBy: string = "admin_ui"
): Promise<RunFullPipelineResponse> {
  return request(`/api/admin/sports/pipeline/${gameId}/run-full`, {
    method: "POST",
    body: JSON.stringify({
      triggered_by: triggeredBy,
    }),
  });
}

export async function getPipelineRuns(
  gameId: number
): Promise<GamePipelineRunsResponse> {
  return request(`/api/admin/sports/pipeline/game/${gameId}`);
}

export async function getPipelineRun(
  runId: number
): Promise<PipelineRunSummary> {
  return request(`/api/admin/sports/pipeline/run/${runId}`);
}

export async function getGamePipelineSummary(
  gameId: number
): Promise<GamePipelineSummary> {
  return request(`/api/admin/sports/pipeline/game/${gameId}/summary`);
}

// Bulk generation types
export interface BulkGenerateRequest {
  start_date: string;
  end_date: string;
  leagues: string[];
  force: boolean;
}

export interface BulkGenerateAsyncResponse {
  job_id: string;
  message: string;
  status_url: string;
}

export interface BulkGenerateStatusResponse {
  job_id: string;
  state: "PENDING" | "PROGRESS" | "SUCCESS" | "FAILURE";
  current: number;
  total: number;
  successful: number;
  failed: number;
  skipped: number;
  result: {
    total: number;
    successful: number;
    failed: number;
    skipped: number;
    errors: Array<{ game_id: number; error: string }>;
  } | null;
}

export async function bulkGenerateStoriesAsync(
  params: BulkGenerateRequest
): Promise<BulkGenerateAsyncResponse> {
  return request(`/api/admin/sports/pipeline/bulk-generate-async`, {
    method: "POST",
    body: JSON.stringify(params),
  });
}

export async function getBulkGenerateStatus(
  jobId: string
): Promise<BulkGenerateStatusResponse> {
  return request(`/api/admin/sports/pipeline/bulk-generate-status/${jobId}`);
}
