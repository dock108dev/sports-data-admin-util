/**
 * API client for sports data administration endpoints.
 * 
 * Provides typed functions for interacting with the theory-engine-api
 * sports data admin endpoints, including scrape run management,
 * game listing/filtering, and game detail views.
 * 
 * All requests are made to the theory-engine-api backend configured
 * via NEXT_PUBLIC_THEORY_ENGINE_URL environment variable.
 */

function getApiBase(): string {
  const base = process.env.NEXT_PUBLIC_SPORTS_API_URL || process.env.NEXT_PUBLIC_THEORY_ENGINE_URL;
  if (!base) {
    throw new Error("Set NEXT_PUBLIC_SPORTS_API_URL (or NEXT_PUBLIC_THEORY_ENGINE_URL) to the sports-data-admin API base URL");
  }
  return base;
}

export type ScrapeRunResponse = {
  id: number;
  league_code: string;
  status: string;
  scraper_type: string;
  season: number | null;
  start_date: string | null;
  end_date: string | null;
  summary: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  requested_by: string | null;
  config: Record<string, unknown> | null;
};

export type GameSummary = {
  id: number;
  league_code: string;
  game_date: string;
  home_team: string;
  away_team: string;
  home_score: number | null;
  away_score: number | null;
  has_boxscore: boolean;
  has_player_stats: boolean;
  has_odds: boolean;
  has_social: boolean;
  social_post_count: number;
  has_required_data: boolean;
  scrape_version: number | null;
  last_scraped_at: string | null;
};

export type GameListResponse = {
  games: GameSummary[];
  total: number;
  next_offset: number | null;
  with_boxscore_count?: number;
  with_player_stats_count?: number;
  with_odds_count?: number;
  with_social_count?: number;
};

export type TeamStat = {
  team: string;
  is_home: boolean;
  stats: Record<string, any>;
  source?: string | null;
  updated_at?: string | null;
};

export type PlayerStat = {
  team: string;
  player_name: string;
  minutes: number | null;
  points: number | null;
  rebounds: number | null;
  assists: number | null;
  yards: number | null;
  touchdowns: number | null;
  raw_stats: Record<string, any>;
};

export type OddsEntry = {
  book: string;
  market_type: string;
  side: string | null;
  line: number | null;
  price: number | null;
  is_closing_line: boolean;
  observed_at: string | null;
};

export type SocialPost = {
  id: number;
  post_url: string;
  posted_at: string;
  has_video: boolean;
  team_abbreviation: string;
};

export type AdminGameDetail = {
  game: {
    id: number;
    league_code: string;
    season: number;
    season_type: string | null;
    game_date: string;
    home_team: string;
    away_team: string;
    home_score: number | null;
    away_score: number | null;
    status: string;
    scrape_version: number | null;
    last_scraped_at: string | null;
    has_boxscore: boolean;
    has_player_stats: boolean;
    has_odds: boolean;
    has_social: boolean;
    social_post_count: number;
  };
  team_stats: TeamStat[];
  player_stats: PlayerStat[];
  odds: OddsEntry[];
  social_posts: SocialPost[];
  derived_metrics: Record<string, any>;
  raw_payloads: Record<string, any>;
};

export type GameFilters = {
  leagues: string[];
  season?: number;
  team?: string;
  startDate?: string;
  endDate?: string;
  missingBoxscore?: boolean;
  missingPlayerStats?: boolean;
  missingOdds?: boolean;
  missingSocial?: boolean;
  missingAny?: boolean;
  limit?: number;
  offset?: number;
};

// EDA / modeling types

export type EDATargets = {
  winner: string | null;
  did_home_cover: boolean | null;
  did_away_cover: boolean | null;
  total_result: string | null;
  moneyline_upset: boolean | null;
  margin_of_victory: number | null;
  combined_score: number | null;
  closing_spread_home: number | null;
  closing_spread_away: number | null;
  closing_total: number | null;
};

// Feature generation types
export type GeneratedFeature = {
  name: string;
  formula: string;
  category: string;
  requires: string[];
  timing?: "pre_game" | "market_derived" | "post_game" | null;
  source?: string | null;
  group?: string | null;
  default_selected?: boolean;
};

export type TargetDefinition = {
  target_class: "stat" | "market";
  target_name: string;
  metric_type: "numeric" | "binary";
  market_type?: "spread" | "total" | "moneyline";
  side?: "home" | "away" | "over" | "under";
  odds_required?: boolean;
};

