"use client";

import React from "react";
import styles from "./TheoryBuilder.module.css";
import type { CohortRule, CohortRuleMode, QuantileRule, ThresholdRule } from "@/lib/api/theoryDraft";

interface Props {
  rule: CohortRule;
  selectedStats: string[];
  onRuleChange: (rule: CohortRule) => void;
  onModeChange: (mode: CohortRuleMode) => void;
}

const MODE_OPTIONS: { mode: CohortRuleMode; label: string; description: string }[] = [
  {
    mode: "auto",
    label: "Auto-discover",
    description: "Find the strongest split using selected stats",
  },
  {
    mode: "quantile",
    label: "Top/Bottom %",
    description: "Games in top or bottom percentile of a stat",
  },
  {
    mode: "threshold",
    label: "Threshold",
    description: "Games where stat is above or below a value",
  },
];

export function CohortRuleSelector({ rule, selectedStats, onRuleChange, onModeChange }: Props) {
  // Generate diff versions of selected stats
  const statOptions = selectedStats.flatMap((stat) => [
    `${stat}_diff`,
    `${stat}_home`,
    `${stat}_away`,
    `${stat}_combined`,
  ]);

  // Handle quantile rule changes
  const handleQuantileChange = (index: number, field: keyof QuantileRule, value: string | number) => {
    const current = rule.quantile_rules ?? [];
    const updated = [...current];
    if (!updated[index]) {
      updated[index] = { stat: statOptions[0] ?? "", direction: "top", percentile: 20 };
    }
    updated[index] = { ...updated[index], [field]: value };
    onRuleChange({ ...rule, quantile_rules: updated });
  };

  // Handle threshold rule changes
  const handleThresholdChange = (index: number, field: keyof ThresholdRule, value: string | number) => {
    const current = rule.threshold_rules ?? [];
    const updated = [...current];
    if (!updated[index]) {
      updated[index] = { stat: statOptions[0] ?? "", operator: ">=", value: 0 };
    }
    updated[index] = { ...updated[index], [field]: value };
    onRuleChange({ ...rule, threshold_rules: updated });
  };

  // Add a new rule
  const addQuantileRule = () => {
    const current = rule.quantile_rules ?? [];
    onRuleChange({
      ...rule,
      quantile_rules: [...current, { stat: statOptions[0] ?? "", direction: "top", percentile: 20 }],
    });
  };

  const addThresholdRule = () => {
    const current = rule.threshold_rules ?? [];
    onRuleChange({
      ...rule,
      threshold_rules: [...current, { stat: statOptions[0] ?? "", operator: ">=", value: 0 }],
    });
  };

  // Remove a rule
  const removeQuantileRule = (index: number) => {
    const current = rule.quantile_rules ?? [];
    onRuleChange({ ...rule, quantile_rules: current.filter((_, i) => i !== index) });
  };

  const removeThresholdRule = (index: number) => {
    const current = rule.threshold_rules ?? [];
    onRuleChange({ ...rule, threshold_rules: current.filter((_, i) => i !== index) });
  };

  const hasNoStats = selectedStats.length === 0;

  return (
    <div className={styles.cohortRuleSelector}>
      {/* Mode selection */}
      <div className={styles.ruleModeSelect}>
        {MODE_OPTIONS.map((opt) => (
          <button
            key={opt.mode}
            type="button"
            className={`${styles.ruleModeButton} ${rule.mode === opt.mode ? styles.ruleModeButtonSelected : ""}`}
            onClick={() => onModeChange(opt.mode)}
            disabled={hasNoStats && opt.mode !== "auto"}
          >
            <span className={styles.ruleModeLabel}>{opt.label}</span>
            <span className={styles.ruleModeDesc}>{opt.description}</span>
          </button>
        ))}
      </div>

      {/* Quantile mode UI */}
      {rule.mode === "quantile" && (
        <div className={styles.ruleBuilder}>
          <p className={styles.ruleBuilderHint}>
            Define which games are “in the cohort” based on stat percentiles.
          </p>
          {(rule.quantile_rules ?? []).map((qr, idx) => (
            <div key={idx} className={styles.ruleRow}>
              <select
                className={styles.ruleSelect}
                value={qr.stat}
                onChange={(e) => handleQuantileChange(idx, "stat", e.target.value)}
              >
                {statOptions.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
              <span className={styles.ruleText}>in</span>
              <select
                className={styles.ruleSelect}
                value={qr.direction}
                onChange={(e) => handleQuantileChange(idx, "direction", e.target.value as "top" | "bottom")}
              >
                <option value="top">top</option>
                <option value="bottom">bottom</option>
              </select>
              <input
                type="number"
                className={styles.ruleInput}
                value={qr.percentile}
                min={5}
                max={50}
                step={5}
                onChange={(e) => handleQuantileChange(idx, "percentile", Number(e.target.value))}
              />
              <span className={styles.ruleText}>%</span>
              <button
                type="button"
                className={styles.ruleRemoveButton}
                onClick={() => removeQuantileRule(idx)}
                aria-label="Remove rule"
              >
                ×
              </button>
            </div>
          ))}
          {(rule.quantile_rules ?? []).length === 0 && (
            <p className={styles.ruleEmpty}>No rules defined. Add one to define the cohort.</p>
          )}
          <button
            type="button"
            className={styles.ruleAddButton}
            onClick={addQuantileRule}
            disabled={statOptions.length === 0}
          >
            + Add quantile rule
          </button>
        </div>
      )}

      {/* Threshold mode UI */}
      {rule.mode === "threshold" && (
        <div className={styles.ruleBuilder}>
          <p className={styles.ruleBuilderHint}>
            Define which games are “in the cohort” based on stat thresholds.
          </p>
          {(rule.threshold_rules ?? []).map((tr, idx) => (
            <div key={idx} className={styles.ruleRow}>
              <select
                className={styles.ruleSelect}
                value={tr.stat}
                onChange={(e) => handleThresholdChange(idx, "stat", e.target.value)}
              >
                {statOptions.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
              <select
                className={styles.ruleSelectSmall}
                value={tr.operator}
                onChange={(e) => handleThresholdChange(idx, "operator", e.target.value as ThresholdRule["operator"])}
              >
                <option value=">=">≥</option>
                <option value="<=">≤</option>
                <option value=">">{">"}</option>
                <option value="<">{"<"}</option>
              </select>
              <input
                type="number"
                className={styles.ruleInput}
                value={tr.value}
                step={0.5}
                onChange={(e) => handleThresholdChange(idx, "value", Number(e.target.value))}
              />
              <button
                type="button"
                className={styles.ruleRemoveButton}
                onClick={() => removeThresholdRule(idx)}
                aria-label="Remove rule"
              >
                ×
              </button>
            </div>
          ))}
          {(rule.threshold_rules ?? []).length === 0 && (
            <p className={styles.ruleEmpty}>No rules defined. Add one to define the cohort.</p>
          )}
          <button
            type="button"
            className={styles.ruleAddButton}
            onClick={addThresholdRule}
            disabled={statOptions.length === 0}
          >
            + Add threshold rule
          </button>
        </div>
      )}

      {/* Auto mode UI */}
      {rule.mode === "auto" && (
        <div className={styles.ruleBuilder}>
          <p className={styles.ruleBuilderHint}>
            The system will find the strongest split using your selected stats.
            After running, the discovered rule will be shown in the results.
          </p>
          {rule.discovered_rule && (
            <div className={styles.discoveredRule}>
              <span className={styles.discoveredRuleLabel}>Last discovered:</span>
              <span className={styles.discoveredRuleValue}>{rule.discovered_rule}</span>
            </div>
          )}
        </div>
      )}

      {/* Preview of current rule */}
      {rule.mode !== "auto" && (
        <div className={styles.rulePreview}>
          <span className={styles.rulePreviewLabel}>Current rule:</span>
          <span className={styles.rulePreviewValue}>
            {rule.mode === "quantile" && (rule.quantile_rules ?? []).length > 0
              ? (rule.quantile_rules ?? [])
                  .map((qr) => `${qr.stat} in ${qr.direction} ${qr.percentile}%`)
                  .join(" AND ")
              : rule.mode === "threshold" && (rule.threshold_rules ?? []).length > 0
                ? (rule.threshold_rules ?? [])
                    .map((tr) => `${tr.stat} ${tr.operator} ${tr.value}`)
                    .join(" AND ")
                : "No rule defined"}
          </span>
        </div>
      )}
    </div>
  );
}

