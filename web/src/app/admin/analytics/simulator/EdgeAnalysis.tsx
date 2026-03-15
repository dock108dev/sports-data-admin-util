"use client";

import { AdminCard } from "@/components/admin";

interface EdgeMetric {
  key: string;
  label: string;
  higherIsBetter: boolean;
}

const EDGE_METRICS: EdgeMetric[] = [
  { key: "barrel_rate", label: "Barrel rate", higherIsBetter: true },
  { key: "hard_hit_rate", label: "Hard hit rate", higherIsBetter: true },
  { key: "avg_exit_velocity", label: "Avg exit velocity", higherIsBetter: true },
  { key: "whiff_rate", label: "Whiff rate", higherIsBetter: false },
  { key: "contact_rate", label: "Contact rate", higherIsBetter: true },
  { key: "chase_rate", label: "Chase rate", higherIsBetter: false },
  { key: "box_avg", label: "Batting avg", higherIsBetter: true },
  { key: "box_obp", label: "OBP", higherIsBetter: true },
  { key: "box_slg", label: "SLG", higherIsBetter: true },
  { key: "box_ops", label: "OPS", higherIsBetter: true },
  { key: "z_contact_pct", label: "Zone contact %", higherIsBetter: true },
  { key: "o_swing_pct", label: "O-swing %", higherIsBetter: false },
];

function fmt(v: number): string {
  if (v > 10) return v.toFixed(1);
  return (v * 100).toFixed(1) + "%";
}

interface Edge {
  label: string;
  favored: "home" | "away";
  favoredVal: number;
  otherVal: number;
  baseline: number;
  magnitude: number;
}

export function EdgeAnalysis({
  profileMeta,
  homeTeam,
  awayTeam,
  homeWP,
}: {
  profileMeta: Record<string, unknown>;
  homeTeam: string;
  awayTeam: string;
  homeWP: number;
}) {
  const homeProfile = profileMeta.home_profile as Record<string, number> | undefined;
  const awayProfile = profileMeta.away_profile as Record<string, number> | undefined;
  const baselines = profileMeta.baselines as Record<string, number> | undefined;

  if (!homeProfile || !awayProfile || !baselines) return null;

  const favoredSide: "home" | "away" = homeWP >= 0.5 ? "home" : "away";
  const favoredTeam = favoredSide === "home" ? homeTeam : awayTeam;

  // Compute edges for each metric
  const edges: Edge[] = [];
  for (const m of EDGE_METRICS) {
    const hv = homeProfile[m.key];
    const av = awayProfile[m.key];
    const bl = baselines[m.key];
    if (hv === undefined || av === undefined || bl === undefined) continue;

    // Which team has advantage on this metric?
    const homeBetter = m.higherIsBetter ? hv > av : hv < av;
    const favored = homeBetter ? "home" : "away";

    // Only care about advantages for the favored team
    if (favored !== favoredSide) continue;

    const magnitude = Math.abs(hv - av) / (bl || 1);
    edges.push({
      label: m.label,
      favored,
      favoredVal: favored === "home" ? hv : av,
      otherVal: favored === "home" ? av : hv,
      baseline: bl,
      magnitude,
    });
  }

  // Sort by magnitude and take top 5
  edges.sort((a, b) => b.magnitude - a.magnitude);
  const topEdges = edges.slice(0, 5);

  if (topEdges.length === 0) return null;

  return (
    <AdminCard
      title="Edge Analysis"
      subtitle={`Why ${favoredTeam} is favored at ${(Math.max(homeWP, 1 - homeWP) * 100).toFixed(1)}%`}
    >
      <ul style={{ margin: 0, padding: "0 0 0 1.25rem", fontSize: "0.9rem", lineHeight: 1.8 }}>
        {topEdges.map((e) => (
          <li key={e.label}>
            Higher {e.label} ({fmt(e.favoredVal)} vs {fmt(e.otherVal)}, league avg {fmt(e.baseline)})
          </li>
        ))}
      </ul>

      {/* Compact full comparison table */}
      <div style={{ marginTop: "1rem", overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.8rem" }}>
          <thead>
            <tr style={{ borderBottom: "1px solid var(--border)" }}>
              <th style={{ textAlign: "left", padding: "0.3rem 0.5rem", color: "var(--text-muted)" }}>Metric</th>
              <th style={{ textAlign: "right", padding: "0.3rem 0.5rem" }}>{homeTeam}</th>
              <th style={{ textAlign: "center", padding: "0.3rem 0.5rem", color: "var(--text-muted)" }}>Lg Avg</th>
              <th style={{ textAlign: "right", padding: "0.3rem 0.5rem" }}>{awayTeam}</th>
            </tr>
          </thead>
          <tbody>
            {EDGE_METRICS.map((m) => {
              const hv = homeProfile[m.key];
              const av = awayProfile[m.key];
              const bl = baselines[m.key];
              if (hv === undefined && av === undefined) return null;
              return (
                <tr key={m.key} style={{ borderBottom: "1px solid #f1f5f9" }}>
                  <td style={{ padding: "0.25rem 0.5rem", color: "var(--text-secondary)" }}>{m.label}</td>
                  <td style={{ textAlign: "right", padding: "0.25rem 0.5rem" }}>{hv !== undefined ? fmt(hv) : "-"}</td>
                  <td style={{ textAlign: "center", padding: "0.25rem 0.5rem", color: "var(--text-muted)" }}>{bl !== undefined ? fmt(bl) : "-"}</td>
                  <td style={{ textAlign: "right", padding: "0.25rem 0.5rem" }}>{av !== undefined ? fmt(av) : "-"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </AdminCard>
  );
}
