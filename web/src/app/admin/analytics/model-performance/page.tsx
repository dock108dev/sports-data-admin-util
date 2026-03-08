"use client";

import { useState, useCallback, useEffect } from "react";
import { AdminCard, AdminTable } from "@/components/admin";
import {
  getCalibrationReport,
  listPredictionOutcomes,
  triggerRecordOutcomes,
  listDegradationAlerts,
  triggerDegradationCheck,
  acknowledgeDegradationAlert,
  type CalibrationReport,
  type PredictionOutcome,
  type DegradationAlert,
} from "@/lib/api/analytics";
import styles from "../analytics.module.css";

export default function ModelPerformancePage() {
  const [sport, setSport] = useState<string>("");
  const [data, setData] = useState<CalibrationReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleLoad = useCallback(() => {
    setLoading(true);
    setError(null);
    getCalibrationReport(sport || undefined)
      .then(setData)
      .catch((err) => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => setLoading(false));
  }, [sport]);

  return (
    <div className={styles.container}>
      <header className={styles.pageHeader}>
        <h1 className={styles.pageTitle}>Model Performance</h1>
        <p className={styles.pageSubtitle}>
          Prediction accuracy, calibration metrics, and model bias tracking
        </p>
      </header>

      <div className={styles.formRow} style={{ marginBottom: "1rem" }}>
        <div className={styles.formGroup}>
          <label>Sport</label>
          <select value={sport} onChange={(e) => setSport(e.target.value)}>
            <option value="">All Sports</option>
            <option value="mlb">MLB</option>
          </select>
        </div>
        <button
          className={`${styles.btn} ${styles.btnPrimary}`}
          onClick={handleLoad}
          disabled={loading}
        >
          {loading ? "Loading..." : "Load Metrics"}
        </button>
      </div>

      {loading && <div className={styles.loading}>Loading metrics...</div>}
      {error && <div className={styles.error}>{error}</div>}

      {data && !loading && (
        <div className={styles.resultsSection}>
          <AdminCard
            title="Overview"
            subtitle={`Based on ${data.total_predictions} resolved predictions`}
          >
            {data.total_predictions === 0 ? (
              <p style={{ color: "var(--text-muted)" }}>
                No resolved predictions yet. Run a batch simulation, then record outcomes after games finish.
              </p>
            ) : (
              <>
                <div className={styles.statsRow}>
                  <div className={styles.statBox}>
                    <div className={styles.statValue}>
                      {data.total_predictions}
                    </div>
                    <div className={styles.statLabel}>Resolved</div>
                  </div>
                  <div className={styles.statBox}>
                    <div className={styles.statValue}>
                      {(data.accuracy * 100).toFixed(1)}%
                    </div>
                    <div className={styles.statLabel}>Winner Accuracy</div>
                  </div>
                  <div className={styles.statBox}>
                    <div className={styles.statValue}>
                      {data.brier_score.toFixed(4)}
                    </div>
                    <div className={styles.statLabel}>Brier Score</div>
                  </div>
                </div>

                <div className={styles.statsRow}>
                  <div className={styles.statBox}>
                    <div className={styles.statValue}>
                      {data.avg_home_score_error.toFixed(1)}
                    </div>
                    <div className={styles.statLabel}>Avg Home Score Error</div>
                  </div>
                  <div className={styles.statBox}>
                    <div className={styles.statValue}>
                      {data.avg_away_score_error.toFixed(1)}
                    </div>
                    <div className={styles.statLabel}>Avg Away Score Error</div>
                  </div>
                  <div className={styles.statBox}>
                    <div className={styles.statValue}>
                      {data.home_bias > 0 ? "+" : ""}
                      {(data.home_bias * 100).toFixed(1)}%
                    </div>
                    <div className={styles.statLabel}>Home Win Bias</div>
                  </div>
                </div>
              </>
            )}
          </AdminCard>
        </div>
      )}

      {/* Degradation Alerts */}
      <DegradationAlertsPanel sport={sport || undefined} />

      {/* DB-backed Calibration from batch simulations */}
      <CalibrationPanel sport={sport || undefined} />
    </div>
  );
}


