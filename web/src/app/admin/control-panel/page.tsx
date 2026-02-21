"use client";

import { useCallback, useEffect, useState } from "react";
import styles from "./styles.module.css";
import { listJobRuns, type JobRunResponse } from "@/lib/api/sportsAdmin";
import { triggerTask } from "@/lib/api/sportsAdmin/taskControl";

// ── Task registry (mirrors API whitelist) ──

type ParamType = "select" | "number";

interface TaskParam {
  name: string;
  type: ParamType;
  required: boolean;
  options?: string[];
  default?: string | number;
}

interface TaskDef {
  name: string;
  label: string;
  description: string;
  category: string;
  queue: "sports-scraper" | "social-scraper";
  params: TaskParam[];
}

const LEAGUE_OPTIONS = ["NBA", "NHL", "NCAAB"];

const TASK_REGISTRY: TaskDef[] = [
  // Ingestion
  {
    name: "run_scheduled_ingestion",
    label: "Scheduled Ingestion",
    description: "Full scheduled ingestion (NBA, NHL, NCAAB sequentially)",
    category: "Ingestion",
    queue: "sports-scraper",
    params: [],
  },
  {
    name: "run_daily_sweep",
    label: "Daily Sweep",
    description: "Daily truth repair and backfill sweep",
    category: "Ingestion",
    queue: "sports-scraper",
    params: [],
  },
  // Polling
  {
    name: "update_game_states",
    label: "Update Game States",
    description: "Update game state machine for all tracked games",
    category: "Polling",
    queue: "sports-scraper",
    params: [],
  },
  {
    name: "poll_live_pbp",
    label: "Poll Live PBP",
    description: "Poll live play-by-play and boxscores",
    category: "Polling",
    queue: "sports-scraper",
    params: [],
  },
  // Odds
  {
    name: "sync_mainline_odds",
    label: "Mainline Odds",
    description: "Sync mainline odds (spreads, totals, moneyline)",
    category: "Odds",
    queue: "sports-scraper",
    params: [
      {
        name: "league",
        type: "select",
        required: false,
        options: LEAGUE_OPTIONS,
      },
    ],
  },
  {
    name: "sync_prop_odds",
    label: "Prop Odds",
    description: "Sync player/team prop odds for pregame events",
    category: "Odds",
    queue: "sports-scraper",
    params: [
      {
        name: "league",
        type: "select",
        required: false,
        options: LEAGUE_OPTIONS,
      },
    ],
  },
  // Social
  {
    name: "collect_game_social",
    label: "Game Social",
    description: "Collect social media content for upcoming games",
    category: "Social",
    queue: "social-scraper",
    params: [],
  },
  {
    name: "collect_social_for_league",
    label: "League Social",
    description: "Collect social content for a specific league",
    category: "Social",
    queue: "social-scraper",
    params: [
      {
        name: "league",
        type: "select",
        required: true,
        options: LEAGUE_OPTIONS,
      },
    ],
  },
  {
    name: "map_social_to_games",
    label: "Map Social to Games",
    description: "Map collected social posts to games",
    category: "Social",
    queue: "social-scraper",
    params: [
      {
        name: "batch_size",
        type: "number",
        required: false,
        default: 100,
      },
    ],
  },
  {
    name: "run_final_whistle_social",
    label: "Final Whistle Social",
    description: "Collect post-game social content for a specific game",
    category: "Social",
    queue: "social-scraper",
    params: [
      { name: "game_id", type: "number", required: true },
    ],
  },
  // Flows
  {
    name: "run_scheduled_flow_generation",
    label: "All Flows",
    description: "Run flow generation for all leagues",
    category: "Flows",
    queue: "sports-scraper",
    params: [],
  },
  {
    name: "run_scheduled_nba_flow_generation",
    label: "NBA Flows",
    description: "Run flow generation for NBA games",
    category: "Flows",
    queue: "sports-scraper",
    params: [],
  },
  {
    name: "run_scheduled_nhl_flow_generation",
    label: "NHL Flows",
    description: "Run flow generation for NHL games",
    category: "Flows",
    queue: "sports-scraper",
    params: [],
  },
  {
    name: "run_scheduled_ncaab_flow_generation",
    label: "NCAAB Flows",
    description: "Run flow generation for NCAAB games (max 10)",
    category: "Flows",
    queue: "sports-scraper",
    params: [],
  },
  {
    name: "trigger_flow_for_game",
    label: "Flow for Game",
    description: "Trigger flow generation for a specific game",
    category: "Flows",
    queue: "sports-scraper",
    params: [
      { name: "game_id", type: "number", required: true },
    ],
  },
  // Timelines
  {
    name: "run_scheduled_timeline_generation",
    label: "Timeline Generation",
    description: "Run scheduled timeline generation for all leagues",
    category: "Timelines",
    queue: "sports-scraper",
    params: [],
  },
  // Utility
  {
    name: "clear_scraper_cache_task",
    label: "Clear Cache",
    description: "Clear scraper cache for a league (optionally limit by days)",
    category: "Utility",
    queue: "sports-scraper",
    params: [
      {
        name: "league",
        type: "select",
        required: true,
        options: LEAGUE_OPTIONS,
      },
      { name: "days", type: "number", required: false },
    ],
  },
];

