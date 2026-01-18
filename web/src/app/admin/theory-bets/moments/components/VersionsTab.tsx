"use client";

import { useState, useEffect, useCallback } from "react";
import styles from "../styles.module.css";
import {
  fetchPayloadVersions,
  comparePayloadVersions,
  type PayloadVersionSummary,
  type PayloadComparisonResponse,
} from "@/lib/api/sportsAdmin";
import type { GameSummary } from "@/lib/api/sportsAdmin";

interface VersionsTabProps {
  gameId: number | null;
  game: GameSummary | null;
}

/**
 * Tab for viewing payload version history with diffs.
 * Shows all versions for a game and allows comparing any two.
 */
export function VersionsTab({ gameId, game }: VersionsTabProps) {
  const [versions, setVersions] = useState<PayloadVersionSummary[]>([]);
  const [activeVersion, setActiveVersion] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Compare state
  const [compareA, setCompareA] = useState<number | null>(null);
  const [compareB, setCompareB] = useState<number | null>(null);
  const [comparison, setComparison] = useState<PayloadComparisonResponse | null>(null);
  const [comparing, setComparing] = useState(false);

  const loadVersions = useCallback(async () => {
    if (!gameId) return;
    setLoading(true);
    setError(null);
    try {
      const data = await fetchPayloadVersions(gameId);
      setVersions(data.versions);
      setActiveVersion(data.active_version);
      // Auto-set compare versions if we have at least 2
      if (data.versions.length >= 2) {
        setCompareA(data.versions[1].version_number);
        setCompareB(data.versions[0].version_number);
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      if (message.includes("404")) {
        setVersions([]);
      } else {
        setError(message);
      }
    } finally {
      setLoading(false);
    }
  }, [gameId]);

  useEffect(() => {
    if (gameId) {
      loadVersions();
      setComparison(null);
    }
  }, [gameId, loadVersions]);

  const handleCompare = async () => {
    if (!gameId || !compareA || !compareB) return;
    setComparing(true);
    try {
      const data = await comparePayloadVersions(gameId, compareA, compareB);
      setComparison(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setComparing(false);
    }
  };

  const formatRelativeTime = (isoDate: string) => {
    const date = new Date(isoDate);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
    if (diffHours < 1) return "< 1 hour ago";
    if (diffHours < 24) return `${diffHours}h ago`;
    const diffDays = Math.floor(diffHours / 24);
    return `${diffDays}d ago`;
  };

  if (loading) {
    return <div className={styles.loading}>Loading versions...</div>;
  }

  if (!gameId) {
    return <div className={styles.empty}>Select a game to view payload versions.</div>;
  }

  if (error) {
    return <div className={styles.error}>{error}</div>;
  }

  if (versions.length === 0) {
    return (
      <div className={styles.empty}>
        No payload versions found for this game.
        <br />
        <span style={{ fontSize: "0.85rem", color: "#94a3b8" }}>
          Moments may need to be generated first.
        </span>
      </div>
    );
  }

  return (
    <div>
      {/* Game info */}
      {game && (
        <div style={{ 
          marginBottom: "1.5rem", 
          padding: "1rem", 
          background: "#f8fafc", 
          borderRadius: "8px",
          fontSize: "0.9rem",
          color: "#64748b"
        }}>
          <strong style={{ color: "#0f172a" }}>
            {game.away_team} @ {game.home_team}
          </strong>
          {" "}— {versions.length} versions
          {activeVersion && ` | Active: v${activeVersion}`}
        </div>
      )}

      {/* Compare controls */}
      <div className={styles.compareControls}>
        <span className={styles.compareLabel}>Compare:</span>
        <select
          className={styles.compareSelect}
          value={compareA ?? ""}
          onChange={(e) => setCompareA(Number(e.target.value))}
        >
          <option value="">Select v</option>
          {versions.map((v) => (
            <option key={v.version_number} value={v.version_number}>
              v{v.version_number}
            </option>
          ))}
        </select>
        <span>vs</span>
        <select
          className={styles.compareSelect}
          value={compareB ?? ""}
          onChange={(e) => setCompareB(Number(e.target.value))}
        >
          <option value="">Select v</option>
          {versions.map((v) => (
            <option key={v.version_number} value={v.version_number}>
              v{v.version_number}
            </option>
          ))}
        </select>
        <button
          className={styles.compareButton}
          onClick={handleCompare}
          disabled={!compareA || !compareB || compareA === compareB || comparing}
        >
          {comparing ? "Comparing..." : "Compare"}
        </button>
      </div>

      {/* Comparison result */}
      {comparison && (
        <div className={styles.diffPanel}>
          <div className={styles.diffHeader}>
            <div className={styles.diffTitle}>
              v{String(comparison.version_a.version_number ?? compareA)} → v{String(comparison.version_b.version_number ?? compareB)}
            </div>
            <div className={styles.diffStats}>
              <span className={styles.diffStat}>
                Hash match: {comparison.hashes_match ? "✅ Yes" : "❌ No"}
              </span>
            </div>
          </div>
          <div className={styles.diffContent}>
            {comparison.hashes_match ? (
              <div style={{ color: "#22c55e" }}>
                Payloads are identical (same hash).
              </div>
            ) : (
              <div>
                <div style={{ marginBottom: "1rem" }}>
                  <strong>Changes:</strong>
                </div>
                {comparison.diff.timeline_changed !== undefined && (
                  <div style={{ color: "#f59e0b" }}>
                    Timeline: {String(comparison.diff.timeline_events_a ?? 0)} → {String(comparison.diff.timeline_events_b ?? 0)} events
                  </div>
                )}
                {comparison.diff.moments_changed !== undefined && (
                  <div style={{ color: "#3b82f6" }}>
                    Moments: {String(comparison.diff.moments_count_a ?? 0)} → {String(comparison.diff.moments_count_b ?? 0)}
                  </div>
                )}
                {comparison.diff.summary_changed !== undefined && (
                  <div style={{ color: "#8b5cf6" }}>
                    Summary: Changed
                  </div>
                )}
                {comparison.diff.moment_diffs !== undefined && (
                  <div style={{ marginTop: "1rem" }}>
                    <strong>Moment-level changes:</strong>
                    <pre style={{ fontSize: "0.8rem", marginTop: "0.5rem" }}>
                      {JSON.stringify(comparison.diff.moment_diffs, null, 2)}
                    </pre>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Versions list */}
      <div className={styles.versionsList}>
        {versions.map((version) => (
          <div
            key={version.version_number}
            className={`${styles.versionCard} ${version.is_active ? styles.versionCardActive : ""}`}
          >
            <div className={styles.versionLeft}>
              <span className={styles.versionNumber}>v{version.version_number}</span>
              <div className={styles.versionInfo}>
                <div style={{ fontWeight: 500, color: "#0f172a" }}>
                  {version.moment_count} moments, {version.event_count} events
                </div>
                <div className={styles.versionMeta}>
                  {formatRelativeTime(version.created_at)} • {version.generation_source || "unknown"}
                  {version.pipeline_run_id && ` • Run #${version.pipeline_run_id}`}
                </div>
              </div>
            </div>
            <div className={styles.versionRight}>
              {version.is_active && (
                <span className={styles.activeBadge}>ACTIVE</span>
              )}
              {version.diff_summary !== null && (
                <div className={styles.diffSummary}>
                  {version.diff_summary.changed === true ? "Changed" : "No change"}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
