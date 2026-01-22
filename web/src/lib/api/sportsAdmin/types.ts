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

// ============================================================================
// CHAPTERS-FIRST MODEL (ISSUE 14)
// ============================================================================

/**
 * Chapter: A contiguous narrative segment (scene) in the game.
 * 
 * Chapters are the structural unit for storytelling and UI expansion.
 * They are deterministic and defined by structural boundaries, not narrative.
 */
export type ChapterEntry = {
  chapter_id: string;                   // "ch_001"
  index: number;                        // Explicit chapter index for UI ordering
  play_start_idx: number;               // First play index (inclusive)
  play_end_idx: number;                 // Last play index (inclusive)
  play_count: number;                   // Number of plays in chapter
  reason_codes: string[];               // Why this chapter boundary exists
  period: number | null;                // Quarter/period number
  time_range: {                         // Game clock range
    start: string;
    end: string;
  } | null;
  
  // AI-generated (optional)
  chapter_summary: string | null;       // 1-3 sentence summary
  chapter_title: string | null;         // Short title (3-8 words)
  
  // Plays (for expansion)
  plays: PlayEntry[];
  
  // Debug-only (optional)
  chapter_fingerprint?: string | null;  // Deterministic chapter hash
  boundary_logs?: Array<Record<string, unknown>> | null;  // Debug boundary events
};

/**
 * Game Story: The authoritative output for apps.
 * 
 * Represents a game as a book with chapters.
 */
export type GameStoryResponse = {
  game_id: number;
  sport: string;
  story_version: string;                // Story generation version
  chapters: ChapterEntry[];
  chapter_count: number;
  total_plays: number;
  
  // AI-generated full story (optional)
  compact_story: string | null;
  reading_time_estimate_minutes: number | null;
  
  // Metadata
  generated_at: string | null;
  metadata: Record<string, unknown>;
  
  // Generation status
  has_summaries: boolean;
  has_titles: boolean;
  has_compact_story: boolean;
};

/**
 * Story State: Running context for AI generation.
 * 
 * Derived deterministically from prior chapters only.
 */
export type StoryStateResponse = {
  chapter_index_last_processed: number;
  players: Record<string, PlayerStoryState>;
  teams: Record<string, TeamStoryState>;
  momentum_hint: "surging" | "steady" | "slipping" | "volatile" | "unknown";
  theme_tags: string[];
  constraints: {
    no_future_knowledge: boolean;
    source: string;
  };
};

export type PlayerStoryState = {
  player_name: string;
  points_so_far: number;
  made_fg_so_far: number;
  made_3pt_so_far: number;
  made_ft_so_far: number;
  notable_actions_so_far: string[];
};

export type TeamStoryState = {
  team_name: string;
  score_so_far: number | null;
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
  derived_metrics: Record<string, unknown>;
  raw_payloads: Record<string, unknown>;
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