function CalibrationPanel({ sport }: { sport?: string }) {
  const [report, setReport] = useState<CalibrationReport | null>(null);
  const [outcomes, setOutcomes] = useState<PredictionOutcome[]>([]);
  const [loading, setLoading] = useState(false);
  const [recording, setRecording] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [rep, oc] = await Promise.all([
        getCalibrationReport(sport),
        listPredictionOutcomes({ sport, limit: 200 }),
      ]);
      setReport(rep);
      setOutcomes(oc.outcomes);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load calibration data");
    } finally {
      setLoading(false);
    }
  }, [sport]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const handleRecordOutcomes = async () => {
    setRecording(true);
    setMessage(null);
    try {
      await triggerRecordOutcomes();
      setMessage("Outcome recording task dispatched. Refresh in a few seconds.");
      setTimeout(refresh, 5000);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : String(err));
    } finally {
      setRecording(false);
    }
  };

  const resolved = outcomes.filter((o) => o.outcome_recorded_at !== null);
  const pending = outcomes.filter((o) => o.outcome_recorded_at === null);

  return (
    <>
      {error && <div className={styles.error}>{error}</div>}
      <AdminCard
        title="Prediction Calibration (Batch Sims)"
        subtitle="Tracks batch simulation predictions vs actual game outcomes"
      >
        <div className={styles.formRow} style={{ marginBottom: "1rem" }}>
          <button
            className={`${styles.btn} ${styles.btnPrimary}`}
            onClick={handleRecordOutcomes}
            disabled={recording}
          >
            {recording ? "Recording..." : "Record Outcomes Now"}
          </button>
          <button className={styles.btn} onClick={refresh} disabled={loading}>
            {loading ? "Loading..." : "Refresh"}
          </button>
        </div>

        {message && <div className={styles.success}>{message}</div>}

        {report && report.total_predictions > 0 && (
          <div className={styles.statsRow}>
            <div className={styles.statBox}>
              <div className={styles.statValue}>{report.total_predictions}</div>
              <div className={styles.statLabel}>Resolved Predictions</div>
            </div>
            <div className={styles.statBox}>
              <div className={styles.statValue}>
                {(report.accuracy * 100).toFixed(1)}%
              </div>
              <div className={styles.statLabel}>Winner Accuracy</div>
            </div>
            <div className={styles.statBox}>
              <div className={styles.statValue}>
                {report.brier_score.toFixed(4)}
              </div>
              <div className={styles.statLabel}>Brier Score</div>
            </div>
            <div className={styles.statBox}>
              <div className={styles.statValue}>
                {report.avg_home_score_error.toFixed(1)}
              </div>
              <div className={styles.statLabel}>Avg Home Score Err</div>
            </div>
            <div className={styles.statBox}>
              <div className={styles.statValue}>
                {report.home_bias > 0 ? "+" : ""}
                {(report.home_bias * 100).toFixed(1)}%
              </div>
              <div className={styles.statLabel}>Home Bias</div>
            </div>
          </div>
        )}

        {report && report.total_predictions === 0 && (
          <p style={{ color: "var(--text-muted)" }}>
            No resolved predictions yet. Run a batch simulation, then record outcomes after games finish.
          </p>
        )}
      </AdminCard>

      {/* Pending predictions */}
      {pending.length > 0 && (
        <AdminCard title="Pending Predictions" subtitle={`${pending.length} awaiting game outcomes`}>
          <AdminTable headers={["Game", "Matchup", "Home WP", "Mode", "Created"]}>
            {pending.slice(0, 50).map((o) => (
              <tr key={o.id}>
                <td style={{ fontSize: "0.85rem" }}>{o.game_date || `#${o.game_id}`}</td>
                <td>{o.away_team} @ {o.home_team}</td>
                <td>{(o.predicted_home_wp * 100).toFixed(1)}%</td>
                <td style={{ fontSize: "0.85rem" }}>{o.probability_mode}</td>
                <td style={{ fontSize: "0.85rem" }}>
                  {o.created_at ? new Date(o.created_at).toLocaleDateString() : "-"}
                </td>
              </tr>
            ))}
          </AdminTable>
        </AdminCard>
      )}

      {/* Resolved predictions */}
      {resolved.length > 0 && (
        <AdminCard title="Resolved Predictions" subtitle={`${resolved.length} with outcomes recorded`}>
          <div style={{ maxHeight: "400px", overflow: "auto" }}>
            <AdminTable headers={["Game", "Matchup", "Pred WP", "Actual", "Result", "Brier", "Score"]}>
              {resolved.map((o) => (
                <tr
                  key={o.id}
                  style={{ background: o.correct_winner ? undefined : "rgba(239, 68, 68, 0.08)" }}
                >
                  <td style={{ fontSize: "0.85rem" }}>{o.game_date || `#${o.game_id}`}</td>
                  <td>{o.away_team} @ {o.home_team}</td>
                  <td>{(o.predicted_home_wp * 100).toFixed(1)}%</td>
                  <td>{o.home_win_actual ? "Home" : "Away"}</td>
                  <td>
                    <span style={{
                      color: o.correct_winner ? "#22c55e" : "#ef4444",
                      fontWeight: "bold",
                      fontSize: "0.85rem",
                    }}>
                      {o.correct_winner ? "Correct" : "Wrong"}
                    </span>
                  </td>
                  <td style={{ fontSize: "0.85rem" }}>{o.brier_score?.toFixed(4) ?? "-"}</td>
                  <td style={{ fontSize: "0.85rem" }}>
                    {o.actual_home_score != null && o.actual_away_score != null
                      ? `${o.actual_home_score}-${o.actual_away_score}`
                      : "-"}
                  </td>
                </tr>
              ))}
            </AdminTable>
          </div>
        </AdminCard>
      )}
    </>
  );
}


