export type ScrapeRunResponse = {
  id: number;
  league_code: string;
  status: string;
  scraper_type: string;
  job_id: string | null;
  season: number | null;
  start_date: string | null;
  end_date: string | null;
  summary: string | null;
  error_details: string | null;
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
  has_pbp: boolean;
  play_count: number;
  social_post_count: number;
  has_required_data: boolean;
  scrape_version: number | null;
  last_scraped_at: string | null;
  last_ingested_at: string | null;
  last_pbp_at: string | null;
  last_social_at: string | null;
};

export type GameListResponse = {
  games: GameSummary[];
  total: number;
  next_offset: number | null;
  with_boxscore_count?: number;
  with_player_stats_count?: number;
  with_odds_count?: number;
  with_social_count?: number;
  with_pbp_count?: number;
};

export type TeamStat = {
  team: string;
  is_home: boolean;
  stats: Record<string, unknown>;
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
  raw_stats: Record<string, unknown>;
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
  tweet_text: string | null;
  video_url: string | null;
  image_url: string | null;
  source_handle: string | null;
  media_type: string | null;
};

export type PlayEntry = {
  play_index: number;
  quarter: number | null;
  game_clock: string | null;
  play_type: string | null;
  team_abbreviation: string | null;
  player_name: string | null;
  description: string | null;
  home_score: number | null;
  away_score: number | null;
};

/**
 * Player contribution within a moment.
 */
export type PlayerContribution = {
  name: string;
  stats: { pts?: number; stl?: number; blk?: number; ast?: number };
  summary: string | null; // "6 pts, 1 stl"
};

/**
 * Run metadata when a run contributed to a moment.
 */
export type RunInfo = {
  team: "home" | "away";
  points: number;
  unanswered: boolean;
  play_ids: number[];
};

/**
 * MomentType values (Lead Ladder):
 * - LEAD_BUILD: Lead tier increased
 * - CUT: Lead tier decreased (comeback)
 * - TIE: Game returned to even
 * - FLIP: Leader changed
 * - CLOSING_CONTROL: Late-game lock-in
 * - HIGH_IMPACT: Ejection, injury, etc.
 * - NEUTRAL: Normal flow
 */
export type MomentType =
  | "LEAD_BUILD"
  | "CUT"
  | "TIE"
  | "FLIP"
  | "CLOSING_CONTROL"
  | "HIGH_IMPACT"
  | "NEUTRAL";

/**
 * The single narrative unit.
 * 
 * Every play belongs to exactly one moment.
 * Moments are always chronological.
 * 
 * Moments are aggressively merged to stay within sport-specific budgets.
 * A typical NBA game has ~25-35 moments, not 60-70.
 */
export type MomentEntry = {
  id: string;                           // "m_001"
  type: MomentType;
  start_play: number;                   // First play index
  end_play: number;                     // Last play index
  play_count: number;                   // Number of plays
  teams: string[];
  primary_team: string | null;
  players: PlayerContribution[];
  score_start: string;                  // "12–15"
  score_end: string;                    // "18–15"
  clock: string;                        // "Q2 8:45–6:12"
  is_notable: boolean;                  // True for notable moments (key game events)
  is_period_start: boolean;             // True if this moment starts a new period
  note: string | null;                  // "7-0 run"
  
  // Lead Ladder state
  ladder_tier_before: number;
  ladder_tier_after: number;
  team_in_control: "home" | "away" | null;
  key_play_ids: number[];
  
  // WHY THIS MOMENT EXISTS - mandatory for narrative clarity
  reason?: MomentReason;
  
  // Run metadata if a run contributed
  run_info?: RunInfo;
  
  // AI-generated content (SportsCenter-style, spoiler-safe)
  headline: string;   // max 60 chars
  summary: string;    // max 150 chars
  
  // Display hints (frontend doesn't need to guess)
  display_weight: "high" | "medium" | "low";
  display_icon: string;  // Icon name suggestion
  display_color_hint: "tension" | "positive" | "neutral" | "highlight";
  
  // Phase 2-4: Context-aware narrative fields
  phase_state?: GamePhaseState;
  narrative_context?: MomentContext;
};

/**
 * Game phase state from Phase 2-4 context plumbing.
 * Provides temporal awareness for narrative generation.
 */
export type GamePhaseState = {
  phase_number: number;
  phase_type: string;
  clock_seconds: number;
  elapsed_seconds: number;
  remaining_seconds: number;
  game_progress: number;
  is_overtime: boolean;
  is_final_phase: boolean;
  is_closing_window: boolean;
};

/**
 * Narrative context from Phase 2-4 context plumbing.
 * Provides memory and continuity for AI-generated text.
 */
