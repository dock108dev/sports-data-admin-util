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
 * Simplified scrape run form state.
 */
export type ScrapeRunForm = {
  leagueCode: LeagueCode;
  season: string;
  startDate: string;
  endDate: string;
  // Data type toggles
  boxscores: boolean;
  odds: boolean;
  social: boolean;
  pbp: boolean;
  // Shared filters
  onlyMissing: boolean;
  updatedBefore: string; // ISO date string or empty
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
  boxscores: true,
  odds: true,
  social: false,
  pbp: false,
  onlyMissing: false,
  updatedBefore: "",
  requestedBy: "admin@dock108.ai",
};

