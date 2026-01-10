"use client";

import { useState, useCallback, useMemo } from "react";
import {
  type TheoryDraft,
  type TheoryAnalysisResponse,
  type TimeWindow,
  type Target,
  type ContextPreset,
  type ContextFeatures,
  type CohortRule,
  type CohortRuleMode,
  createDefaultTheoryDraft,
  CONTEXT_PRESETS,
  analyzeTheory,
} from "@/lib/api/theoryDraft";
import type { AvailableStatKeysResponse } from "@/lib/api/sportsAdmin";

export interface TheoryBuilderState {
  // Core state
  draft: TheoryDraft;
  statKeys: AvailableStatKeysResponse | null;
  loadingStatKeys: boolean;

  // Analysis state
  analysisResult: TheoryAnalysisResponse | null;
  analysisLoading: boolean;
  analysisError: string | null;

  // Model state
  modelResult: unknown | null;
  modelLoading: boolean;
  modelError: string | null;

  // MC state
  mcResult: unknown | null;
  mcLoading: boolean;
  mcError: string | null;

  // UI state
  activeTab: "define" | "run" | "results" | "advanced";
  showAdvancedFilters: boolean;
}

export interface TheoryBuilderActions {
  // Draft mutations
  setLeague: (league: string) => void;
  setTimeWindow: (tw: TimeWindow) => void;
  setTarget: (target: Target) => void;
  setBaseStats: (stats: string[]) => void;
  toggleBaseStat: (stat: string) => void;
  setCohortRule: (rule: CohortRule) => void;
  setCohortRuleMode: (mode: CohortRuleMode) => void;
  setContextPreset: (preset: ContextPreset) => void;
  setContextFeatures: (features: ContextFeatures) => void;
  setFilter: <K extends keyof TheoryDraft["filters"]>(
    key: K,
    value: TheoryDraft["filters"][K]
  ) => void;
  setDiagnosticsAllowed: (allowed: boolean) => void;
  setModelEnabled: (enabled: boolean) => void;
  setModelProbThreshold: (threshold: number) => void;

  // Actions
  runAnalysis: () => Promise<void>;
  runModel: () => Promise<void>;
  runMonteCarlo: () => Promise<void>;
  reset: () => void;

  // UI
  setActiveTab: (tab: TheoryBuilderState["activeTab"]) => void;
  setShowAdvancedFilters: (show: boolean) => void;
  setStatKeys: (keys: AvailableStatKeysResponse | null) => void;
  setLoadingStatKeys: (loading: boolean) => void;
}

