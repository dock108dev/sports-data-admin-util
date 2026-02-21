"use client";

import { useState } from "react";
import styles from "./styles.module.css";
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
    name: "clear_scraper_cache",
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
          return;
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

      {task.params.length > 0 && (
        <div className={styles.paramsRow}>
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
        </div>
      )}

      <div className={styles.taskFooter}>
        <button
          className={styles.runButton}
          disabled={!canRun || dispatching}
          onClick={handleRun}
        >
          {dispatching ? "Dispatching..." : "Run"}
        </button>
        {result && (
          <span className={styles.dispatchedMsg}>
            Dispatched{" "}
            <span className={styles.dispatchedTaskId}>{result.taskId}</span>
          </span>
        )}
      </div>
    </div>
  );
}

// ── Main page ──

export default function ControlPanelPage() {
  return (
    <div className={styles.container}>
      <h1>Control Panel</h1>
      <p className={styles.subtitle}>
        Trigger Celery tasks on-demand. Open the Runs drawer at the bottom to
        monitor job history.
      </p>

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
    </div>
  );
}
