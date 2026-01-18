"use client";

import { useState, useMemo } from "react";
import styles from "./CompareVersions.module.css";

/**
 * Phase 5: Compare Versions A/B View
 * 
 * Shows side-by-side comparison of two moment outputs with:
 * 1. High-level summary (counts, budget, half distribution)
 * 2. Distribution metrics (by type, tier, play counts)
 * 3. Timeline comparison (moment-by-moment diff)
 * 4. Merge/suppression visibility
 * 5. Narrative quality flags
 */

// Types for comparison data
export type HighLevelSummary = {
  total_moments: number;
  target_budget: number;
  actual_count: number;
  first_half_count: number;
  second_half_count: number;
  first_half_pct: number;
  moments_per_quarter: Record<number, number>;
};

export type DistributionMetrics = {
  by_trigger_type: Record<string, number>;
  by_tier: Record<number, number>;
  avg_play_count: number;
  min_play_count: number;
  max_play_count: number;
  mega_moment_count: number;
  chapter_moment_count: number;
};

export type TimelineRow = {
  play_range: string;
  old: {
    moment_id: string | null;
    type: string | null;
    importance: number | null;
    top_scorer: string | null;
    team_diff: number;
  } | null;
  new: {
    moment_id: string | null;
    type: string | null;
    importance: number | null;
    top_scorer: string | null;
    team_diff: number;
  } | null;
  status: "unchanged" | "added" | "removed" | "modified";
};

export type DisplacementEntry = {
  moment_id: string;
  reason: string;
  importance_rank: number;
  importance_score: number;
  displaced_by: string[];
  absorbed_into: string | null;
};

export type NarrativeFlag = {
  flag_id: string;
  severity: "info" | "warn";
  title: string;
  message: string;
  related_moment_ids: string[];
  details: Record<string, unknown>;
};

export type ComparisonData = {
  old_summary: HighLevelSummary;
  new_summary: HighLevelSummary;
  old_distribution: DistributionMetrics;
  new_distribution: DistributionMetrics;
  timeline: TimelineRow[];
  displacements: DisplacementEntry[];
  deltas: {
    moment_count: number;
    first_half_pct: number;
    avg_play_count: number;
  };
};

export type QualityCheckData = {
  flags: NarrativeFlag[];
  checks_run: number;
  warnings_count: number;
  info_count: number;
  has_warnings: boolean;
};

interface CompareVersionsProps {
  comparison: ComparisonData | null;
  qualityCheck: QualityCheckData | null;
  versionA: string;
  versionB: string;
  loading?: boolean;
}

type ViewMode = "structural" | "story";