function DegradationAlertsPanel({ sport }: { sport?: string }) {
  const [alerts, setAlerts] = useState<DegradationAlert[]>([]);
  const [loading, setLoading] = useState(false);
  const [checking, setChecking] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await listDegradationAlerts({ sport, limit: 20 });
      setAlerts(res.alerts);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load degradation alerts");
    } finally {
      setLoading(false);
    }
  }, [sport]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const handleCheck = async () => {
    setChecking(true);
    setMessage(null);
    try {
      await triggerDegradationCheck(sport || "mlb");
      setMessage("Degradation check dispatched. Refresh in a few seconds.");
      setTimeout(refresh, 5000);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : String(err));
    } finally {
      setChecking(false);
    }
  };

  const handleAcknowledge = async (id: number) => {
    try {
      await acknowledgeDegradationAlert(id);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to acknowledge alert");
    }
  };

  const unacknowledged = alerts.filter((a) => !a.acknowledged);
  const hasActiveAlerts = unacknowledged.length > 0;

  const severityColors: Record<string, { bg: string; text: string; border: string }> = {
    critical: { bg: "#fee2e2", text: "#991b1b", border: "#ef4444" },
    warning: { bg: "#fef3c7", text: "#92400e", border: "#f59e0b" },
    info: { bg: "#dbeafe", text: "#1e40af", border: "#3b82f6" },
  };

  return (
    <>
    {error && <div className={styles.error}>{error}</div>}
    <AdminCard
      title={hasActiveAlerts ? "Model Degradation Alerts" : "Model Health"}
      subtitle={hasActiveAlerts
        ? `${unacknowledged.length} active alert${unacknowledged.length > 1 ? "s" : ""}`
        : "No active degradation alerts"
      }
    >
      <div className={styles.formRow} style={{ marginBottom: "1rem" }}>
        <button
          className={`${styles.btn} ${styles.btnPrimary}`}
          onClick={handleCheck}
          disabled={checking}
        >
          {checking ? "Checking..." : "Run Degradation Check"}
        </button>
        <button className={styles.btn} onClick={refresh} disabled={loading}>
          {loading ? "Loading..." : "Refresh"}
        </button>
      </div>

      {message && <div className={styles.success}>{message}</div>}

      {!hasActiveAlerts && alerts.length === 0 && (
        <p style={{ color: "var(--text-muted)" }}>
          No degradation alerts. Run a check after recording enough prediction outcomes.
        </p>
      )}

      {!hasActiveAlerts && alerts.length > 0 && (
        <p style={{ color: "#22c55e", fontWeight: 500 }}>
          Model is healthy. All previous alerts have been acknowledged.
        </p>
      )}

      {alerts.map((alert) => {
        const colors = severityColors[alert.severity] || severityColors.info;
        return (
          <div
            key={alert.id}
            style={{
              background: colors.bg,
              border: `1px solid ${colors.border}`,
              borderRadius: "8px",
              padding: "1rem",
              marginBottom: "0.75rem",
              opacity: alert.acknowledged ? 0.6 : 1,
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.5rem" }}>
              <div>
                <span style={{
                  color: colors.text,
                  fontWeight: 700,
                  fontSize: "0.9rem",
                  textTransform: "uppercase",
                }}>
                  {alert.severity}
                </span>
                <span style={{ color: colors.text, fontSize: "0.85rem", marginLeft: "0.75rem" }}>
                  {alert.sport.toUpperCase()} — {alert.alert_type.replace(/_/g, " ")}
                </span>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                <span style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>
                  {alert.created_at ? new Date(alert.created_at).toLocaleString() : ""}
                </span>
                {!alert.acknowledged && (
                  <button
                    className={styles.btn}
                    onClick={() => handleAcknowledge(alert.id)}
                    style={{ fontSize: "0.75rem", padding: "2px 8px" }}
                  >
                    Acknowledge
                  </button>
                )}
                {alert.acknowledged && (
                  <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>Acknowledged</span>
                )}
              </div>
            </div>

            <p style={{ color: colors.text, fontSize: "0.85rem", margin: "0 0 0.5rem" }}>
              {alert.message}
            </p>

            <div style={{ display: "flex", gap: "1.5rem", fontSize: "0.8rem", color: colors.text }}>
              <span>Baseline Brier: <strong>{alert.baseline_brier.toFixed(4)}</strong></span>
              <span>Recent Brier: <strong>{alert.recent_brier.toFixed(4)}</strong></span>
              <span>Delta: <strong>+{alert.delta_brier.toFixed(4)}</strong></span>
              <span>Accuracy: <strong>{(alert.baseline_accuracy * 100).toFixed(1)}%</strong> → <strong>{(alert.recent_accuracy * 100).toFixed(1)}%</strong></span>
            </div>
          </div>
        );
      })}
    </AdminCard>
    </>
  );
}
