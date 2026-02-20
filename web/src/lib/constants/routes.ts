/**
 * Canonical route paths for the admin UI.
 *
 * Import these instead of hardcoding path strings across components.
 */
export const ROUTES = {
  /** Admin dashboard / overview */
  OVERVIEW: "/admin",

  GAMES: "/admin/sports/browser",
  RUNS: "/admin/sports/ingestion",
  PIPELINES: "/admin/sports/flow-generator",
  LOGS: "/admin/sports/logs",

  FAIRBET_ODDS: "/admin/fairbet/odds",
  SPORTS_GAME: (id: number | string) => `/admin/sports/games/${id}`,
} as const;
