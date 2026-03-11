"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { AdminCard, AdminTable } from "@/components/admin";
import {
  listRegisteredModels,
  activateModel,
  compareModels,
  getCalibrationReport,
  listPredictionOutcomes,
  triggerRecordOutcomes,
  listDegradationAlerts,
  triggerDegradationCheck,
  acknowledgeDegradationAlert,
  type RegisteredModel,
  type ModelComparison,
  type CalibrationReport,
  type PredictionOutcome,
  type DegradationAlert,
} from "@/lib/api/analytics";
import { CalibrationChart } from "../charts";
import { LoadoutsPanel } from "../workbench/LoadoutsPanel";
import { TrainingPanel } from "../workbench/TrainingPanel";
import { EnsemblePanel } from "../workbench/EnsemblePanel";
import styles from "../analytics.module.css";

type Tab = "registry" | "loadouts" | "training" | "performance";

export default function ModelsPage() {
  const [tab, setTab] = useState<Tab>("registry");

  return (
    <div className={styles.container}>
      <header className={styles.pageHeader}>
        <h1 className={styles.pageTitle}>Models</h1>
        <p className={styles.pageSubtitle}>
          Full model lifecycle — loadouts, training, registry, and performance
        </p>
      </header>

      <div style={{ display: "flex", gap: "0.5rem", marginBottom: "1.5rem" }}>
        {([
          { key: "registry", label: "Registry" },
          { key: "loadouts", label: "Loadouts" },
          { key: "training", label: "Training" },
          { key: "performance", label: "Performance" },
        ] as const).map((t) => (
          <button
            key={t.key}
            className={`${styles.btn} ${tab === t.key ? styles.btnPrimary : ""}`}
            onClick={() => setTab(t.key)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "registry" && <RegistryPanel />}
      {tab === "loadouts" && <LoadoutsPanel />}
      {tab === "training" && <TrainingSection />}
      {tab === "performance" && <PerformanceSection />}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Training Section — TrainingPanel + EnsemblePanel                  */
/* ------------------------------------------------------------------ */

function TrainingSection() {
  return (
    <>
      <TrainingPanel />
      <div style={{ marginTop: "1.5rem" }}>
        <EnsemblePanel />
      </div>
    </>
  );
}

/* ------------------------------------------------------------------ */
/*  Registry Panel — migrated from the original ModelsPage            */
/* ------------------------------------------------------------------ */

type SortKey = "version" | "accuracy" | "log_loss" | "brier_score" | "created_at";

function RegistryPanel() {
  const [models, setModels] = useState<RegisteredModel[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activating, setActivating] = useState<string | null>(null);

  // Filters
  const [sportFilter, setSportFilter] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [activeOnly, setActiveOnly] = useState(false);

  // Sorting
  const [sortBy, setSortBy] = useState<SortKey>("version");
  const [sortDesc, setSortDesc] = useState(true);

  // Comparison
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [comparison, setComparison] = useState<ModelComparison | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await listRegisteredModels(
        sportFilter || undefined,
        typeFilter || undefined,
      );
      setModels(res.models);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [sportFilter, typeFilter]);

  useEffect(() => {
    load();
  }, [load]);

  async function handleActivate(m: RegisteredModel) {
    setActivating(m.model_id);
    try {
      const res = await activateModel(m.sport, m.model_type, m.model_id);
      if (res.status === "error") {
        setError(res.message || "Activation failed");
      } else {
        await load();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setActivating(null);
    }
  }

  function toggleSelect(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
    setComparison(null);
  }

  async function handleCompare() {
    const ids = Array.from(selected);
    if (ids.length < 2) return;
    const first = models.find((m) => m.model_id === ids[0]);
    if (!first) return;
    try {
      const res = await compareModels(first.sport, first.model_type, ids);
      setComparison(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  // Apply client-side filtering and sorting
  let filtered = activeOnly ? models.filter((m) => m.active) : models;
  filtered = [...filtered].sort((a, b) => {
    let va: number | string;
    let vb: number | string;
    if (sortBy === "version" || sortBy === "created_at") {
      va = a[sortBy] ?? "";
      vb = b[sortBy] ?? "";
    } else {
      va = a.metrics?.[sortBy] ?? (sortDesc ? -Infinity : Infinity);
      vb = b.metrics?.[sortBy] ?? (sortDesc ? -Infinity : Infinity);
    }
    if (va < vb) return sortDesc ? 1 : -1;
    if (va > vb) return sortDesc ? -1 : 1;
    return 0;
  });

  // Group by sport / model_type
  const grouped = filtered.reduce<Record<string, RegisteredModel[]>>((acc, m) => {
    const key = `${m.sport} / ${m.model_type}`;
    if (!acc[key]) acc[key] = [];
    acc[key].push(m);
    return acc;
  }, {});

  // Unique sports and types for filter dropdowns
  const sports = [...new Set(models.map((m) => m.sport))];
  const types = [...new Set(models.map((m) => m.model_type))];

  function sortHeader(label: string, key: SortKey) {
    const active = sortBy === key;
    return (
      <span
        style={{ cursor: "pointer", textDecoration: active ? "underline" : "none" }}
        onClick={() => {
          if (active) setSortDesc(!sortDesc);
          else { setSortBy(key); setSortDesc(true); }
        }}
      >
        {label}{active ? (sortDesc ? " \u25BC" : " \u25B2") : ""}
      </span>
    );
  }

  return (
    <>
      {/* Filters */}
      <div className={styles.formRow} style={{ marginBottom: "1rem" }}>
        <div className={styles.formGroup}>
          <label>Sport</label>
          <select value={sportFilter} onChange={(e) => setSportFilter(e.target.value)}>
            <option value="">All</option>
            {sports.map((s) => <option key={s} value={s}>{s.toUpperCase()}</option>)}
          </select>
        </div>
        <div className={styles.formGroup}>
          <label>Model Type</label>
          <select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)}>
            <option value="">All</option>
            {types.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        </div>
        <label style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <input type="checkbox" checked={activeOnly} onChange={(e) => setActiveOnly(e.target.checked)} />
          Active only
        </label>
        {selected.size >= 2 && (
          <button className={`${styles.btn} ${styles.btnPrimary}`} onClick={handleCompare}>
            Compare ({selected.size})
          </button>
        )}
      </div>

      {error && <div className={styles.error}>{error}</div>}
      {loading && <p>Loading models...</p>}

      {!loading && filtered.length === 0 && (
        <AdminCard title="No Models Found">
          <p>Train a model using the training pipeline to see it here.</p>
        </AdminCard>
      )}

      {Object.entries(grouped).map(([group, groupModels]) => {
        const activeModel = groupModels.find((m) => m.active);
        return (
          <AdminCard
            key={group}
            title={group.toUpperCase()}
            subtitle={`${groupModels.length} version(s)${activeModel ? ` — Active: ${activeModel.model_id}` : ""}`}
          >
            <AdminTable
              headers={[
                "",
                "Model ID",
                sortHeader("Version", "version"),
                sortHeader("Accuracy", "accuracy"),
                sortHeader("Log Loss", "log_loss"),
                sortHeader("Brier Score", "brier_score"),
                sortHeader("Created", "created_at"),
                "Status",
                "",
              ]}
            >
              {groupModels.map((m) => (
                <tr key={m.model_id}>
                  <td>
                    <input
                      type="checkbox"
                      checked={selected.has(m.model_id)}
                      onChange={() => toggleSelect(m.model_id)}
                    />
                  </td>
                  <td>
                    <Link
                      href={`/admin/analytics/models/${encodeURIComponent(m.model_id)}`}
                      style={{ textDecoration: "underline" }}
                    >
                      {m.model_id}
                    </Link>
                  </td>
                  <td>v{m.version}</td>
                  <td>{m.metrics?.accuracy != null ? m.metrics.accuracy.toFixed(3) : "-"}</td>
                  <td>{m.metrics?.log_loss != null ? m.metrics.log_loss.toFixed(3) : "-"}</td>
                  <td>{m.metrics?.brier_score != null ? m.metrics.brier_score.toFixed(3) : "-"}</td>
                  <td>{m.created_at ? new Date(m.created_at).toLocaleDateString() : "-"}</td>
                  <td>
                    {m.active ? (
                      <span style={{ background: "#22c55e", color: "#fff", padding: "2px 8px", borderRadius: "4px", fontSize: "0.8rem" }}>
                        Active
                      </span>
                    ) : ""}
                  </td>
                  <td>
                    {!m.active && (
                      <button
                        className={`${styles.btn} ${styles.btnPrimary}`}
                        onClick={() => handleActivate(m)}
                        disabled={activating === m.model_id}
                        style={{ fontSize: "0.8rem", padding: "4px 8px" }}
                      >
                        {activating === m.model_id ? "..." : "Activate"}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </AdminTable>
          </AdminCard>
        );
      })}

      {/* Comparison Section */}
      {comparison && comparison.models.length >= 2 && (
        <AdminCard title="Model Comparison" subtitle={`${comparison.sport.toUpperCase()} / ${comparison.model_type}`}>
          <AdminTable
            headers={["Metric", ...comparison.models.map((m) => m.model_id)]}
          >
            {(() => {
              const metricKeys = new Set<string>();
              comparison.models.forEach((m) => {
                Object.keys(m.metrics).forEach((k) => {
                  if (typeof m.metrics[k] === "number") metricKeys.add(k);
                });
              });
              const better = comparison.comparison?.better_model;
              return Array.from(metricKeys).map((key) => (
                <tr key={key}>
                  <td>{key}</td>
                  {comparison.models.map((m) => {
                    const val = m.metrics[key];
                    const isBetter = better === m.model_id;
                    return (
                      <td key={m.model_id} style={isBetter ? { fontWeight: "bold" } : {}}>
                        {val != null ? (typeof val === "number" ? val.toFixed(4) : String(val)) : "-"}
                      </td>
                    );
                  })}
                </tr>
              ));
            })()}
          </AdminTable>
          {comparison.comparison && (
            <p style={{ marginTop: "0.5rem", fontSize: "0.9rem" }}>
              Better model: <strong>{comparison.comparison.better_model}</strong>
            </p>
          )}
        </AdminCard>
      )}
    </>
  );
}

/* ------------------------------------------------------------------ */
/*  Performance Section — calibration + degradation alerts            */
/* ------------------------------------------------------------------ */

function PerformanceSection() {
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
    <>
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
    </>
  );
}

/* ------------------------------------------------------------------ */
/*  Calibration Panel                                                 */
/* ------------------------------------------------------------------ */

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

      {/* Calibration curve from resolved predictions */}
      {resolved.length >= 5 && (
        <AdminCard title="Calibration Curve" subtitle="Predicted win probability vs actual win rate by bucket">
          <CalibrationChart
            data={(() => {
              const buckets = [
                { min: 0, max: 0.3, label: "0-30%" },
                { min: 0.3, max: 0.4, label: "30-40%" },
                { min: 0.4, max: 0.5, label: "40-50%" },
                { min: 0.5, max: 0.6, label: "50-60%" },
                { min: 0.6, max: 0.7, label: "60-70%" },
                { min: 0.7, max: 1.01, label: "70-100%" },
              ];
              return buckets.map((b) => {
                const inBucket = resolved.filter(
                  (o) => o.predicted_home_wp >= b.min && o.predicted_home_wp < b.max,
                );
                const avgPred = inBucket.length
                  ? inBucket.reduce((s, o) => s + o.predicted_home_wp, 0) / inBucket.length
                  : (b.min + b.max) / 2;
                const actualWin = inBucket.length
                  ? inBucket.filter((o) => o.home_win_actual).length / inBucket.length
                  : 0;
                return {
                  label: `${b.label} (${inBucket.length})`,
                  predicted: +(avgPred * 100).toFixed(1),
                  actual: +(actualWin * 100).toFixed(1),
                };
              }).filter((b) => {
                const n = parseInt(b.label.match(/\((\d+)\)/)?.[1] ?? "0");
                return n > 0;
              });
            })()}
          />
        </AdminCard>
      )}

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

/* ------------------------------------------------------------------ */
/*  Degradation Alerts Panel                                          */
/* ------------------------------------------------------------------ */

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
