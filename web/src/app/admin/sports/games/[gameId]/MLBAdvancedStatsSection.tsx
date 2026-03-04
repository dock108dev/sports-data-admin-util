"use client";

import type { MLBAdvancedTeamStats, MLBAdvancedPlayerStats } from "@/lib/api/sportsAdmin/types";
import { CollapsibleSection } from "./CollapsibleSection";
import styles from "./styles.module.css";

function fmtPct(v: number | null): string {
  return v != null ? `${(v * 100).toFixed(1)}%` : "—";
}

function fmtVelo(v: number | null): string {
  return v != null ? `${v.toFixed(1)} mph` : "—";
}

export function MLBAdvancedStatsSection({
  stats,
  playerStats,
}: {
  stats: MLBAdvancedTeamStats[];
  playerStats?: MLBAdvancedPlayerStats[] | null;
}) {
  const homePlayers = (playerStats ?? [])
    .filter((p) => p.isHome)
    .sort((a, b) => b.totalPitches - a.totalPitches);

  const awayPlayers = (playerStats ?? [])
    .filter((p) => !p.isHome)
    .sort((a, b) => b.totalPitches - a.totalPitches);

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

      {playerStats && playerStats.length > 0 && (
        <>
          <h3 style={{ margin: "1.5rem 0 0.75rem", fontSize: "1rem", color: "#1e293b" }}>
            Player Breakdown
          </h3>
          {[
            { label: "Away", players: awayPlayers },
            { label: "Home", players: homePlayers },
          ]
            .filter((g) => g.players.length > 0)
            .map((group) => (
              <div key={group.label} style={{ marginBottom: "1.25rem" }}>
                <h4 style={{ margin: "0 0 0.5rem", fontSize: "0.9rem", color: "#475569" }}>
                  {group.players[0]?.team ?? group.label}{" "}
                  <span className={styles.badge}>{group.label}</span>
                </h4>
                <div style={{ overflowX: "auto" }}>
                  <table className={styles.table}>
                    <thead>
                      <tr>
                        <th>Batter</th>
                        <th>Pitches</th>
                        <th>Z-Sw%</th>
                        <th>O-Sw%</th>
                        <th>Z-Con%</th>
                        <th>O-Con%</th>
                        <th>BIP</th>
                        <th>Avg EV</th>
                        <th>HH%</th>
                        <th>Brl%</th>
                      </tr>
                    </thead>
                    <tbody>
                      {group.players.map((p) => (
                        <tr key={p.playerName}>
                          <td>{p.playerName}</td>
                          <td>{p.totalPitches}</td>
                          <td>{fmtPct(p.zSwingPct)}</td>
                          <td>{fmtPct(p.oSwingPct)}</td>
                          <td>{fmtPct(p.zContactPct)}</td>
                          <td>{fmtPct(p.oContactPct)}</td>
                          <td>{p.ballsInPlay}</td>
                          <td>{fmtVelo(p.avgExitVelo)}</td>
                          <td>{fmtPct(p.hardHitPct)}</td>
                          <td>{fmtPct(p.barrelPct)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ))}
        </>
      )}
    </CollapsibleSection>
  );
}