export type TriggerDefinition = {
  prob_threshold: number;
  confidence_band?: number | null;
  min_edge_vs_implied?: number | null;
};

export type ExposureControls = {
  max_bets_per_day?: number | null;
  max_bets_per_side_per_day?: number | null;
  spread_abs_min?: number | null;
  spread_abs_max?: number | null;
};

export type FeatureGenerationResponse = {
  features: GeneratedFeature[];
  summary: string;
};

export type CleaningOptions = {
  drop_if_all_null?: boolean;
  drop_if_any_null?: boolean;
  drop_if_non_numeric?: boolean;
  min_non_null_features?: number | null;
};

export type CleaningSummary = {
  raw_rows: number;
  rows_after_cleaning: number;
  dropped_null: number;
  dropped_non_numeric: number;
};

export type MicroModelRow = {
  theory_id?: string | null;
  game_id: number;
  target_name: string;
  target_value: number | string | null;
  baseline_value?: number | null;
  market_type?: string | null;
  side?: string | null;
  closing_line?: number | null;
  closing_odds?: number | null;
  implied_prob?: number | null;
  final_score_home?: number | null;
  final_score_away?: number | null;
  outcome?: string | null;
  pnl_units?: number | null;
  est_ev_pct?: number | null;
  model_prob?: number | null;
  edge_vs_implied?: number | null;
  trigger_flag: boolean;
  features?: Record<string, any> | null;
  meta?: Record<string, any> | null;
};

export type TheoryMetrics = {
  sample_size: number;
  cover_rate: number;
  baseline_cover_rate?: number | null;
  delta_cover?: number | null;
  ev_vs_implied?: number | null;
  sharpe_like?: number | null;
  max_drawdown?: number | null;
  time_stability?: number | null;
};

export type TheoryEvaluation = {
  target_class: "stat" | "market";
  sample_size: number;
  cohort_value?: number | null;
  baseline_value?: number | null;
  delta_value?: number | null;
  cohort_std?: number | null;
  cohort_min?: number | null;
  cohort_max?: number | null;
  p25?: number | null;
  p75?: number | null;
  implied_rate?: number | null;
  roi_units?: number | null;
  formatting: "numeric" | "percent";
  notes?: string[] | null;
  stability_by_season?: Record<string, number> | null;
  stability_by_month?: Record<string, number> | null;
  verdict?: string | null;
};

export type MetaInfo = {
  run_id: string;
  snapshot_hash?: string | null;
  created_at?: string | null;
  engine_version?: string | null;
};

export type TheoryDescriptor = {
  target: Record<string, any>;
  filters: Record<string, any>;
};

export type CohortInfo = {
  sample_size: number;
  time_span?: Record<string, any> | null;
  baseline_definition?: Record<string, any> | null;
  odds_coverage_pct?: number | null;
};

export type ModelingStatus = {
  available: boolean;
  has_run: boolean;
  reason_not_run?: string | null;
  reason_not_available?: string | null;
  eligibility?: Record<string, any> | null;
  model_type?: string | null;
  metrics?: Record<string, any> | null;
  feature_importance?: Array<Record<string, any>> | null;
};

export type MonteCarloStatus = {
  available: boolean;
  has_run: boolean;
  reason_not_run?: string | null;
  reason_not_available?: string | null;
  eligibility?: Record<string, any> | null;
  results?: Record<string, any> | null;
};

export type McSummary = {
  runs: number;
  mean_pnl: number;
  p5_pnl: number;
  p50_pnl?: number;
  p95_pnl: number;
  actual_pnl: number;
  luck_score: number;
  mean_max_drawdown?: number;
  actual_max_drawdown?: number;
};

export type FeatureQualityStats = {
  nulls: number;
  null_pct: number;
  non_numeric: number;
  distinct_count: number;
  count: number;
  min: number | null;
  max: number | null;
  mean: number | null;
};

export type DataQualitySummary = {
  rows_inspected: number;
  feature_stats: Record<string, FeatureQualityStats>;
};

