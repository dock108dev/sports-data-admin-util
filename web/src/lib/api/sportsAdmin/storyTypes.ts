/**
 * Story Types
 *
 * TypeScript definitions matching story/schema.py and sports/schemas.py
 *
 * These types are READ-ONLY views of Story data.
 * The UI must not modify, augment, or interpret these structures.
 */

/**
 * Score state at a point in time.
 */
export type ScoreTuple = {
  home: number;
  away: number;
};

/**
 * A condensed moment: the atomic unit of Story.
 *
 * Contract guarantees:
 * - play_ids: Non-empty list of unique play identifiers
 * - explicitly_narrated_play_ids: Non-empty strict subset of play_ids
 * - narrative: Non-empty text describing at least one explicitly narrated play
 */
export type CondensedMoment = {
  play_ids: number[];
  explicitly_narrated_play_ids: number[];
  start_clock: string;
  end_clock: string;
  period: number;
  score_before: ScoreTuple;
  score_after: ScoreTuple;
  narrative: string;
};

/**
 * Story output: an ordered list of condensed moments.
 *
 * Contract guarantees:
 * - moments: Non-empty ordered list
 * - Moments are ordered by (period, start_clock) descending clock
 * - No play_id appears in multiple moments
 */
export type StoryOutput = {
  moments: CondensedMoment[];
};

/**
 * Play data for expansion view.
 *
 * Matches moment_builder.PlayData structure.
 */
export type PlayData = {
  play_index: number;
  period: number;
  game_clock: string;
  description: string;
  play_type: string | null;
  team_id: number | null;
  home_score: number;
  away_score: number;
};

/**
 * API response for Story.
 */
export type StoryResponse = {
  game_id: number;
  sport: string;
  home_team: string;
  away_team: string;
  story: StoryOutput;
  plays: PlayData[];
  validation_passed: boolean;
  validation_errors: string[];
};

/**
 * API error response for Story.
 */
export type StoryErrorResponse = {
  error: string;
  validation_errors?: string[];
};

// =============================================================================
// Game Flow API Types (GET /games/{game_id}/story)
// =============================================================================

/**
 * Player stat entry in cumulative box score.
 */
export type MomentPlayerStat = {
  name: string;
  // Basketball stats
  pts?: number | null;
  reb?: number | null;
  ast?: number | null;
  "3pm"?: number | null;
  // Hockey stats
  goals?: number | null;
  assists?: number | null;
  sog?: number | null;
  plusMinus?: number | null;
};

/**
 * Goalie stat entry for NHL box score.
 */
export type MomentGoalieStat = {
  name: string;
  saves: number;
  ga: number;
  savePct: number;
};

/**
 * Team box score for a moment.
 */
export type MomentTeamBoxScore = {
  team: string;
  score: number;
  players: MomentPlayerStat[];
  goalie?: MomentGoalieStat | null;
};

/**
 * Cumulative box score at a moment in time.
 */
export type MomentBoxScore = {
  home: MomentTeamBoxScore;
  away: MomentTeamBoxScore;
};

/**
 * A moment in the game flow.
 * Uses camelCase to match API JSON response.
 */
export type StoryMoment = {
  playIds: number[];
  explicitlyNarratedPlayIds: number[];
  period: number;
  startClock: string | null;
  endClock: string | null;
  scoreBefore: number[];
  scoreAfter: number[];
  narrative: string | null;  // Narrative is in blocks, not moments
  cumulativeBoxScore?: MomentBoxScore | null;
};

/**
 * A play referenced by a story moment.
 * Uses camelCase to match API JSON response.
 *
 * IMPORTANT: playId equals playIndex (not a database ID).
 * To join moments to plays: plays.filter(p => moment.playIds.includes(p.playId))
 */
export type StoryPlay = {
  /** Play identifier - equals playIndex for joining with moment.playIds */
  playId: number;
  /** Sequential play number in the game */
  playIndex: number;
  period: number;
  clock: string | null;
  playType: string | null;
  description: string | null;
  homeScore: number | null;
  awayScore: number | null;
};

