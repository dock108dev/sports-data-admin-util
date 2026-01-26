/**
 * Story V2 Types
 *
 * TypeScript definitions matching story_v2/schema.py
 *
 * These types are READ-ONLY views of Story V2 data.
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
 * A condensed moment: the atomic unit of Story V2.
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
 * Story V2 output: an ordered list of condensed moments.
 *
 * Contract guarantees:
 * - moments: Non-empty ordered list
 * - Moments are ordered by (period, start_clock) descending clock
 * - No play_id appears in multiple moments
 */
export type StoryV2Output = {
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
 * API response for Story V2.
 */
export type StoryV2Response = {
  game_id: number;
  sport: string;
  home_team: string;
  away_team: string;
  story: StoryV2Output;
  plays: PlayData[];
  validation_passed: boolean;
  validation_errors: string[];
};

/**
 * API error response for Story V2.
 */
export type StoryV2ErrorResponse = {
  error: string;
  validation_errors?: string[];
};
