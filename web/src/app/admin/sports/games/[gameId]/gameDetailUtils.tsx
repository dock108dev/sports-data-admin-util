import styles from "./styles.module.css";

/**
 * Format a stat value for display, handling nested objects.
 * Handles common CBB/NCAAB API patterns:
 * - {total: 89, byPeriod: [...]} -> "89"
 * - {made: 24, attempted: 50} -> "24/50"
 * - {offensive: 10, defensive: 32, total: 42} -> "42 (10 off, 32 def)"
 */
export function formatStatValue(value: unknown): string {
  if (value === null || value === undefined) {
    return "—";
  }

  if (typeof value !== "object") {
    // Primitive value - format numbers nicely
    if (typeof value === "number") {
      return Number.isInteger(value) ? String(value) : value.toFixed(1);
    }
    return String(value);
  }

  // Handle arrays - show count for large arrays, values for small ones
  if (Array.isArray(value)) {
    if (value.length > 4) {
      return `[${value.length} items]`;
    }
    return value.map(formatStatValue).join(", ");
  }

  // Handle objects
  const obj = value as Record<string, unknown>;
  const keys = Object.keys(obj);

  // Pattern: {total: X, byPeriod: [...]} - common for points/rebounds/turnovers in CBB API
  // Just show the total since byPeriod is detail we don't need inline
  if (keys.includes("total") && typeof obj.total === "number") {
    const total = obj.total as number;
    // Check for offensive/defensive breakdown (rebounds)
    if (keys.includes("offensive") && keys.includes("defensive")) {
      const off = obj.offensive as number;
      const def = obj.defensive as number;
      return `${total} (${off} off, ${def} def)`;
    }
    // Check for forced turnovers
    if (keys.includes("forced") && typeof obj.forced === "number") {
      return `${total} (${obj.forced} forced)`;
    }
    // Just return total for other cases
    return String(total);
  }

  // Pattern: {made: X, attempted: Y} - shooting stats
  if (
    (keys.includes("made") && keys.includes("attempted")) ||
    (keys.includes("makes") && keys.includes("attempts"))
  ) {
    const made = (obj.made ?? obj.makes ?? 0) as number;
    const attempted = (obj.attempted ?? obj.attempts ?? 0) as number;
    const pct = obj.percentage ?? obj.pct;
    if (pct !== undefined && typeof pct === "number") {
      return `${made}/${attempted} (${pct.toFixed(1)}%)`;
    }
    // Calculate percentage if we have attempts
    if (attempted > 0) {
      const calcPct = ((made / attempted) * 100).toFixed(1);
      return `${made}/${attempted} (${calcPct}%)`;
    }
    return `${made}/${attempted}`;
  }

  // Pattern: {personal: X, technical: Y} - fouls
  if (keys.includes("personal") && keys.includes("technical")) {
    const personal = obj.personal as number;
    const technical = obj.technical ?? 0;
    return technical ? `${personal} (${technical} tech)` : String(personal);
  }

  // Pattern: Four factors stats - just show key metrics
  if (keys.includes("effectiveFieldGoalPercentage") || keys.includes("turnoverPercentage")) {
    const efg = obj.effectiveFieldGoalPercentage;
    const to = obj.turnoverPercentage;
    const orb = obj.offensiveReboundPercentage;
    const ft = obj.freeThrowRate;
    const parts: string[] = [];
    if (typeof efg === "number") parts.push(`eFG%: ${efg.toFixed(1)}`);
    if (typeof to === "number") parts.push(`TO%: ${to.toFixed(1)}`);
    if (typeof orb === "number") parts.push(`ORB%: ${orb.toFixed(1)}`);
    if (typeof ft === "number") parts.push(`FTR: ${ft.toFixed(2)}`);
    return parts.length > 0 ? parts.join(", ") : "—";
  }

  // For other objects, format as "key: value" pairs (skip arrays/byPeriod)
  return keys
    .filter((k) => {
      const v = obj[k];
      return v !== null && v !== undefined && k !== "byPeriod" && !Array.isArray(v);
    })
    .map((k) => `${k}: ${formatStatValue(obj[k])}`)
    .join(", ");
}