export function useTheoryBuilderState(
  initialLeague: string = "NBA"
): [TheoryBuilderState, TheoryBuilderActions] {
  // Single source of truth
  const [draft, setDraft] = useState<TheoryDraft>(() =>
    createDefaultTheoryDraft(initialLeague)
  );

  // Stat keys
  const [statKeys, setStatKeys] = useState<AvailableStatKeysResponse | null>(null);
  const [loadingStatKeys, setLoadingStatKeys] = useState(false);

  // Analysis
  const [analysisResult, setAnalysisResult] = useState<TheoryAnalysisResponse | null>(null);
  const [analysisLoading, setAnalysisLoading] = useState(false);
  const [analysisError, setAnalysisError] = useState<string | null>(null);

  // Model
  const [modelResult, setModelResult] = useState<unknown | null>(null);
  const [modelLoading, setModelLoading] = useState(false);
  const [modelError, setModelError] = useState<string | null>(null);

  // MC
  const [mcResult, setMcResult] = useState<unknown | null>(null);
  const [mcLoading, setMcLoading] = useState(false);
  const [mcError, setMcError] = useState<string | null>(null);

  // UI
  const [activeTab, setActiveTab] = useState<TheoryBuilderState["activeTab"]>("define");
  const [showAdvancedFilters, setShowAdvancedFilters] = useState(false);

  // Draft mutations
  const setLeague = useCallback((league: string) => {
    setDraft((prev) => ({ ...prev, league }));
    // Clear results when league changes
    setAnalysisResult(null);
    setModelResult(null);
    setMcResult(null);
  }, []);

  const setTimeWindow = useCallback((time_window: TimeWindow) => {
    setDraft((prev) => ({ ...prev, time_window }));
  }, []);

  const setTarget = useCallback((target: Target) => {
    setDraft((prev) => ({ ...prev, target }));
  }, []);

  const setBaseStats = useCallback((base_stats: string[]) => {
    setDraft((prev) => ({
      ...prev,
      inputs: { ...prev.inputs, base_stats },
    }));
  }, []);

  const toggleBaseStat = useCallback((stat: string) => {
    setDraft((prev) => {
      const current = prev.inputs.base_stats;
      const next = current.includes(stat)
        ? current.filter((s) => s !== stat)
        : [...current, stat];
      return {
        ...prev,
        inputs: { ...prev.inputs, base_stats: next },
      };
    });
  }, []);

  const setCohortRule = useCallback((cohort_rule: CohortRule) => {
    setDraft((prev) => ({ ...prev, cohort_rule }));
  }, []);

  const setCohortRuleMode = useCallback((mode: CohortRuleMode) => {
    setDraft((prev) => ({
      ...prev,
      cohort_rule: {
        ...prev.cohort_rule,
        mode,
        // Clear rules when switching modes
        quantile_rules: mode === "quantile" ? prev.cohort_rule.quantile_rules : [],
        threshold_rules: mode === "threshold" ? prev.cohort_rule.threshold_rules : [],
      },
    }));
  }, []);

  const setContextPreset = useCallback((preset: ContextPreset) => {
    setDraft((prev) => ({
      ...prev,
      context: {
        preset,
        features: preset === "custom" ? prev.context.features : { ...CONTEXT_PRESETS[preset] },
      },
    }));
  }, []);

  const setContextFeatures = useCallback((features: ContextFeatures) => {
    setDraft((prev) => ({
      ...prev,
      context: { preset: "custom", features },
    }));
  }, []);

  const setFilter = useCallback(
    <K extends keyof TheoryDraft["filters"]>(key: K, value: TheoryDraft["filters"][K]) => {
      setDraft((prev) => ({
        ...prev,
        filters: { ...prev.filters, [key]: value },
      }));
    },
    []
  );

  const setDiagnosticsAllowed = useCallback((allow_post_game_features: boolean) => {
    setDraft((prev) => ({
      ...prev,
      diagnostics: { allow_post_game_features },
    }));
  }, []);

  const setModelEnabled = useCallback((enabled: boolean) => {
    setDraft((prev) => ({
      ...prev,
      model: { ...prev.model, enabled },
    }));
  }, []);

  const setModelProbThreshold = useCallback((prob_threshold: number) => {
    setDraft((prev) => ({
      ...prev,
      model: { ...prev.model, prob_threshold },
    }));
  }, []);

  // Actions
  const runAnalysis = useCallback(async () => {
    setAnalysisLoading(true);
    setAnalysisError(null);
    try {
      const result = await analyzeTheory(draft);
      setAnalysisResult(result);
      setActiveTab("results");
    } catch (err) {
      setAnalysisError(err instanceof Error ? err.message : String(err));
    } finally {
      setAnalysisLoading(false);
    }
  }, [draft]);

  const runModel = useCallback(async () => {
    setModelLoading(true);
    setModelError(null);
    setModelResult(null);
    try {
      throw new Error("Model building is not available yet.");
    } catch (err) {
      setModelError(err instanceof Error ? err.message : String(err));
    } finally {
      setModelLoading(false);
    }
  }, []);

  const runMonteCarlo = useCallback(async () => {
    setMcLoading(true);
    setMcError(null);
    setMcResult(null);
    try {
      throw new Error("Monte Carlo simulations are not available yet.");
    } catch (err) {
      setMcError(err instanceof Error ? err.message : String(err));
    } finally {
      setMcLoading(false);
    }
  }, []);

  const reset = useCallback(() => {
    setDraft(createDefaultTheoryDraft(draft.league));
    setAnalysisResult(null);
    setModelResult(null);
    setMcResult(null);
    setAnalysisError(null);
    setModelError(null);
    setMcError(null);
    setActiveTab("define");
    setShowAdvancedFilters(false);
  }, [draft.league]);

  const state: TheoryBuilderState = useMemo(
    () => ({
      draft,
      statKeys,
      loadingStatKeys,
      analysisResult,
      analysisLoading,
      analysisError,
      modelResult,
      modelLoading,
      modelError,
      mcResult,
      mcLoading,
      mcError,
      activeTab,
      showAdvancedFilters,
    }),
    [
      draft,
      statKeys,
      loadingStatKeys,
      analysisResult,
      analysisLoading,
      analysisError,
      modelResult,
      modelLoading,
      modelError,
      mcResult,
      mcLoading,
      mcError,
      activeTab,
      showAdvancedFilters,
    ]
  );

  const actions: TheoryBuilderActions = useMemo(
    () => ({
      setLeague,
      setTimeWindow,
      setTarget,
      setBaseStats,
      toggleBaseStat,
      setCohortRule,
      setCohortRuleMode,
      setContextPreset,
      setContextFeatures,
      setFilter,
      setDiagnosticsAllowed,
      setModelEnabled,
      setModelProbThreshold,
      runAnalysis,
      runModel,
      runMonteCarlo,
      reset,
      setActiveTab,
      setShowAdvancedFilters,
      setStatKeys,
      setLoadingStatKeys,
    }),
    [
      setLeague,
      setTimeWindow,
      setTarget,
      setBaseStats,
      toggleBaseStat,
      setCohortRule,
      setCohortRuleMode,
      setContextPreset,
      setContextFeatures,
      setFilter,
      setDiagnosticsAllowed,
      setModelEnabled,
      setModelProbThreshold,
      runAnalysis,
      runModel,
      runMonteCarlo,
      reset,
    ]
  );

  return [state, actions];
}
