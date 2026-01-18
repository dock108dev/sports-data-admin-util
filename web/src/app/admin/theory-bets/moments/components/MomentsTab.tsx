"use client";

import { useState, useEffect, useCallback } from "react";
import styles from "../styles.module.css";
import { MomentCard } from "./MomentCard";
import {
  fetchLatestMomentTrace,
  type LatestTraceResponse,
  type MomentTraceDetail,
} from "@/lib/api/sportsAdmin";
import type { GameSummary } from "@/lib/api/sportsAdmin";

interface MomentsTabProps {
  gameId: number | null;
  game: GameSummary | null;
  loading: boolean;
}

/**
 * Tab for inspecting moments with full tracing.
 * Shows all moments for a game with expandable trace details.
 */
export function MomentsTab({ gameId, game, loading: parentLoading }: MomentsTabProps) {
  const [trace, setTrace] = useState<LatestTraceResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedMomentId, setExpandedMomentId] = useState<string | null>(null);

  const loadTrace = useCallback(async () => {
    if (!gameId) return;
    setLoading(true);
    setError(null);
    try {
      const data = await fetchLatestMomentTrace(gameId);
      setTrace(data);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      // Don't show error if no trace exists yet
      if (message.includes("404") || message.includes("No pipeline run")) {
        setTrace(null);
      } else {
        setError(message);
      }
    } finally {
      setLoading(false);
    }
  }, [gameId]);

  useEffect(() => {
    if (gameId) {
      loadTrace();
      setExpandedMomentId(null);
    }
  }, [gameId, loadTrace]);

  const toggleMoment = (momentId: string) => {
    setExpandedMomentId((prev) => (prev === momentId ? null : momentId));
  };

  // Build a map of moment traces by ID for quick lookup
  const traceMap = new Map<string, MomentTraceDetail>();
  if (trace?.moment_traces) {
    for (const t of trace.moment_traces) {
      traceMap.set(t.moment_id, t);
    }
  }

  // Get final moments only (not rejected or merged)
  const finalMoments = trace?.moment_traces?.filter((t) => t.is_final) ?? [];

  if (parentLoading || loading) {
    return <div className={styles.loading}>Loading moments...</div>;
  }

  if (!gameId) {
    return <div className={styles.empty}>Select a game to view moments.</div>;
  }

  if (error) {
    return <div className={styles.error}>{error}</div>;
  }

  if (!trace) {
    return (
      <div className={styles.empty}>
        No moment trace found for this game.
        <br />
        <span style={{ fontSize: "0.85rem", color: "#94a3b8" }}>
          Moments may need to be generated first.
        </span>
      </div>
    );
  }

  return (
    <div>
      {/* Stats */}
      <div className={styles.stats}>
        <div className={styles.statCard}>
          <div className={styles.statValue}>{trace.summary.final_moment_count}</div>
          <div className={styles.statLabel}>Final Moments</div>
        </div>
        <div className={styles.statCard}>
          <div className={styles.statValue}>{trace.summary.initial_moment_count}</div>
          <div className={styles.statLabel}>Initial</div>
        </div>
        <div className={styles.statCard}>
          <div className={styles.statValue}>{trace.summary.merged_count}</div>
          <div className={styles.statLabel}>Merged</div>
        </div>
        <div className={styles.statCard}>
          <div className={styles.statValue}>{trace.summary.rejected_count}</div>
          <div className={styles.statLabel}>Rejected</div>
        </div>
        <div className={styles.statCard}>
          <div className={styles.statValue}>{trace.summary.pbp_event_count}</div>
          <div className={styles.statLabel}>PBP Events</div>
        </div>
        <div className={styles.statCard}>
          <div className={styles.statValue}>{trace.summary.budget}</div>
          <div className={styles.statLabel}>Budget</div>
        </div>
      </div>

      {/* Game info header */}
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
          {" "}— {game.away_score ?? 0} - {game.home_score ?? 0}
          {" "}| Run: {trace.run_uuid.slice(0, 8)}
        </div>
      )}

      {/* Moments list */}
      <div className={styles.momentsList}>
        {finalMoments.length === 0 ? (
          <div className={styles.empty}>No moments generated.</div>
        ) : (
          finalMoments.map((momentTrace) => (
            <MomentCard
              key={momentTrace.moment_id}
              trace={momentTrace}
              isExpanded={expandedMomentId === momentTrace.moment_id}
              onToggle={() => toggleMoment(momentTrace.moment_id)}
              gameId={gameId}
            />
          ))
        )}
      </div>
    </div>
  );
}
