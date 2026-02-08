/**
 * Canonical route paths for the admin UI.
 *
 * Import these instead of hardcoding path strings across components.
 */
export const ROUTES = {
  SPORTS_BROWSER: "/admin/sports/browser",
  SPORTS_INGESTION: "/admin/sports/ingestion",
  SPORTS_FLOW_GENERATOR: "/admin/sports/flow-generator",
  FAIRBET_ODDS: "/admin/fairbet/odds",
  SPORTS_GAME: (id: number | string) => `/admin/sports/games/${id}`,
} as const;
