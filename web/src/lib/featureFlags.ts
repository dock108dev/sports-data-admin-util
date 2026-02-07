/**
 * Feature flags for gating functionality.
 * 
 * MVP scope: minimal UI surface.
 * These flags hide features that exist but aren't MVP-ready.
 */

// Model building button in Run panel
export const FEATURE_MODEL_BUILDING =
  process.env.NEXT_PUBLIC_FF_MODEL_BUILDING === "true";

// Monte Carlo simulation button
export const FEATURE_MONTE_CARLO =
  process.env.NEXT_PUBLIC_FF_MONTE_CARLO === "true";

// Player-level features and filters
export const FEATURE_PLAYER_MODELING =
  process.env.NEXT_PUBLIC_FF_PLAYER_MODELING === "true";

// Team stat targets (non-market outcomes)
export const FEATURE_TEAM_STAT_TARGETS =
  process.env.NEXT_PUBLIC_FF_TEAM_STAT_TARGETS === "true";

// Custom context preset with individual toggles
export const FEATURE_CUSTOM_CONTEXT =
  process.env.NEXT_PUBLIC_FF_CUSTOM_CONTEXT === "true";

// Post-game diagnostic features
export const FEATURE_DIAGNOSTICS =
  process.env.NEXT_PUBLIC_FF_DIAGNOSTICS === "true";
