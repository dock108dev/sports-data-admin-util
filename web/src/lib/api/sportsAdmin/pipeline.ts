import { request } from "./client";

export interface PipelineStageStatus {
  stage_name: string;
  status: "pending" | "in_progress" | "completed" | "failed" | "skipped";
  started_at: string | null;
  completed_at: string | null;
  error_message: string | null;
  output_summary: string | null;
}

export interface PipelineRunSummary {
  run_id: number;
  run_uuid: string;
  game_id: number;
  status: "pending" | "in_progress" | "completed" | "failed";
  auto_chain: boolean;
  triggered_by: string;
  started_at: string;
  completed_at: string | null;
  stages: PipelineStageStatus[];
  current_stage: string | null;
  next_stage: string | null;
}

export interface RunFullPipelineResponse {
  run_id: number;
  run_uuid: string;
  game_id: number;
  status: string;
  stages: PipelineStageStatus[];
  message: string;
  flow_saved: boolean;
  word_count: number | null;
  moment_count: number | null;
}

export interface GamePipelineSummary {
  game_id: number;
  game_date: string;
  league: string;
  home_team: string;
  away_team: string;
  status: string;
  has_pbp: boolean;
  has_flow: boolean;
  latest_run: PipelineRunSummary | null;
  total_runs: number;
}

export interface GamePipelineRunsResponse {
  game_id: number;
  total_runs: number;
  runs: PipelineRunSummary[];
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
  return request(`/api/admin/sports/pipeline/${gameId}/runs`);
}

export async function getPipelineRun(
  runId: number
): Promise<PipelineRunSummary> {
  return request(`/api/admin/sports/pipeline/runs/${runId}`);
}

export async function getGamePipelineSummary(
  gameId: number
): Promise<GamePipelineSummary> {
  return request(`/api/admin/sports/pipeline/${gameId}/summary`);
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
