"use client";

import React, { useEffect, useCallback, useMemo } from "react";
import Link from "next/link";
import styles from "./TheoryBuilder.module.css";
import { useTheoryBuilderState } from "./useTheoryBuilderState";
import { DefinePanel } from "./DefinePanel";
import { RunPanel } from "./RunPanel";
import { ResultsPanel } from "./ResultsPanel";
import { fetchStatKeys } from "@/lib/api/sportsAdmin";

export function TheoryBuilderPage() {
  const [state, actions] = useTheoryBuilderState("NBA");

  // Load stat keys when league changes
  const loadStatKeys = useCallback(async (league: string) => {
    actions.setLoadingStatKeys(true);
    try {
      const keys = await fetchStatKeys(league);
      actions.setStatKeys(keys);
    } catch (err) {
      console.error("Failed to load stat keys:", err);
      actions.setStatKeys(null);
    } finally {
      actions.setLoadingStatKeys(false);
    }
  }, [actions]);

  useEffect(() => {
    loadStatKeys(state.draft.league);
  }, [state.draft.league, loadStatKeys]);

  // Validation: is Define complete?
  const defineComplete = useMemo(() => {
    const hasTarget = !!state.draft.target.type;
    const hasStats = state.draft.inputs.base_stats.length > 0;
    return hasTarget && hasStats;
  }, [state.draft.target.type, state.draft.inputs.base_stats.length]);

  // Validation: has results?
  const hasResults = state.analysisResult !== null;
  
  // Can run analysis?
  const canRun = defineComplete;

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.title}>Theory Builder</h1>
        <p className={styles.subtitle}>
          Define, analyze, and model sports betting theories.{" "}
          <Link href="/admin/sports">← Back</Link>
        </p>
      </header>

      {/* Tabs with completion states */}
      <div className={styles.tabs}>
        <button
          type="button"
          className={`${styles.tab} ${state.activeTab === "define" ? styles.tabActive : ""} ${defineComplete ? styles.tabComplete : ""}`}
          onClick={() => actions.setActiveTab("define")}
        >
          Define
        </button>
        <button
          type="button"
          className={`${styles.tab} ${state.activeTab === "run" ? styles.tabActive : ""} ${hasResults ? styles.tabComplete : ""}`}
          onClick={() => canRun && actions.setActiveTab("run")}
          disabled={!canRun}
          title={!canRun ? "Select a target and at least one stat first" : undefined}
        >
          Run
        </button>
        <button
          type="button"
          className={`${styles.tab} ${state.activeTab === "results" ? styles.tabActive : ""}`}
          onClick={() => hasResults && actions.setActiveTab("results")}
          disabled={!hasResults}
          title={!hasResults ? "Run an analysis first" : undefined}
        >
          Results
        </button>
      </div>

      {/* Panel content */}
      {state.activeTab === "define" && (
        <DefinePanel state={state} actions={actions} defineComplete={defineComplete} />
      )}
      {state.activeTab === "run" && (
        <RunPanel state={state} actions={actions} />
      )}
      {state.activeTab === "results" && (
        <ResultsPanel state={state} actions={actions} />
      )}

      {/* Reset button */}
      <div style={{ marginTop: "1rem", display: "flex", justifyContent: "flex-end" }}>
        <button
          type="button"
          className={styles.tertiaryButton}
          onClick={actions.reset}
        >
          Reset all
        </button>
      </div>
    </div>
  );
}

