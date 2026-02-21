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
