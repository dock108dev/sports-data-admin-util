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
  has_highlights: boolean;
  play_count: number;
  social_post_count: number;
  highlight_count: number;
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
  with_highlights_count?: number;
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
 * Player contribution in a highlight stretch.
 */
export type PlayerContribution = {
  name: string;
  stats: { pts?: number; stl?: number; blk?: number; ast?: number };
  summary: string | null; // "6 pts, 1 stl"
};

/**
 * Grounded highlight with play references and context.
 * Each highlight is traceable to specific plays in the timeline.
 */
export type HighlightEntry = {
  highlight_id: string;
  type: string; // SCORING_RUN, LEAD_CHANGE, MOMENTUM_SHIFT, etc.
  title: string;
  description: string;
  start_play_id: string;
  end_play_id: string;
  key_play_ids: string[];
  involved_teams: string[];
  involved_players: PlayerContribution[];
  score_change: string; // "92–96 → 98–96"
  game_clock_range: string; // "Q4 7:42–5:58"
  game_phase: "early" | "mid" | "late" | "closing";
  importance_score: number;
};

/**
 * Response from GET /games/{game_id}/highlights
 */
export type HighlightsResponse = {
  game_id: number;
  generated_at: string | null;
  highlights: HighlightEntry[];
  total_count: number;
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
    has_highlights: boolean;
    play_count: number;
    social_post_count: number;
    highlight_count: number;
  };
  team_stats: TeamStat[];
  player_stats: PlayerStat[];
  odds: OddsEntry[];
  social_posts: SocialPost[];
  plays: PlayEntry[];
  highlights: HighlightEntry[];
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