export type PreviewRequest = {
  league_code: string;
  features: GeneratedFeature[];
  seasons?: number[];
  season_windows?: { season: number; start_date?: string; end_date?: string }[]; // deprecated, not used for NCAAB
  start_date?: string;
  end_date?: string;
  phase?: "all" | "out_conf" | "conf" | "postseason";
  recent_days?: number;
  team?: string;
  player?: string;
  home_spread_min?: number;
  home_spread_max?: number;
  conference_only?: boolean; // ignored for NCAAB
  limit?: number | null;
  offset?: number | null;
  include_target?: boolean;
  context?: "deployable" | "diagnostic";
  target_definition: TargetDefinition;
  sort_by?: "null_pct" | "non_numeric" | "name";
  sort_dir?: "asc" | "desc";
  feature_filter?: string[];
};

export type CorrelationResult = {
  feature: string;
  correlation: number;
  p_value?: number | null;
  is_significant?: boolean;
};

export type SegmentResult = {
  condition: string;
  sample_size: number;
  hit_rate: number;
  baseline_rate: number;
  edge: number;
};

export type AnalysisRequest = {
  league_code: string;
  features?: GeneratedFeature[] | null;
  target_definition: TargetDefinition;
  seasons?: number[];
  season_windows?: { season: number; start_date?: string; end_date?: string }[]; // deprecated, not used for NCAAB
  start_date?: string;
  end_date?: string;
  phase?: "all" | "out_conf" | "conf" | "postseason";
  recent_days?: number;
  team?: string;
  player?: string;
  home_spread_min?: number;
  home_spread_max?: number;
  conference_only?: boolean; // ignored for NCAAB
  cleaning?: CleaningOptions;
  context?: "deployable" | "diagnostic";
};

export type AnalysisResponse = {
  sample_size: number;
  baseline_value: number;
  correlations: CorrelationResult[];
  best_segments: SegmentResult[];
  insights: string[];
  cleaning_summary?: CleaningSummary | null;
  micro_rows?: MicroModelRow[] | null;
  theory_metrics?: TheoryMetrics | null;
  evaluation?: TheoryEvaluation | null;
  meta?: MetaInfo | null;
  theory?: TheoryDescriptor | null;
  cohort?: CohortInfo | null;
  modeling?: ModelingStatus | null;
  monte_carlo?: MonteCarloStatus | null;
  notes?: string[] | null;
  feature_policy?: Record<string, any> | null;
  run_id?: string | null;
  detected_concepts?: string[] | null;
  concept_derived_fields?: string[] | null;
};

export type AddFeaturesRequest = {
  features: GeneratedFeature[];
  feature_mode?: string | null;
  context?: "deployable" | "diagnostic";
  cleaning?: CleaningOptions | null;
};

export type TrainedModelResponse = {
  model_type: string;
  features_used: string[];
  feature_weights: Record<string, number>;
  accuracy: number;
  roi: number;
};

export type SuggestedTheoryResponse = {
  text: string;
  features_used: string[];
  historical_edge: number;
  confidence: string;
};

export type ModelBuildResponse = {
  model_summary: TrainedModelResponse;
  suggested_theories: SuggestedTheoryResponse[];
  validation_stats: Record<string, number>;
  cleaning_summary?: CleaningSummary | null;
  micro_rows?: MicroModelRow[] | null;
  theory_metrics?: TheoryMetrics | null;
  mc_summary?: McSummary | null;
  evaluation?: TheoryEvaluation | null;
  meta?: MetaInfo | null;
  theory?: TheoryDescriptor | null;
  cohort?: CohortInfo | null;
  modeling?: ModelingStatus | null;
  monte_carlo?: MonteCarloStatus | null;
  notes?: string[] | null;
  feature_policy?: Record<string, any> | null;
  features_dropped?: Array<Record<string, any>> | null;
  exposure_summary?: Record<string, any> | null;
  bet_tape?: Array<Record<string, any>> | null;
  performance_slices?: Record<string, any> | null;
  failure_analysis?: Record<string, any> | null;
  mc_assumptions?: Record<string, any> | null;
  mc_interpretation?: string[] | null;
  theory_candidates?: Array<Record<string, any>> | null;
  model_snapshot?: Record<string, any> | null;
};

export type AnalysisRunSummary = {
  run_id: string;
  created_at?: string | null;
  target_name?: string | null;
  target_class?: string | null;
  run_type?: string | null;
  micro_rows_ref?: string | null;
  cohort_size?: number | null;
  snapshot_hash?: string | null;
};

