/**
 * Sports-related constants shared across admin pages.
 * 
 * Centralized configuration to avoid duplication and ensure consistency.
 */

export const SUPPORTED_LEAGUES = ["NBA", "NCAAB", "NFL", "NCAAF", "MLB", "NHL"] as const;

export type LeagueCode = typeof SUPPORTED_LEAGUES[number];

/**
 * Status color mapping for scrape run status indicators.
 */
export const SCRAPE_RUN_STATUS_COLORS: Record<string, string> = {
  success: "#0f9d58",
  running: "#fbbc04",
  pending: "#5f6368",
  error: "#ea4335",
  interrupted: "#f97316", // Orange color for interrupted runs
  canceled: "#94a3b8",
} as const;

/**
 * Type for scrape run form state.
 */
export type ScrapeRunForm = {
  leagueCode: LeagueCode;
  season: string;
  startDate: string;
  endDate: string;
  includeBoxscores: boolean;
  includeOdds: boolean;
  includeSocial: boolean;
  backfillPlayerStats: boolean;
  backfillOdds: boolean;
  backfillSocial: boolean;
  requestedBy: string;
};

/**
 * Default form values for scrape run creation.
 */
export const DEFAULT_SCRAPE_RUN_FORM: ScrapeRunForm = {
  leagueCode: "NBA",
  season: "",
  startDate: "",
  endDate: "",
  includeBoxscores: true,
  includeOdds: true,
  includeSocial: false,
  backfillPlayerStats: false,
  backfillOdds: false,
  backfillSocial: false,
  requestedBy: "admin@dock108.ai",
};