export type MomentContext = {
  game_phase: "opening" | "middle" | "closing";
  phase_progress: number;
  is_overtime: boolean;
  is_closing_window: boolean;
  previous_moment_type: string | null;
  previous_narrative_delta: string | null;
  is_continuation: boolean;
  parent_moment_id: string | null;
  recent_flip_tie_count: number;
  volatility_phase: "stable" | "back_and_forth" | "swingy";
  controlling_team: string | null;
  control_duration: number;
  tier_stability: "stable" | "volatile";
};

/**
 * Explains WHY a moment exists.
 * Every moment must have a reason. If you can't explain it, don't create it.
 */
export type MomentReason = {
  trigger: "tier_cross" | "flip" | "tie" | "closing_lock" | "high_impact" | "stable";
  control_shift: "home" | "away" | null;
  narrative_delta: string;  // "tension ↑" | "control gained" | "pressure relieved" | etc.
};

/**
 * Quality status of validated moments.
 * Provides clear signal about data integrity beyond pass/fail.
 */
export type QualityStatus = "PASSED" | "DEGRADED" | "FAILED" | "OVERRIDDEN";

/**
 * Score continuity issue record.
 * Captures where score jumped unexpectedly between moments.
 */
export type ScoreContinuityIssue = {
  prev_moment_id: string;
  curr_moment_id: string;
  prev_score_after: [number, number];
  curr_score_before: [number, number];
  delta: { home: number; away: number };
  position_in_sequence: number;
  prev_end_play: number;
  curr_start_play: number;
};

/**
 * Score continuity override audit record.
 */
export type ScoreContinuityOverride = {
  enabled: boolean;
  reason: string | null;
  overridden_by: string | null;
  overridden_at: string | null;
};

/**
 * Moment distribution metrics for pacing analysis.
 * Enables instant detection of pacing problems (e.g., Q1 spam).
 */
export type MomentDistribution = {
  moments_per_quarter: Record<string, number>;  // e.g., { Q1: 7, Q2: 6, Q3: 5, Q4: 3 }
  moments_by_trigger_type: Record<string, number>;  // e.g., { flip: 5, tier_cross: 12 }
  moments_by_tier: Record<string, number>;  // Tier at end of moment, keyed as strings
  average_plays_per_moment: number;
  first_half_vs_second_half: {
    first_half: number;
    second_half: number;
    overtime: number;
    first_half_percentage: number;
  };
  budget_utilization: {
    total_moments: number;
    budget: number;
    utilization_percentage: number;
  };
  merge_statistics: {
    total_before_merge: number;
    total_merged: number;
    merge_ratio: number;
  };
};

/**
 * Response from GET /games/{game_id}/moments
 * 
 * Moments are already merged and within sport-specific budgets (e.g., NBA: 30 max).
 * Each moment has a 'reason' field explaining why it exists.
 */
export type MomentsResponse = {
  game_id: number;
  generated_at: string | null;
  moments: MomentEntry[];
  total_count: number;
  
  // AI-generated game-level copy (SportsCenter-style, spoiler-safe)
  game_headline: string;   // max 80 chars
  game_subhead: string;    // max 120 chars
  
  // Phase 0: Quality and observability data
  quality_status?: QualityStatus;
  moment_distribution?: MomentDistribution;
  score_continuity_issues?: ScoreContinuityIssue[];
  score_continuity_override?: ScoreContinuityOverride;
};

/**
 * Game analysis from the pipeline.
 * Contains moments plus Phase 0 observability data.
 */
export type GameAnalysis = {
  moments: MomentEntry[];
  notable_moments: MomentEntry[];
  moment_count: number;
  quality_status: QualityStatus;
  moment_distribution?: MomentDistribution;
  score_continuity_issues?: ScoreContinuityIssue[];
  score_continuity_override?: ScoreContinuityOverride;
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
    last_ingested_at: string | null;
    last_pbp_at: string | null;
    last_social_at: string | null;
    has_boxscore: boolean;
    has_player_stats: boolean;
    has_odds: boolean;
    has_social: boolean;
    has_pbp: boolean;
    play_count: number;
    social_post_count: number;
  };
  team_stats: TeamStat[];
  player_stats: PlayerStat[];
  odds: OddsEntry[];
  social_posts: SocialPost[];
  plays: PlayEntry[];
  moments: MomentEntry[];  // Full game coverage; filter by is_notable for key moments
  derived_metrics: Record<string, unknown>;
  raw_payloads: Record<string, unknown>;
  // Phase 0: Game analysis with observability data
  game_analysis?: GameAnalysis;
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

export type AvailableStatKeysResponse = {
  league_code: string;
  team_stat_keys: string[];
  player_stat_keys: string[];
};

export type JobResponse = {
  run_id: number;
  job_id: string | null;
  message: string;
};