export type AnalysisRunDetail = {
  run_id: string;
  created_at?: string | null;
  request?: Record<string, any> | null;
  target?: Record<string, any> | null;
  evaluation?: Record<string, any> | null;
  modeling?: Record<string, any> | null;
  monte_carlo?: Record<string, any> | null;
  mc_summary?: Record<string, any> | null;
  model_snapshot?: Record<string, any> | null;
  micro_rows_ref?: string | null;
  micro_rows_sample?: Array<Record<string, any>> | null;
  run_type?: string | null;
  cohort_size?: number | null;
  snapshot_hash?: string | null;
};

export type WalkforwardSlice = {
  start_date?: string | null;
  end_date?: string | null;
  sample_size: number;
  hit_rate?: number | null;
  roi_units?: number | null;
  edge_avg?: number | null;
  odds_coverage_pct?: number | null;
};

export type WalkforwardRequest = {
  league_code: string;
  features: GeneratedFeature[];
  target_definition: TargetDefinition;
  seasons?: number[];
  start_date?: string;
  end_date?: string;
  phase?: "all" | "out_conf" | "conf" | "postseason";
  recent_days?: number;
  team?: string;
  player?: string;
  home_spread_min?: number;
  home_spread_max?: number;
  games_limit?: number;
  cleaning?: CleaningOptions;
  feature_mode?: "deployable" | "diagnostic" | "admin" | "full";
  context?: "deployable" | "diagnostic";
  window?: {
    train_days: number;
    test_days: number;
    step_days: number;
  };
};

export type WalkforwardResponse = {
  run_id: string;
  slices: WalkforwardSlice[];
  edge_half_life_days?: number | null;
  predictions_ref?: string | null;
  notes?: string[] | null;
};

export type ModelBuildRequest = {
  league_code: string;
  features: GeneratedFeature[];
  target_definition: TargetDefinition;
  trigger_definition?: TriggerDefinition | null;
  exposure_controls?: ExposureControls | null;
  seasons?: number[];
  season_windows?: { season: number; start_date?: string; end_date?: string }[]; // deprecated, not used for NCAAB
  start_date?: string;
  end_date?: string;
  phase?: "all" | "out_conf" | "conf" | "postseason";
  recent_days?: number;
  team?: string;
  player?: string;
  home_spread_min?: number;
  home_spread_max?: number;
  conference_only?: boolean; // ignored for NCAAB
  cleaning?: CleaningOptions;
  context?: "deployable" | "diagnostic";
};

export async function downloadAnalysisCsv(req: AnalysisRequest): Promise<Blob> {
  const apiBase = getApiBase();
  const res = await fetch(`${apiBase}/api/admin/sports/eda/analyze/export`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(req),
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Download failed (${res.status}): ${body}`);
  }
  return await res.blob();
}

export async function downloadMicroModelCsv(req: AnalysisRequest): Promise<Blob> {
  const apiBase = getApiBase();
  const res = await fetch(`${apiBase}/api/admin/sports/eda/micro-model/export`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(req),
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Micro-model download failed (${res.status}): ${body}`);
  }
  return await res.blob();
}

export async function fetchAnalysisRuns(): Promise<AnalysisRunSummary[]> {
  return request(`/api/admin/sports/eda/analysis-runs`);
}

export async function fetchAnalysisRun(runId: string): Promise<AnalysisRunDetail> {
  return request(`/api/admin/sports/eda/analysis-runs/${runId}`);
}

