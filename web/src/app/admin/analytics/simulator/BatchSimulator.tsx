"use client";

import { useState, useEffect, useCallback } from "react";
import { AdminCard, AdminTable } from "@/components/admin";
import {
  startBatchSimulation,
  listBatchSimJobs,
  type BatchSimJob,
} from "@/lib/api/analytics";
import styles from "../analytics.module.css";

function BatchStatusBadge({ status }: { status: string }) {
  const colors: Record<string, { bg: string; text: string }> = {
    pending: { bg: "#fef3c7", text: "#92400e" },
    queued: { bg: "#dbeafe", text: "#1e40af" },
    running: { bg: "#dbeafe", text: "#1e40af" },
    completed: { bg: "#dcfce7", text: "#166534" },
    failed: { bg: "#fee2e2", text: "#991b1b" },
  };
  const c = colors[status] || { bg: "#f3f4f6", text: "#374151" };
  return (
    <span
      style={{
        background: c.bg,
        color: c.text,
        padding: "2px 8px",
        borderRadius: "4px",
        fontSize: "0.8rem",
        fontWeight: 500,
      }}
    >
      {status}
    </span>
  );
}

export function BatchSimulator() {
  const [sport, setSport] = useState("mlb");
  const [probabilityMode, setProbabilityMode] = useState("ml");
  const [iterations, setIterations] = useState(5000);
  const [rollingWindow, setRollingWindow] = useState(30);
  const [dateStart, setDateStart] = useState("");
  const [dateEnd, setDateEnd] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [jobs, setJobs] = useState<BatchSimJob[]>([]);
  const [expandedJob, setExpandedJob] = useState<number | null>(null);

  const refresh = useCallback(async () => {
    try {
      const res = await listBatchSimJobs(sport);
      setJobs(res.jobs);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load batch jobs");
    }
  }, [sport]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // Poll for in-progress jobs
  useEffect(() => {
    const active = jobs.filter(
      (j) => j.status === "pending" || j.status === "queued" || j.status === "running",
    );
    if (active.length === 0) return;
    const interval = setInterval(refresh, 5000);
    return () => clearInterval(interval);
  }, [jobs, refresh]);

  const handleSubmit = async () => {
    setSubmitting(true);
    setError(null);
    setMessage(null);
    try {
      const res = await startBatchSimulation({
        sport,
        probability_mode: probabilityMode,
        iterations,
        rolling_window: rollingWindow,
        date_start: dateStart || undefined,
        date_end: dateEnd || undefined,
      });
      setMessage(`Batch sim job #${res.job.id} submitted`);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <>
      <AdminCard title="Simulate Upcoming Games" subtitle="Run Monte Carlo sims on all scheduled/pregame games">
        <div className={styles.formRow}>
          <div className={styles.formGroup}>
            <label>Sport</label>
            <select value={sport} onChange={(e) => setSport(e.target.value)}>
              <option value="mlb">MLB</option>
            </select>
          </div>
          <div className={styles.formGroup}>
            <label>Probability Mode</label>
            <select value={probabilityMode} onChange={(e) => setProbabilityMode(e.target.value)}>
              <option value="ml">ML Model</option>
              <option value="rule_based">Rule Based</option>
              <option value="ensemble">Ensemble</option>
            </select>
          </div>
          <div className={styles.formGroup}>
            <label>Iterations</label>
            <input
              type="number"
              value={iterations}
              onChange={(e) => setIterations(Math.max(100, parseInt(e.target.value) || 100))}
              min={100}
              max={50000}
            />
          </div>
          <div className={styles.formGroup}>
            <label>Rolling Window: {rollingWindow}</label>
            <input
              type="range"
              min={5}
              max={80}
              step={5}
              value={rollingWindow}
              onChange={(e) => setRollingWindow(parseInt(e.target.value))}
            />
          </div>
        </div>
        <div className={styles.formRow}>
          <div className={styles.formGroup}>
            <label>Date Start (optional)</label>
            <input type="date" value={dateStart} onChange={(e) => setDateStart(e.target.value)} />
          </div>
          <div className={styles.formGroup}>
            <label>Date End (optional)</label>
            <input type="date" value={dateEnd} onChange={(e) => setDateEnd(e.target.value)} />
          </div>
        </div>

        {error && <div className={styles.error}>{error}</div>}
        {message && <div className={styles.success}>{message}</div>}

        <button
          className={`${styles.btn} ${styles.btnPrimary}`}
          onClick={handleSubmit}
          disabled={submitting}
          style={{ marginTop: "0.5rem" }}
        >
          {submitting ? "Submitting..." : "Simulate Upcoming Games"}
        </button>
      </AdminCard>

      {/* Job History */}
      {jobs.length > 0 && (
        <AdminCard title="Batch Simulation History">
          <AdminTable headers={["ID", "Mode", "Iterations", "Window", "Status", "Games", "Created", ""]}>
            {jobs.map((job) => (
              <tr key={job.id}>
                <td>#{job.id}</td>
                <td>{job.probability_mode}</td>
                <td>{job.iterations.toLocaleString()}</td>
                <td>{job.rolling_window}</td>
                <td><BatchStatusBadge status={job.status} /></td>
                <td>{job.game_count ?? "-"}</td>
                <td style={{ fontSize: "0.85rem" }}>
                  {job.created_at ? new Date(job.created_at).toLocaleString() : "-"}
                </td>
                <td>
                  {job.results && job.results.length > 0 && (
                    <button
                      className={styles.btn}
                      onClick={() => setExpandedJob(expandedJob === job.id ? null : job.id)}
                      style={{ fontSize: "0.8rem", padding: "2px 8px" }}
                    >
                      {expandedJob === job.id ? "Hide" : "Results"}
                    </button>
                  )}
                  {job.error_message && (
                    <span style={{ color: "#ef4444", fontSize: "0.8rem", marginLeft: "0.5rem" }} title={job.error_message}>
                      Error
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </AdminTable>

          {/* Expanded game results */}
          {expandedJob && (() => {
            const job = jobs.find((j) => j.id === expandedJob);
            if (!job?.results) return null;
            return (
              <div style={{ marginTop: "1rem" }}>
                <h4 style={{ marginBottom: "0.5rem" }}>
                  Results for Batch #{job.id}
                  <span style={{ fontWeight: "normal", fontSize: "0.85rem", marginLeft: "0.5rem" }}>
                    ({job.game_count} games)
                  </span>
                </h4>
                <div style={{ maxHeight: "500px", overflow: "auto" }}>
                  <AdminTable headers={["Date", "Matchup", "Home Win %", "Away Win %", "Avg Score", "Source", "Profiles"]}>
                    {job.results.map((g, i) => (
                      <tr key={i}>
                        <td style={{ fontSize: "0.85rem" }}>{g.game_date}</td>
                        <td style={{ fontWeight: 500 }}>
                          {g.away_team} @ {g.home_team}
                        </td>
                        <td style={{ color: g.home_win_probability > 0.5 ? "#22c55e" : undefined }}>
                          {(g.home_win_probability * 100).toFixed(1)}%
                        </td>
                        <td style={{ color: g.away_win_probability > 0.5 ? "#22c55e" : undefined }}>
                          {(g.away_win_probability * 100).toFixed(1)}%
                        </td>
                        <td style={{ fontSize: "0.85rem" }}>
                          {g.average_home_score.toFixed(1)} - {g.average_away_score.toFixed(1)}
                        </td>
                        <td style={{ fontSize: "0.8rem" }}>{g.probability_source}</td>
                        <td>{g.has_profiles ? "Yes" : "No"}</td>
                      </tr>
                    ))}
                  </AdminTable>
                </div>
              </div>
            );
          })()}
        </AdminCard>
      )}
    </>
  );
}
