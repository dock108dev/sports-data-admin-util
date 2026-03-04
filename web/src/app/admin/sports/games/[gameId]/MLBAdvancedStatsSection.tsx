"use client";

import type { MLBAdvancedTeamStats } from "@/lib/api/sportsAdmin/types";
import { CollapsibleSection } from "./CollapsibleSection";
import styles from "./styles.module.css";

function fmtPct(v: number | null): string {
  return v != null ? `${v.toFixed(1)}%` : "—";
}

function fmtVelo(v: number | null): string {
  return v != null ? `${v.toFixed(1)} mph` : "—";
}

export function MLBAdvancedStatsSection({ stats }: { stats: MLBAdvancedTeamStats[] }) {
  return (
    <CollapsibleSection title="Advanced Stats (Statcast)" defaultOpen={false}>
      <div className={styles.teamStatsGrid}>
        {stats.map((t) => (
          <div key={t.team} className={styles.teamStatsCard}>
            <div className={styles.teamStatsHeader}>
              <h3>{t.team}</h3>
              <span className={styles.badge}>{t.isHome ? "Home" : "Away"}</span>
            </div>

            <h4 style={{ margin: "0.75rem 0 0.25rem", fontSize: "0.85rem", color: "#64748b" }}>
              Plate Discipline
            </h4>
            <table className={styles.table}>
              <tbody>
                <tr><td>Z-Swing%</td><td>{fmtPct(t.zSwingPct)}</td></tr>
                <tr><td>O-Swing%</td><td>{fmtPct(t.oSwingPct)}</td></tr>
                <tr><td>Z-Contact%</td><td>{fmtPct(t.zContactPct)}</td></tr>
                <tr><td>O-Contact%</td><td>{fmtPct(t.oContactPct)}</td></tr>
              </tbody>
            </table>

            <h4 style={{ margin: "0.75rem 0 0.25rem", fontSize: "0.85rem", color: "#64748b" }}>
              Quality of Contact
            </h4>
            <table className={styles.table}>
              <tbody>
                <tr><td>Total Pitches</td><td>{t.totalPitches}</td></tr>
                <tr><td>Balls in Play</td><td>{t.ballsInPlay}</td></tr>
                <tr><td>Avg Exit Velo</td><td>{fmtVelo(t.avgExitVelo)}</td></tr>
                <tr><td>Hard Hit%</td><td>{fmtPct(t.hardHitPct)}</td></tr>
                <tr><td>Barrel%</td><td>{fmtPct(t.barrelPct)}</td></tr>
              </tbody>
            </table>
          </div>
        ))}
      </div>
    </CollapsibleSection>
  );
}
