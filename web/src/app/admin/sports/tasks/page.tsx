"use client";

import { useCallback, useEffect, useState } from "react";
import styles from "./styles.module.css";
import { listJobRuns, type JobRunResponse } from "@/lib/api/sportsAdmin";

const PHASE_OPTIONS = [
  { value: "", label: "All phases" },
  { value: "update_game_states", label: "Update Game States" },
  { value: "poll_live_pbp", label: "Poll Live PBP" },
  { value: "sync_mainline_odds", label: "Mainline Odds" },
  { value: "sync_prop_odds", label: "Prop Odds" },
  { value: "final_whistle_social", label: "Final Whistle Social" },
  { value: "trigger_flow", label: "Trigger Flow" },
  { value: "daily_sweep", label: "Daily Sweep" },
  { value: "collect_game_social", label: "Game Social" },
];

const STATUS_OPTIONS = [
  { value: "", label: "All statuses" },
  { value: "success", label: "Success" },
  { value: "running", label: "Running" },
  { value: "error", label: "Error" },
];

const AUTO_REFRESH_MS = 30_000;

function formatDuration(seconds: number | null): string {
  if (seconds === null) return "-";
  if (seconds < 1) return "<1s";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const mins = Math.floor(seconds / 60);
  const secs = Math.round(seconds % 60);
  return `${mins}m ${secs}s`;
}

function formatTime(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleTimeString("en-US", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

export default function TaskRunsPage() {
  const [runs, setRuns] = useState<JobRunResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [phase, setPhase] = useState("");
  const [status, setStatus] = useState("");
  const [expandedId, setExpandedId] = useState<number | null>(null);

  const fetchRuns = useCallback(async () => {
    try {
      setError(null);
      const data = await listJobRuns({
        phase: phase || undefined,
        status: status || undefined,
        limit: 100,
      });
      setRuns(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [phase, status]);

  // Initial load + filter changes
  useEffect(() => {
    setLoading(true);
    fetchRuns();
  }, [fetchRuns]);

  // Auto-refresh every 30s
  useEffect(() => {
    const interval = setInterval(fetchRuns, AUTO_REFRESH_MS);
    return () => clearInterval(interval);
  }, [fetchRuns]);

  const getStatusClass = (s: string) => {
    switch (s) {
      case "success":
        return styles.statusSuccess;
      case "running":
        return styles.statusRunning;
      case "error":
        return styles.statusError;
      default:
        return "";
    }
  };

  return (
    <div className={styles.container}>
      <h1>Task Runs</h1>
      <p className={styles.subtitle}>
        Monitor recurring Celery task executions across all workers.
      </p>

      <div className={styles.card}>
        <div className={styles.cardHeader}>
          <h2>Recent Runs</h2>
          <div className={styles.filters}>
            <select value={phase} onChange={(e) => setPhase(e.target.value)}>
              {PHASE_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
            <select value={status} onChange={(e) => setStatus(e.target.value)}>
              {STATUS_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
            <button
              className={styles.refreshButton}
              onClick={fetchRuns}
              disabled={loading}
            >
              {loading ? "Loading..." : "Refresh"}
            </button>
            <span className={styles.autoRefresh}>Auto-refresh: 30s</span>
          </div>
        </div>

        {error && <div className={styles.error}>{error}</div>}

        {!loading && runs.length === 0 && !error && (
          <div className={styles.empty}>No task runs found.</div>
        )}

        {runs.length > 0 && (
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Phase</th>
                <th>Leagues</th>
                <th>Status</th>
                <th>Started</th>
                <th>Duration</th>
                <th>Summary</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => (
                <>
                  <tr
                    key={run.id}
                    className={run.summaryData ? styles.expandable : undefined}
                    onClick={() => {
                      if (run.summaryData) {
                        setExpandedId(expandedId === run.id ? null : run.id);
                      }
                    }}
                  >
                    <td>
                      <span className={styles.phaseBadge}>{run.phase}</span>
                    </td>
                    <td>
                      {run.leagues.map((lg) => (
                        <span key={lg} className={styles.leagueBadge}>
                          {lg}
                        </span>
                      ))}
                    </td>
                    <td>
                      <span
                        className={`${styles.statusPill} ${getStatusClass(run.status)}`}
                      >
                        {run.status}
                      </span>
                    </td>
                    <td>
                      {formatDate(run.startedAt)} {formatTime(run.startedAt)}
                    </td>
                    <td className={styles.durationCell}>
                      {formatDuration(run.durationSeconds)}
                    </td>
                    <td>
                      {run.errorSummary
                        ? run.errorSummary.slice(0, 60)
                        : run.summaryData
                          ? "Click to expand"
                          : "-"}
                    </td>
                  </tr>
                  {expandedId === run.id && run.summaryData && (
                    <tr key={`${run.id}-detail`} className={styles.summaryRow}>
                      <td colSpan={6}>
                        <pre className={styles.summaryPre}>
                          {JSON.stringify(run.summaryData, null, 2)}
                        </pre>
                      </td>
                    </tr>
                  )}
                </>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
