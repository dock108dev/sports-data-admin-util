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
// V2 Moments API Types (GET /games/{game_id}/story)
// =============================================================================

/**
 * A moment in the v2-moments story format.
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
  narrative: string;
};

/**
 * A play referenced by a story moment.
 * Uses camelCase to match API JSON response.
 */
export type StoryPlay = {
  playId: number;
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
 * Returns the persisted v2-moments Story exactly as stored.
 */
export type GameStoryResponse = {
  gameId: number;
  story: StoryContent;
  plays: StoryPlay[];
  validationPassed: boolean;
  validationErrors: string[];
};