// Group tasks by category preserving insertion order
const CATEGORIES = Array.from(
  new Set(TASK_REGISTRY.map((t) => t.category))
);

// ── Run History constants ──

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

// ── Helpers ──

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

// ── TaskCard component ──

function TaskCard({ task }: { task: TaskDef }) {
  const [paramValues, setParamValues] = useState<Record<string, string>>(() => {
    const defaults: Record<string, string> = {};
    for (const p of task.params) {
      if (p.default !== undefined) {
        defaults[p.name] = String(p.default);
      } else {
        defaults[p.name] = "";
      }
    }
    return defaults;
  });
  const [dispatching, setDispatching] = useState(false);
  const [result, setResult] = useState<{ taskId: string } | null>(null);

  const canRun = task.params
    .filter((p) => p.required)
    .every((p) => paramValues[p.name]?.trim());

  const handleRun = async () => {
    setDispatching(true);
    setResult(null);
    try {
      const args: unknown[] = [];
      for (const p of task.params) {
        const val = paramValues[p.name]?.trim();
        if (val) {
          args.push(p.type === "number" ? Number(val) : val);
        } else if (p.required) {
          return; // shouldn't happen — button is disabled
        } else {
          args.push(null);
        }
      }
      const res = await triggerTask(task.name, args);
      setResult({ taskId: res.task_id });
    } catch {
      setResult(null);
    } finally {
      setDispatching(false);
    }
  };

  return (
    <div className={styles.taskCard}>
      <div className={styles.taskHeader}>
        <span className={styles.taskName}>{task.label}</span>
        <span
          className={`${styles.queueBadge} ${
            task.queue === "sports-scraper"
              ? styles.queueSports
              : styles.queueSocial
          }`}
        >
          {task.queue === "sports-scraper" ? "sports" : "social"}
        </span>
      </div>
      <div className={styles.taskDescription}>{task.description}</div>
      <div className={styles.taskControls}>
        {task.params.map((p) => (
          <div key={p.name} className={styles.paramGroup}>
            <label className={styles.paramLabel}>
              {p.name}
              {p.required ? "" : " (opt)"}
            </label>
            {p.type === "select" && p.options ? (
              <select
                className={styles.paramInput}
                value={paramValues[p.name] ?? ""}
                onChange={(e) =>
                  setParamValues((prev) => ({
                    ...prev,
                    [p.name]: e.target.value,
                  }))
                }
              >
                {!p.required && <option value="">All</option>}
                {p.options.map((opt) => (
                  <option key={opt} value={opt}>
                    {opt}
                  </option>
                ))}
              </select>
            ) : (
              <input
                type="number"
                className={styles.paramInput}
                placeholder={p.default !== undefined ? String(p.default) : ""}
                value={paramValues[p.name] ?? ""}
                onChange={(e) =>
                  setParamValues((prev) => ({
                    ...prev,
                    [p.name]: e.target.value,
                  }))
                }
              />
            )}
          </div>
        ))}
        <button
          className={styles.runButton}
          disabled={!canRun || dispatching}
          onClick={handleRun}
        >
          {dispatching ? "..." : "Run"}
        </button>
      </div>
      {result && (
        <div>
          <span className={styles.dispatchedMsg}>Dispatched</span>{" "}
          <span className={styles.dispatchedTaskId}>{result.taskId}</span>
        </div>
      )}
    </div>
  );
}

// ── Main page ──

export default function ControlPanelPage() {
  // Run history state
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

  useEffect(() => {
    setLoading(true);
    fetchRuns();
  }, [fetchRuns]);

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
      <h1>Control Panel</h1>
      <p className={styles.subtitle}>
        Trigger Celery tasks on-demand and monitor recent job runs.
      </p>

      {/* ── Section 1: Task Triggers ── */}
      {CATEGORIES.map((cat) => (
        <div key={cat} className={styles.categoryGroup}>
          <h2 className={styles.categoryTitle}>{cat}</h2>
          <div className={styles.taskGrid}>
            {TASK_REGISTRY.filter((t) => t.category === cat).map((task) => (
              <TaskCard key={task.name} task={task} />
            ))}
          </div>
        </div>
      ))}

      {/* ── Section 2: Run History ── */}
      <div className={styles.card}>
        <div className={styles.cardHeader}>
          <h2>Run History</h2>
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
