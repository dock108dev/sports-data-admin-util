/**
 * TheoryDraft types - the canonical shape for theory definitions.
 *
 * This is the single source of truth for theory configuration.
 * UI emits this shape, backend persists this shape.
 */

import { getApiBase as resolveApiBase } from "./apiBase";

// -----------------------------------------------------------------------------
// Time Window
// -----------------------------------------------------------------------------

export type TimeWindowMode =
  | "current_season"
  | "last_30"
  | "last_60"
  | "last_n"
  | "custom"
  | "specific_seasons";

export interface TimeWindow {
  mode: TimeWindowMode;
  value?: number | number[] | null; // days for last_n, season list for specific_seasons
  start_date?: string | null; // ISO date for custom
  end_date?: string | null; // ISO date for custom
}

// -----------------------------------------------------------------------------
// Target
// -----------------------------------------------------------------------------

export type TargetType =
  | "game_total"
  | "spread_result"
  | "moneyline_win"
  | "team_stat"
  | "forward_return"
  | "direction"
  | "threshold_cross"
  | "volatility_bucket";
export type TargetMetric = "numeric" | "binary" | "categorical";
export type TargetSide = "home" | "away" | "over" | "under";

export interface Target {
  type: TargetType;
  stat?: string | null; // e.g. "combined_score", "turnovers"
  metric: TargetMetric;
  side?: TargetSide | null;
  horizon_hours?: number | null;
  threshold_value?: number | null;
  bucket_edges?: number[] | null;
  quote?: string | null;
}

// -----------------------------------------------------------------------------
// Inputs
// -----------------------------------------------------------------------------

export type FeaturePolicy = "auto" | "manual";

export interface Inputs {
  base_stats: string[];
  feature_policy: FeaturePolicy;
}

// -----------------------------------------------------------------------------
// Context Features
// -----------------------------------------------------------------------------

export interface ContextFeatures {
  game: string[]; // conference_game, rest_days, pace
  market: string[]; // closing_spread, closing_total, implied_prob
  team: string[]; // rating_diff, projections
  player: string[]; // player_minutes, player_minutes_rolling
  diagnostic: string[]; // cover_margin, total_delta (post-game leaky)
}

export type ContextPreset =
  | "minimal"
  | "standard"
  | "market_aware"
  | "player_aware"
  | "verbose"
  | "custom";

export interface Context {
  preset: ContextPreset;
  features: ContextFeatures;
}

// -----------------------------------------------------------------------------
// Filters
// -----------------------------------------------------------------------------

export type Phase = "all" | "out_conf" | "conf" | "postseason";
export type MarketType = "spread" | "total" | "moneyline";

export interface Filters {
  team?: string | null;
  player?: string | null;
  phase?: Phase | null;
  market_type?: MarketType | null;
  season_type?: string | null;
  spread_abs_min?: number | null;
  spread_abs_max?: number | null;
  // Domain-aware filters
  exchange?: string | null;
  assets?: string[] | null;
  quote?: string | null;
  timeframe?: string | null;
}

// -----------------------------------------------------------------------------
// Model Configuration
// -----------------------------------------------------------------------------

export interface ModelConfig {
  enabled: boolean;
  prob_threshold: number;
  confidence_band?: number | null;
  min_edge_vs_implied?: number | null;
}

// -----------------------------------------------------------------------------
// Exposure Controls
// -----------------------------------------------------------------------------

export type ExposureRanking = "edge" | "prob" | "ev";

export interface ExposureConfig {
  max_bets_per_day?: number | null;
  max_per_side_per_day?: number | null;
  spread_abs_min?: number | null;
  spread_abs_max?: number | null;
  ranking: ExposureRanking;
}

// -----------------------------------------------------------------------------
// Results Configuration
// -----------------------------------------------------------------------------

export interface ResultsConfig {
  columns: string[];
  include_team_stats: string[];
  include_player_stats: string[];
}

// -----------------------------------------------------------------------------
// Diagnostics
// -----------------------------------------------------------------------------

export interface DiagnosticsConfig {
  allow_post_game_features: boolean;
}

// -----------------------------------------------------------------------------
// Cohort Rule - REQUIRED: defines what games are "in the cohort"
// -----------------------------------------------------------------------------

export type CohortRuleMode = "auto" | "quantile" | "threshold";

