"use client";

import { CollapsibleSection } from "./CollapsibleSection";
import {
  METRIC_GROUPS,
  OUTCOME_KEYS,
  formatMetricValue,
  getOutcomeBadgeClass,
} from "./GameDetailUtils";
import styles from "./styles.module.css";

type ComputedFieldsSectionProps = {
  derivedMetrics: Record<string, unknown>;
};

export function ComputedFieldsSection({ derivedMetrics }: ComputedFieldsSectionProps) {
  const metrics = derivedMetrics;
  const allGroupedKeys = new Set(METRIC_GROUPS.flatMap((g) => g.keys));
  const ungroupedKeys = Object.keys(metrics).filter((k) => !allGroupedKeys.has(k));

  return (
    <CollapsibleSection title="Computed Fields" defaultOpen={false}>
      {Object.keys(metrics).length === 0 ? (
        <div style={{ color: "#475569" }}>No computed fields.</div>
      ) : (
        <div className={styles.computedFieldsGrid}>
          {METRIC_GROUPS.map((group) => {
            const present = group.keys.filter((k) => k in metrics);
            if (present.length === 0) return null;
            return (
              <div key={group.label} className={styles.metricGroup}>
                <div className={styles.metricGroupLabel}>{group.label}</div>
                {present.map((k) => {
                  const isOutcome = OUTCOME_KEYS.has(k);
                  const formatted = formatMetricValue(k, metrics[k]);
                  return (
                    <div key={k} className={styles.metricRow}>
                      <span className={styles.metricKey}>{k}</span>
                      {isOutcome ? (
                        <span className={`${styles.outcomeBadge} ${getOutcomeBadgeClass(metrics[k])}`}>
                          {formatted}
                        </span>
                      ) : (
                        <span className={styles.metricValue}>{formatted}</span>
                      )}
                    </div>
                  );
                })}
              </div>
            );
          })}
          {ungroupedKeys.length > 0 && (
            <div className={styles.metricGroup}>
              <div className={styles.metricGroupLabel}>Other</div>
              {ungroupedKeys.map((k) => (
                <div key={k} className={styles.metricRow}>
                  <span className={styles.metricKey}>{k}</span>
                  <span className={styles.metricValue}>{formatMetricValue(k, metrics[k])}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </CollapsibleSection>
  );
}