/**
 * Flatten nested stats object for better display.
 * Converts nested objects into flattened key-value pairs with descriptive keys.
 */
export function flattenStats(
  stats: Record<string, unknown>,
): Array<{ key: string; label: string; value: string }> {
  const result: Array<{ key: string; label: string; value: string }> = [];

  // Stats to display in order, with display labels
  const displayStats: Array<{ key: string; label: string }> = [
    { key: "points", label: "Points" },
    { key: "rebounds", label: "Rebounds" },
    { key: "assists", label: "Assists" },
    { key: "steals", label: "Steals" },
    { key: "blocks", label: "Blocks" },
    { key: "turnovers", label: "Turnovers" },
    { key: "fouls", label: "Fouls" },
    { key: "fieldGoals", label: "FG" },
    { key: "twoPointFieldGoals", label: "2PT" },
    { key: "threePointFieldGoals", label: "3PT" },
    { key: "freeThrows", label: "FT" },
    { key: "possessions", label: "Possessions" },
    { key: "trueShooting", label: "TS%" },
  ];

  for (const { key, label } of displayStats) {
    const value = stats[key];

    if (value === null || value === undefined) {
      continue;
    }

    result.push({
      key,
      label,
      value: formatStatValue(value),
    });
  }

  return result;
}

/* ---- Computed Fields: metric grouping config ---- */
export const METRIC_GROUPS: { label: string; keys: string[] }[] = [
  { label: "Score", keys: ["home_score", "away_score", "margin_of_victory", "combined_score", "winner"] },
  { label: "Spread", keys: [
    "pregame_spread_label", "opening_spread_home", "opening_spread_away",
    "closing_spread_home", "closing_spread_away",
    "line_movement_spread", "did_home_cover", "did_away_cover", "spread_outcome_label",
  ]},
  { label: "Total", keys: [
    "pregame_total_label", "opening_total", "closing_total",
    "line_movement_total", "total_result", "total_outcome_label",
  ]},
  { label: "Moneyline", keys: [
    "pregame_ml_home_label", "pregame_ml_away_label",
    "closing_ml_home", "closing_ml_away",
    "closing_ml_home_implied", "closing_ml_away_implied",
    "opening_ml_home", "opening_ml_away",
    "moneyline_upset", "ml_outcome_label",
  ]},
];

export const OUTCOME_KEYS = new Set(["spread_outcome_label", "total_outcome_label", "ml_outcome_label"]);
export const GREEN_OUTCOMES = new Set(["home_cover", "over", "favorite_won", "home_win", "away_win"]);
export const RED_OUTCOMES = new Set(["away_cover", "under", "underdog_won", "upset"]);

export function formatMetricValue(key: string, value: unknown): string {
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "number") {
    if (key.includes("implied")) return `${(value * 100).toFixed(1)}%`;
    if (Number.isInteger(value)) return String(value);
    return value.toFixed(1);
  }
  return String(value ?? "—");
}

export function getOutcomeBadgeClass(value: unknown): string {
  const v = String(value ?? "").toLowerCase().replace(/\s+/g, "_");
  if (GREEN_OUTCOMES.has(v) || v.includes("cover") && !v.includes("away")) return styles.outcomeBadgeGreen;
  if (RED_OUTCOMES.has(v) || v.includes("under") || v.includes("upset")) return styles.outcomeBadgeRed;
  if (v === "push" || v === "pick") return styles.outcomeBadgeGray;
  return styles.outcomeBadgeGray;
}

/* ---- FieldLabel: tooltip showing API field name ---- */
export function FieldLabel({ label, field }: { label: string; field: string }) {
  return (
    <span className={styles.fieldLabel} title={`API field: ${field}`}>
      {label}
    </span>
  );
}
