# Feature Flags & Toggles Inventory

This document tracks all flags, environment toggles, and behavior switches.
Use this to decide what stays, what goes, and what becomes permanent config.

## Table

### FEATURE_MODEL_BUILDING
- **Flag Name:** `FEATURE_MODEL_BUILDING`
- **File / Location:** `web/src/lib/featureFlags.ts` (export), `web/src/components/admin/theory-builder/RunPanel.tsx`
- **Default Value:** `false` (env var must be set to `"true"`)
- **Env Overrides:** `NEXT_PUBLIC_FF_MODEL_BUILDING`
- **Purpose:** Shows the Model Building button in the Theory Builder run panel.
- **MVP or Permanent:** MVP
- **Classification:** MVP_ONLY
- **Notes:** UI-only visibility gate.

### FEATURE_MONTE_CARLO
- **Flag Name:** `FEATURE_MONTE_CARLO`
- **File / Location:** `web/src/lib/featureFlags.ts` (export), `web/src/components/admin/theory-builder/RunPanel.tsx`
- **Default Value:** `false`
- **Env Overrides:** `NEXT_PUBLIC_FF_MONTE_CARLO`
- **Purpose:** Shows the Monte Carlo simulation button in the Theory Builder run panel.
- **MVP or Permanent:** MVP
- **Classification:** MVP_ONLY
- **Notes:** UI-only visibility gate.

### FEATURE_PLAYER_MODELING
- **Flag Name:** `FEATURE_PLAYER_MODELING`
- **File / Location:** `web/src/lib/featureFlags.ts` (export), `web/src/components/admin/theory-builder/DefinePanel.tsx`, `web/src/components/admin/theory-builder/ContextPresetSelector.tsx`
- **Default Value:** `false`
- **Env Overrides:** `NEXT_PUBLIC_FF_PLAYER_MODELING`
- **Purpose:** Enables player-level feature presets/filters in Theory Builder.
- **MVP or Permanent:** MVP
- **Classification:** MVP_ONLY
- **Notes:** Hides player-related presets and filter UI when disabled.

### FEATURE_TEAM_STAT_TARGETS
- **Flag Name:** `FEATURE_TEAM_STAT_TARGETS`
- **File / Location:** `web/src/lib/featureFlags.ts` (export), `web/src/components/admin/theory-builder/TargetSelector.tsx`
- **Default Value:** `false`
- **Env Overrides:** `NEXT_PUBLIC_FF_TEAM_STAT_TARGETS`
- **Purpose:** Shows team-stat target types (non-market outcomes) in Theory Builder.
- **MVP or Permanent:** MVP
- **Classification:** MVP_ONLY
- **Notes:** Flags target options as gated.

### FEATURE_CUSTOM_CONTEXT
- **Flag Name:** `FEATURE_CUSTOM_CONTEXT`
- **File / Location:** `web/src/lib/featureFlags.ts` (export), `web/src/components/admin/theory-builder/ContextPresetSelector.tsx`
- **Default Value:** `false`
- **Env Overrides:** `NEXT_PUBLIC_FF_CUSTOM_CONTEXT`
- **Purpose:** Allows the custom context preset with individual feature toggles.
- **MVP or Permanent:** MVP
- **Classification:** MVP_ONLY
- **Notes:** Gates the “Custom” preset and related feature list.

### FEATURE_DIAGNOSTICS
- **Flag Name:** `FEATURE_DIAGNOSTICS`
- **File / Location:** `web/src/lib/featureFlags.ts` (export), `web/src/components/admin/theory-builder/ContextPresetSelector.tsx`
- **Default Value:** `false`
- **Env Overrides:** `NEXT_PUBLIC_FF_DIAGNOSTICS`
- **Purpose:** Enables post-game diagnostic features in Theory Builder.
- **MVP or Permanent:** MVP
- **Classification:** MVP_ONLY
- **Notes:** Adds leaky-feature diagnostics and warnings.

### ENABLE_INLINE_X_VIDEO
- **Flag Name:** `ENABLE_INLINE_X_VIDEO`
- **File / Location:** `web/src/lib/featureFlags.ts` (export), `web/src/components/social/SocialMediaRenderer.tsx`
- **Default Value:** `false`
- **Env Overrides:** `NEXT_PUBLIC_ENABLE_INLINE_X_VIDEO`
- **Purpose:** Allows inline playback of X videos in social media rendering.
- **MVP or Permanent:** Experimental
- **Classification:** EXPERIMENTAL
- **Notes:** UI behavior toggle for embedded media.

## Conflicts & Risk Areas
- No conflicting values detected; all feature flags default to `false` and are enabled only via environment variables.

## Removal Candidates
- None identified yet. All flags are active UI gates and appear intentionally scoped.

## Permanent Config Flags
- None identified yet.