export function CompareVersions({
  comparison,
  qualityCheck,
  versionA,
  versionB,
  loading = false,
}: CompareVersionsProps) {
  const [viewMode, setViewMode] = useState<ViewMode>("structural");
  const [showUnchanged, setShowUnchanged] = useState(false);
  const [expandedMoment, setExpandedMoment] = useState<string | null>(null);

  // Filter timeline based on showUnchanged
  const filteredTimeline = useMemo(() => {
    if (!comparison) return [];
    if (showUnchanged) return comparison.timeline;
    return comparison.timeline.filter((row) => row.status !== "unchanged");
  }, [comparison, showUnchanged]);

  if (loading) {
    return <div className={styles.loading}>Loading comparison...</div>;
  }

  if (!comparison) {
    return (
      <div className={styles.empty}>
        Select two versions to compare, or run a new analysis.
      </div>
    );
  }

  const { old_summary, new_summary, old_distribution, new_distribution, deltas, displacements } =
    comparison;

  return (
    <div className={styles.container}>
      {/* View Mode Toggle */}
      <div className={styles.viewToggle}>
        <button
          className={`${styles.viewButton} ${viewMode === "structural" ? styles.active : ""}`}
          onClick={() => setViewMode("structural")}
        >
          Structural View
        </button>
        <button
          className={`${styles.viewButton} ${viewMode === "story" ? styles.active : ""}`}
          onClick={() => setViewMode("story")}
        >
          Story View
        </button>
      </div>

      {/* Narrative Quality Flags */}
      {qualityCheck && qualityCheck.flags.length > 0 && (
        <div className={styles.flagsSection}>
          <h3 className={styles.sectionTitle}>
            Narrative Quality Flags
            {qualityCheck.has_warnings && (
              <span className={styles.warningBadge}>{qualityCheck.warnings_count} warnings</span>
            )}
          </h3>
          <div className={styles.flagsList}>
            {qualityCheck.flags.map((flag) => (
              <div
                key={flag.flag_id}
                className={`${styles.flagCard} ${
                  flag.severity === "warn" ? styles.flagWarn : styles.flagInfo
                }`}
              >
                <div className={styles.flagHeader}>
                  <span className={styles.flagIcon}>
                    {flag.severity === "warn" ? "⚠️" : "ℹ️"}
                  </span>
                  <span className={styles.flagTitle}>{flag.title}</span>
                </div>
                <p className={styles.flagMessage}>{flag.message}</p>
                {flag.related_moment_ids.length > 0 && (
                  <div className={styles.flagMoments}>
                    Related: {flag.related_moment_ids.slice(0, 5).join(", ")}
                    {flag.related_moment_ids.length > 5 && ` +${flag.related_moment_ids.length - 5} more`}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* High-Level Summary */}
      <div className={styles.summarySection}>
        <h3 className={styles.sectionTitle}>High-Level Summary</h3>
        <div className={styles.summaryGrid}>
          <SummaryCard
            label="Total Moments"
            oldValue={old_summary.total_moments}
            newValue={new_summary.total_moments}
            delta={deltas.moment_count}
          />
          <SummaryCard
            label="Target Budget"
            oldValue={old_summary.target_budget}
            newValue={new_summary.target_budget}
          />
          <SummaryCard
            label="First Half %"
            oldValue={old_summary.first_half_pct}
            newValue={new_summary.first_half_pct}
            delta={deltas.first_half_pct}
            suffix="%"
          />
          <SummaryCard
            label="Avg Play Count"
            oldValue={old_distribution.avg_play_count}
            newValue={new_distribution.avg_play_count}
            delta={deltas.avg_play_count}
          />
        </div>

        {/* Quarter Distribution */}
        <div className={styles.quarterGrid}>
          <h4>Moments per Quarter</h4>
          <div className={styles.quarterRow}>
            {[1, 2, 3, 4].map((q) => (
              <div key={q} className={styles.quarterCell}>
                <span className={styles.quarterLabel}>Q{q}</span>
                <span className={styles.quarterOld}>
                  {old_summary.moments_per_quarter[q] ?? 0}
                </span>
                <span className={styles.quarterArrow}>→</span>
                <span className={styles.quarterNew}>
                  {new_summary.moments_per_quarter[q] ?? 0}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Distribution Metrics */}
      <div className={styles.distributionSection}>
        <h3 className={styles.sectionTitle}>Distribution Metrics</h3>
        <div className={styles.distributionGrid}>
          {/* By Trigger Type */}
          <div className={styles.distributionCard}>
            <h4>By Trigger Type</h4>
            <table className={styles.distributionTable}>
              <thead>
                <tr>
                  <th>Type</th>
                  <th>{versionA}</th>
                  <th>{versionB}</th>
                  <th>Δ</th>
                </tr>
              </thead>
              <tbody>
                {Object.keys({
                  ...old_distribution.by_trigger_type,
                  ...new_distribution.by_trigger_type,
                }).map((type) => {
                  const oldVal = old_distribution.by_trigger_type[type] ?? 0;
                  const newVal = new_distribution.by_trigger_type[type] ?? 0;
                  const delta = newVal - oldVal;
                  return (
                    <tr key={type}>
                      <td>{type}</td>
                      <td>{oldVal}</td>
                      <td>{newVal}</td>
                      <td className={delta > 0 ? styles.positive : delta < 0 ? styles.negative : ""}>
                        {delta > 0 ? `+${delta}` : delta}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* Special Moments */}
          <div className={styles.distributionCard}>
            <h4>Special Moments</h4>
            <div className={styles.specialList}>
              <div className={styles.specialItem}>
                <span>Mega-Moments (50+ plays)</span>
                <span>
                  {old_distribution.mega_moment_count} → {new_distribution.mega_moment_count}
                </span>
              </div>
              <div className={styles.specialItem}>
                <span>Chapter Moments</span>
                <span>
                  {old_distribution.chapter_moment_count} → {new_distribution.chapter_moment_count}
                </span>
              </div>
              <div className={styles.specialItem}>
                <span>Play Count Range</span>
                <span>
                  {old_distribution.min_play_count}-{old_distribution.max_play_count} →{" "}
                  {new_distribution.min_play_count}-{new_distribution.max_play_count}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Timeline Comparison */}
      <div className={styles.timelineSection}>
        <div className={styles.timelineHeader}>
          <h3 className={styles.sectionTitle}>Timeline Comparison</h3>
          <label className={styles.toggleLabel}>
            <input
              type="checkbox"
              checked={showUnchanged}
              onChange={(e) => setShowUnchanged(e.target.checked)}
            />
            Show unchanged
          </label>
        </div>

        {filteredTimeline.length === 0 ? (
          <div className={styles.noChanges}>No changes detected in timeline.</div>
        ) : (
          <div className={styles.timelineList}>
            {filteredTimeline.map((row, idx) => (
              <div
                key={idx}
                className={`${styles.timelineRow} ${styles[`status${capitalize(row.status)}`]}`}
                onClick={() =>
                  setExpandedMoment(
                    expandedMoment === row.play_range ? null : row.play_range
                  )
                }
              >
                <div className={styles.playRange}>{row.play_range}</div>
                <div className={styles.timelineSide}>
                  {row.old ? (
                    <>
                      <span className={styles.momentType}>{row.old.type}</span>
                      {viewMode === "story" && row.old.top_scorer && (
                        <span className={styles.topScorer}>{row.old.top_scorer}</span>
                      )}
                      <span className={styles.importance}>
                        {row.old.importance?.toFixed(2)}
                      </span>
                    </>
                  ) : (
                    <span className={styles.missing}>—</span>
                  )}
                </div>
                <div className={styles.statusIndicator}>
                  {row.status === "added" && "➕"}
                  {row.status === "removed" && "➖"}
                  {row.status === "modified" && "✏️"}
                  {row.status === "unchanged" && "═"}
                </div>
                <div className={styles.timelineSide}>
                  {row.new ? (
                    <>
                      <span className={styles.momentType}>{row.new.type}</span>
                      {viewMode === "story" && row.new.top_scorer && (
                        <span className={styles.topScorer}>{row.new.top_scorer}</span>
                      )}
                      <span className={styles.importance}>
                        {row.new.importance?.toFixed(2)}
                      </span>
                    </>
                  ) : (
                    <span className={styles.missing}>—</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Displacements */}
      {displacements.length > 0 && (
        <div className={styles.displacementsSection}>
          <h3 className={styles.sectionTitle}>
            Merged / Suppressed Moments ({displacements.length})
          </h3>
          <div className={styles.displacementsList}>
            {displacements.map((d) => (
              <div key={d.moment_id} className={styles.displacementCard}>
                <div className={styles.displacementHeader}>
                  <span className={styles.displacementId}>{d.moment_id}</span>
                  <span className={styles.displacementReason}>{d.reason}</span>
                </div>
                <div className={styles.displacementDetails}>
                  <span>Rank: #{d.importance_rank}</span>
                  <span>Score: {d.importance_score.toFixed(2)}</span>
                  {d.displaced_by.length > 0 && (
                    <span>Displaced by: {d.displaced_by.join(", ")}</span>
                  )}
                  {d.absorbed_into && <span>Absorbed into: {d.absorbed_into}</span>}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// Helper component for summary cards
function SummaryCard({
  label,
  oldValue,
  newValue,
  delta,
  suffix = "",
}: {
  label: string;
  oldValue: number;
  newValue: number;
  delta?: number;
  suffix?: string;
}) {
  const showDelta = delta !== undefined && delta !== 0;

  return (
    <div className={styles.summaryCard}>
      <div className={styles.summaryLabel}>{label}</div>
      <div className={styles.summaryValues}>
        <span className={styles.summaryOld}>
          {oldValue}
          {suffix}
        </span>
        <span className={styles.summaryArrow}>→</span>
        <span className={styles.summaryNew}>
          {newValue}
          {suffix}
        </span>
      </div>
      {showDelta && (
        <div
          className={`${styles.summaryDelta} ${
            delta > 0 ? styles.positive : styles.negative
          }`}
        >
          {delta > 0 ? `+${delta}` : delta}
          {suffix}
        </div>
      )}
    </div>
  );
}

function capitalize(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export default CompareVersions;
