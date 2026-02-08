/**
 * Canonical route paths for the admin UI.
 *
 * Import these instead of hardcoding path strings across components.
 */
export const ROUTES = {
  SPORTS_BROWSER: "/admin/sports/browser",
  SPORTS_INGESTION: "/admin/sports/ingestion",
  SPORTS_STORY_GENERATOR: "/admin/sports/story-generator",
  FAIRBET_ODDS: "/admin/fairbet/odds",
  SPORTS_GAME: (id: number | string) => `/admin/sports/games/${id}`,
  SPORTS_TEAM: (id: number | string) => `/admin/sports/teams/${id}`,
} as const;