export async function runWalkforward(payload: WalkforwardRequest): Promise<WalkforwardResponse> {
  return request(`/api/admin/sports/eda/walkforward`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function downloadPreviewCsv(payload: PreviewRequest): Promise<Blob> {
  const apiBase = getApiBase();
  const res = await fetch(`${apiBase}/api/admin/sports/eda/preview`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ ...payload, format: "csv" }),
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Preview download failed (${res.status}): ${body}`);
  }
  return await res.blob();
}

export async function fetchDataQuality(payload: PreviewRequest): Promise<DataQualitySummary> {
  return request(`/api/admin/sports/eda/preview`, {
    method: "POST",
    body: JSON.stringify({ ...payload, format: "json" }),
  });
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const apiBase = getApiBase();
  const url = `${apiBase}${path}`;
  
  try {
    const res = await fetch(url, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(init?.headers ?? {}),
      },
      cache: "no-store",
    });

    if (!res.ok) {
      const body = await res.text();
      throw new Error(`Request failed (${res.status}): ${body}`);
    }
    
    return await res.json();
  } catch (err) {
    if (err instanceof TypeError && err.message.includes("fetch")) {
      throw new Error(`Failed to connect to backend at ${apiBase}. Is the server running?`);
    }
    throw err;
  }
}

export async function createScrapeRun(payload: {
  requestedBy?: string;
  config: {
    leagueCode: string;
    scraperType?: string;
    season?: number;
    seasonType?: string;
    startDate?: string;
    endDate?: string;
    includeBoxscores?: boolean;
    includeOdds?: boolean;
    includeSocial?: boolean;
    backfillPlayerStats?: boolean;
    backfillOdds?: boolean;
    backfillSocial?: boolean;
    books?: string[];
  };
}): Promise<ScrapeRunResponse> {
  return request("/api/admin/sports/scraper/runs", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function listScrapeRuns(params?: { league?: string; status?: string }): Promise<ScrapeRunResponse[]> {
  const query = new URLSearchParams();
  if (params?.league) query.append("league", params.league);
  if (params?.status) query.append("status", params.status);
  const qs = query.toString();
  return request(`/api/admin/sports/scraper/runs${qs ? `?${qs}` : ""}`);
}

export async function fetchScrapeRun(runId: number): Promise<ScrapeRunResponse> {
  return request(`/api/admin/sports/scraper/runs/${runId}`);
}

export async function cancelScrapeRun(runId: number): Promise<ScrapeRunResponse> {
  return request(`/api/admin/sports/scraper/runs/${runId}/cancel`, {
    method: "POST",
  });
}

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
  if (filters?.missingAny) query.append("missingAny", "true");
  if (typeof filters?.limit === "number") query.append("limit", String(filters.limit));
  if (typeof filters?.offset === "number") query.append("offset", String(filters.offset));
  const qs = query.toString();
  return request(`/api/admin/sports/games${qs ? `?${qs}` : ""}`);
}


export async function generateFeatures(payload: {
  league_code: string;
  raw_stats: string[];
  include_rest_days?: boolean;
  include_rolling?: boolean;
  rolling_window?: number;
}): Promise<FeatureGenerationResponse> {
  return request(`/api/admin/sports/eda/generate-features`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function runAnalysis(payload: AnalysisRequest): Promise<AnalysisResponse> {
  return request(`/api/admin/sports/eda/analyze`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function addExplanatoryFeatures(runId: string, payload: AddFeaturesRequest): Promise<AnalysisResponse> {
  return request(`/api/admin/sports/eda/analysis-runs/${runId}/add-features`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function buildModel(payload: ModelBuildRequest): Promise<ModelBuildResponse> {
  return request(`/api/admin/sports/eda/build-model`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function fetchGame(gameId: number | string): Promise<AdminGameDetail> {
  const idStr = String(gameId);
  if (!/^\d+$/.test(idStr)) {
    throw new Error(`Invalid game id: ${idStr}`);
  }
  return request(`/api/admin/sports/games/${idStr}`);
}

export async function rescrapeGame(gameId: number): Promise<{ run_id: number; job_id: string | null; message: string }> {
  return request(`/api/admin/sports/games/${gameId}/rescrape`, { method: "POST" });
}

export async function resyncOdds(gameId: number): Promise<{ run_id: number; job_id: string | null; message: string }> {
  return request(`/api/admin/sports/games/${gameId}/resync-odds`, { method: "POST" });
}

// Teams API

export type TeamSummary = {
  id: number;
  name: string;
  shortName: string;
  abbreviation: string;
  leagueCode: string;
  gamesCount: number;
};

export type TeamListResponse = {
  teams: TeamSummary[];
  total: number;
};

export type TeamGameSummary = {
  id: number;
  gameDate: string;
  opponent: string;
  isHome: boolean;
  score: string;
  result: string;
};

export type TeamDetail = {
  id: number;
  name: string;
  shortName: string;
  abbreviation: string;
  leagueCode: string;
  location: string | null;
  externalRef: string | null;
  recentGames: TeamGameSummary[];
};

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

// Stat keys API for EDA multi-select

export type AvailableStatKeysResponse = {
  league_code: string;
  team_stat_keys: string[];
  player_stat_keys: string[];
};

export async function fetchStatKeys(leagueCode: string): Promise<AvailableStatKeysResponse> {
  return request(`/api/admin/sports/eda/stat-keys/${leagueCode}`);
}