export interface QuantileRule {
  stat: string; // e.g. "turnovers_diff"
  direction: "top" | "bottom"; // top 20% or bottom 20%
  percentile: number; // 10, 20, 25, etc.
}

export interface ThresholdRule {
  stat: string; // e.g. "turnovers_diff"
  operator: ">=" | "<=" | ">" | "<" | "=";
  value: number;
}

export interface CohortRule {
  mode: CohortRuleMode;
  // For quantile mode
  quantile_rules?: QuantileRule[];
  // For threshold mode
  threshold_rules?: ThresholdRule[];
  // For auto mode - backend will populate this after discovery
  discovered_rule?: string | null;
}

// -----------------------------------------------------------------------------
// Main TheoryDraft
// -----------------------------------------------------------------------------

export type DomainType = "bets" | "crypto" | "stocks" | "conspiracies" | "playlist";

export interface Scope {
  league?: string | null;
  seasons?: number[] | null;
  exchange?: string | null;
  assets?: string[] | null;
  quote?: string | null;
  timeframe?: string | null;
}

export interface TheoryDraft {
  theory_id: string;
  domain: DomainType;
  league: string;
  scope?: Scope | null;
  time_window: TimeWindow;
  target: Target;
  inputs: Inputs;
  cohort_rule: CohortRule; // REQUIRED: how we decide what games are in the cohort
  context: Context;
  filters: Filters;
  model: ModelConfig;
  exposure: ExposureConfig;
  results: ResultsConfig;
  diagnostics: DiagnosticsConfig;
}

// -----------------------------------------------------------------------------
// Default Values
// -----------------------------------------------------------------------------

export const DEFAULT_TIME_WINDOW: TimeWindow = {
  mode: "current_season",
  value: null,
};

export const DEFAULT_TARGET: Target = {
  type: "game_total",
  stat: "combined_score",
  metric: "numeric",
  side: null,
};

export const DEFAULT_INPUTS: Inputs = {
  base_stats: [],
  feature_policy: "auto",
};

export const DEFAULT_CONTEXT_FEATURES: ContextFeatures = {
  game: [],
  market: [],
  team: [],
  player: [],
  diagnostic: [],
};

export const DEFAULT_CONTEXT: Context = {
  preset: "minimal",
  features: DEFAULT_CONTEXT_FEATURES,
};

export const DEFAULT_FILTERS: Filters = {
  team: null,
  player: null,
  phase: null,
  market_type: null,
  season_type: null,
  spread_abs_min: null,
  spread_abs_max: null,
  exchange: null,
  assets: null,
  quote: null,
  timeframe: null,
};

export const DEFAULT_MODEL_CONFIG: ModelConfig = {
  enabled: false,
  prob_threshold: 0.55,
  confidence_band: null,
  min_edge_vs_implied: null,
};

export const DEFAULT_EXPOSURE_CONFIG: ExposureConfig = {
  max_bets_per_day: 5,
  max_per_side_per_day: null,
  spread_abs_min: null,
  spread_abs_max: null,
  ranking: "edge",
};

export const DEFAULT_RESULTS_CONFIG: ResultsConfig = {
  columns: [],
  include_team_stats: [],
  include_player_stats: [],
};

export const DEFAULT_DIAGNOSTICS_CONFIG: DiagnosticsConfig = {
  allow_post_game_features: false,
};

export const DEFAULT_COHORT_RULE: CohortRule = {
  mode: "auto",
  quantile_rules: [],
  threshold_rules: [],
  discovered_rule: null,
};

export function createDefaultTheoryDraft(
  league: string = "NBA",
  domain: DomainType = "bets",
  scope?: Scope
): TheoryDraft {
  const effectiveScope =
    scope ??
    (domain === "bets"
      ? { league }
      : undefined);

  return {
    theory_id: "auto",
    domain,
    league: domain === "bets" ? league : "",
    scope: effectiveScope,
    time_window: { ...DEFAULT_TIME_WINDOW },
    target: { ...DEFAULT_TARGET },
    inputs: { ...DEFAULT_INPUTS, base_stats: [] },
    cohort_rule: { ...DEFAULT_COHORT_RULE },
    context: { ...DEFAULT_CONTEXT, features: { ...DEFAULT_CONTEXT_FEATURES } },
    filters: { ...DEFAULT_FILTERS },
    model: { ...DEFAULT_MODEL_CONFIG },
    exposure: { ...DEFAULT_EXPOSURE_CONFIG },
    results: { ...DEFAULT_RESULTS_CONFIG },
    diagnostics: { ...DEFAULT_DIAGNOSTICS_CONFIG },
  };
}

