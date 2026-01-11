"use client";

import React from "react";
import styles from "./TheoryBuilder.module.css";
import { LeagueSelector } from "./LeagueSelector";
import { TimeWindowSelector } from "./TimeWindowSelector";
import { TargetSelector } from "./TargetSelector";
import { BaseStatsSelector } from "./BaseStatsSelector";
import { CohortRuleSelector } from "./CohortRuleSelector";
import { ContextPresetSelector } from "./ContextPresetSelector";
import { FEATURE_PLAYER_MODELING } from "@/lib/featureFlags";
import type { TheoryBuilderState, TheoryBuilderActions } from "./useTheoryBuilderState";

interface Props {
  state: TheoryBuilderState;
  actions: TheoryBuilderActions;
  defineComplete: boolean;
}

export function DefinePanel({ state, actions, defineComplete }: Props) {
  const { draft, statKeys, loadingStatKeys, analysisLoading } = state;
  const hasTarget = !!draft.target.type;
  const hasStats = draft.inputs.base_stats.length > 0;
  const hasRule = draft.cohort_rule.mode === "auto" || 
    (draft.cohort_rule.mode === "quantile" && (draft.cohort_rule.quantile_rules ?? []).length > 0) ||
    (draft.cohort_rule.mode === "threshold" && (draft.cohort_rule.threshold_rules ?? []).length > 0);

  return (
    <div className={styles.definePanel}>
      {/* Section 1: Scope - single row */}
      <div className={styles.section}>
        <h3 className={styles.sectionTitle}>1. Scope</h3>
        <div className={styles.row}>
          <LeagueSelector value={draft.league} onChange={actions.setLeague} />
          <TimeWindowSelector
            value={draft.time_window}
            onChange={actions.setTimeWindow}
            league={draft.league}
          />
        </div>
      </div>

      {/* Section 2: Target - hero section */}
      <div className={styles.section}>
        <h3 className={styles.sectionTitle}>2. Target</h3>
        <p className={styles.hint}>What are we trying to explain / predict?</p>
        <TargetSelector value={draft.target} onChange={actions.setTarget} />
      </div>

      {/* Section 3: Stats */}
      <div className={styles.section}>
        <h3 className={styles.sectionTitle}>3. Stats</h3>
        <p className={styles.hint}>Select the stats to analyze.</p>
        <BaseStatsSelector
          selected={draft.inputs.base_stats}
          available={statKeys?.team_stat_keys ?? []}
          loading={loadingStatKeys}
          onToggle={actions.toggleBaseStat}
          onSelectAll={() => actions.setBaseStats(statKeys?.team_stat_keys ?? [])}
          onClear={() => actions.setBaseStats([])}
        />
      </div>

      {/* Section 4: Rule - REQUIRED - defines the cohort */}
      <div className={styles.section}>
        <h3 className={styles.sectionTitle}>
          4. Rule <span className={styles.required}>*</span>
        </h3>
        <p className={styles.hint}>How do we decide a game is “in the cohort”?</p>
        <CohortRuleSelector
          rule={draft.cohort_rule}
          selectedStats={draft.inputs.base_stats}
          onRuleChange={actions.setCohortRule}
          onModeChange={actions.setCohortRuleMode}
        />
      </div>

      {/* Section 5: Context - optional additional features */}
      <div className={styles.section}>
        <h3 className={styles.sectionTitle}>5. Context (optional)</h3>
        <p className={styles.hint}>Additional context features beyond your selected stats.</p>
        <ContextPresetSelector
          preset={draft.context.preset}
          features={draft.context.features}
          onPresetChange={actions.setContextPreset}
          onFeaturesChange={actions.setContextFeatures}
          diagnosticsAllowed={draft.diagnostics.allow_post_game_features}
          onDiagnosticsChange={actions.setDiagnosticsAllowed}
          hasPlayerFilter={!!draft.filters.player}
        />
      </div>

      {/* Advanced filters - simplified for MVP */}
      <details className={styles.advancedSection}>
        <summary className={styles.advancedToggle}>Advanced filters</summary>
        <div className={styles.advancedContent}>
          <div className={styles.filterRow}>
            <label className={styles.filterLabel}>
              Team
              <input
                type="text"
                className={styles.filterInput}
                placeholder="Team name..."
                value={draft.filters.team ?? ""}
                onChange={(e) => actions.setFilter("team", e.target.value || null)}
              />
            </label>
            {/* Player filter only shown if feature flag enabled */}
            {FEATURE_PLAYER_MODELING && (
              <label className={styles.filterLabel}>
                Player
                <input
                  type="text"
                  className={styles.filterInput}
                  placeholder="Player name..."
                  value={draft.filters.player ?? ""}
                  onChange={(e) => actions.setFilter("player", e.target.value || null)}
                />
              </label>
            )}
          </div>
          {draft.league === "NCAAB" && (
            <div className={styles.filterRow}>
              <label className={styles.filterLabel}>
                Phase
                <select
                  className={styles.filterSelect}
                  value={draft.filters.phase ?? "all"}
                  onChange={(e) =>
                    actions.setFilter(
                      "phase",
                      e.target.value === "all"
                        ? null
                        : (e.target.value as "out_conf" | "conf" | "postseason")
                    )
                  }
                >
                  <option value="all">All</option>
                  <option value="out_conf">Out of conference</option>
                  <option value="conf">Conference</option>
                  <option value="postseason">Postseason</option>
                </select>
              </label>
            </div>
          )}
          {draft.target.type === "spread_result" && (
            <div className={styles.filterRow}>
              <label className={styles.filterLabel}>
                Spread min
                <input
                  type="number"
                  className={styles.filterInput}
                  placeholder="0"
                  value={draft.filters.spread_abs_min ?? ""}
                  onChange={(e) =>
                    actions.setFilter(
                      "spread_abs_min",
                      e.target.value ? Number(e.target.value) : null
                    )
                  }
                />
              </label>
              <label className={styles.filterLabel}>
                Spread max
                <input
                  type="number"
                  className={styles.filterInput}
                  placeholder="10"
                  value={draft.filters.spread_abs_max ?? ""}
                  onChange={(e) =>
                    actions.setFilter(
                      "spread_abs_max",
                      e.target.value ? Number(e.target.value) : null
                    )
                  }
                />
              </label>
            </div>
          )}
        </div>
      </details>

      {/* CTA with validation feedback */}
      <div className={styles.ctaSection}>
        <button
          type="button"
          className={styles.primaryButton}
          disabled={!defineComplete || analysisLoading}
          onClick={() => {
            actions.runAnalysis();
            actions.setActiveTab("run");
          }}
        >
          {analysisLoading ? "Analyzing…" : "Analyze →"}
        </button>

        {defineComplete && <span className={styles.readyIndicator}>✓ Ready</span>}

        {!hasTarget && <p className={styles.ctaHint}>Select a target.</p>}
        {hasTarget && !hasStats && <p className={styles.ctaHint}>Select at least one stat.</p>}
        {hasTarget && hasStats && !hasRule && <p className={styles.ctaHint}>Define a cohort rule (or use Auto).</p>}
      </div>
    </div>
  );
}