/**
 * Story content containing ordered moments.
 */
export type StoryContent = {
  moments: StoryMoment[];
};

/**
 * Response from GET /games/{game_id}/story endpoint.
 * Returns the persisted game flow data.
 */
export type GameStoryResponse = {
  gameId: number;
  story: StoryContent;
  plays: StoryPlay[];
  validationPassed: boolean;
  validationErrors: string[];
  /** Phase 1 narrative blocks (4-7 blocks with narratives) */
  blocks?: NarrativeBlock[];
  /** Total word count across all block narratives */
  totalWords?: number;
};

// =============================================================================
// Phase 5: Block-based Narrative Types
// =============================================================================

/**
 * Semantic role for a narrative block.
 * Describes the block's function in the game's narrative arc.
 */
export type SemanticRole =
  | "SETUP"
  | "MOMENTUM_SHIFT"
  | "RESPONSE"
  | "DECISION_POINT"
  | "RESOLUTION";

/**
 * Embedded tweet in a narrative block.
 * Selected high-signal tweet for inline display.
 */
export type EmbeddedTweet = {
  tweetId: string;
  postedAt: string;
  text: string;
  author: string;
  phase: string;
  score: number;
  position: "EARLY" | "MID" | "LATE";
  hasMedia: boolean;
  mediaType?: string | null;
};

/**
 * Player stat with delta showing segment production.
 */
export type BlockPlayerStat = {
  name: string;
  // Basketball stats (cumulative)
  pts?: number;
  reb?: number;
  ast?: number;
  "3pm"?: number;
  fgm?: number;
  ftm?: number;
  // Basketball deltas (this block's production)
  delta_pts?: number;
  delta_reb?: number;
  delta_ast?: number;
  // Hockey stats (cumulative)
  goals?: number;
  assists?: number;
  sog?: number;
  plusMinus?: number;
  // Hockey deltas
  delta_goals?: number;
  delta_assists?: number;
};

/**
 * Team mini box score for a block.
 */
export type BlockTeamMiniBox = {
  team: string;
  players: BlockPlayerStat[];
};

/**
 * Mini box score for a block with cumulative stats and segment deltas.
 */
export type BlockMiniBox = {
  home: BlockTeamMiniBox;
  away: BlockTeamMiniBox;
  /** Top contributors in this segment (last names) */
  block_stars: string[];
};

/**
 * A narrative block in the collapsed game flow.
 * Replaces moment-level narratives with 1-2 sentences.
 */
export type NarrativeBlock = {
  blockIndex: number;
  role: SemanticRole;
  momentIndices: number[];
  periodStart: number;
  periodEnd: number;
  scoreBefore: number[];
  scoreAfter: number[];
  playIds: number[];
  keyPlayIds: number[];
  narrative: string | null;
  embeddedTweet?: EmbeddedTweet | null;
  /** Cumulative box score with segment deltas */
  miniBox?: BlockMiniBox | null;
};

/**
 * Social post for expandable sections.
 * Categorized by phase for organization.
 */
export type CategorizedSocialPost = {
  id: string | number;
  text: string;
  author: string;
  postedAt: string;
  phase: string;
  segment?: string | null;
  hasMedia: boolean;
  mediaType?: string | null;
  postUrl?: string;
};

/**
 * Grouped social posts for expandable sections.
 */
export type SocialPostsByPhase = {
  pregame: CategorizedSocialPost[];
  inGame: Record<string, CategorizedSocialPost[]>; // Keyed by segment (q1, q2, etc.)
  postgame: CategorizedSocialPost[];
};

/**
 * Response for block-based game flow.
 */
export type BlockStoryResponse = {
  gameId: number;
  leagueCode: string;
  blocks: NarrativeBlock[];
  totalWords: number;
  socialPosts?: SocialPostsByPhase;
  validationPassed: boolean;
  validationErrors: string[];
};