// -----------------------------------------------------------------------------
// Context Presets (matching backend)
// -----------------------------------------------------------------------------

// IMPORTANT: "minimal" must be truly empty - no pace, no conference, nothing.
// Only user-selected base stats are used when preset is "minimal".
export const CONTEXT_PRESETS: Record<ContextPreset, ContextFeatures> = {
  minimal: {
    // EMPTY - only base stats derived features are used
    game: [],
    market: [],
    team: [],
    player: [],
    diagnostic: [],
  },
  standard: {
    // Adds conference game only - NO pace (pace is in verbose)
    game: ["is_conference_game"],
    market: [],
    team: [],
    player: [],
    diagnostic: [],
  },
  market_aware: {
    // Adds closing lines for market context
    game: ["is_conference_game"],
    market: ["closing_spread_home", "closing_total"],
    team: [],
    player: [],
    diagnostic: [],
  },
  player_aware: {
    // Adds player and rest data
    game: ["is_conference_game", "home_rest_days", "away_rest_days"],
    market: [],
    team: [],
    player: ["player_minutes", "player_minutes_rolling"],
    diagnostic: [],
  },
  verbose: {
    // Everything
    game: [
      "is_conference_game",
      "pace_game",
      "home_rest_days",
      "away_rest_days",
      "rest_advantage",
    ],
    market: ["closing_spread_home", "closing_total", "ml_implied_edge"],
    team: ["rating_diff", "proj_points_diff"],
    player: ["player_minutes", "player_minutes_rolling", "player_minutes_delta"],
    diagnostic: [],
  },
  custom: {
    game: [],
    market: [],
    team: [],
    player: [],
    diagnostic: [],
  },
};

// -----------------------------------------------------------------------------
// Response Types
// -----------------------------------------------------------------------------

export interface CohortDefinition {
  rule_description: string; // Human-readable: "turnovers_diff in top 20%"
  discovered_split?: string | null; // If auto mode, what was found
  sample_size: number;
  feature_set_used: string; // "base_stats_only" | "standard" | "market_aware" etc
}

export interface SampleGame {
  game_id: string;
  game_date: string;
  home_team: string;
  away_team: string;
  home_score: number;
  away_score: number;
  target_value: number | string; // Spread, total, or win indicator
  outcome: string; // "W", "L", "O", "U", "Cover", "Miss"
}

export interface TheoryAnalysisResponse {
  run_id: string;
  // REQUIRED: Cohort definition - must be shown first in results
  cohort_definition: CohortDefinition;
  // Core metrics (single source of truth)
  sample_size: number;
  baseline_value: number;
  cohort_value: number;
  delta_value: number; // MUST equal cohort_value - baseline_value
  // Concepts - only shown if rule mode is auto OR context is not minimal
  detected_concepts: string[];
  concept_fields: string[];
  // Correlations - only from eligible features
  correlations: Array<{
    feature: string;
    correlation: number;
  }>;
  // Sample games with full data
  sample_games: SampleGame[];
  // Optional extended data
  evaluation?: Record<string, unknown> | null;
  micro_rows?: Array<Record<string, unknown>> | null;
  modeling_available: boolean;
  mc_available: boolean;
  mc_reason?: string | null;
  notes: string[];
}

// -----------------------------------------------------------------------------
// API Functions
// -----------------------------------------------------------------------------

function getApiBase(): string {
  // IMPORTANT: Do not rely on `NEXT_PUBLIC_*` for production base URLs. Those values
  // are inlined at build time into the browser bundle, and CI builds the `web` image
  // without production-specific build args. Use runtime resolution instead.
  return resolveApiBase({
    serverInternalBaseEnv: process.env.SPORTS_API_INTERNAL_URL,
    serverPublicBaseEnv: process.env.NEXT_PUBLIC_THEORY_ENGINE_URL,
    localhostPort: 8000,
  });
}

export async function analyzeTheory(draft: TheoryDraft): Promise<TheoryAnalysisResponse> {
  const res = await fetch(`${getApiBase()}/api/admin/theory/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(draft),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Failed to analyze theory: ${res.statusText} - ${text}`);
  }
  return res.json();
}

