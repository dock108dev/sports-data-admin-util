"use client";

import { useMemo, useState } from "react";
import type { AdminGameDetail } from "@/lib/api/sportsAdmin";
import styles from "./styles.module.css";

/**
 * Get period label based on league format.
 * - NBA: Q1, Q2, Q3, Q4, OT1, OT2...
 * - NHL: P1, P2, P3, OT, SO
 * - NCAAB: 1st Half, 2nd Half, OT1, OT2...
 */
const getPeriodLabel = (period: number, leagueCode?: string) => {
  if (leagueCode === "NCAAB") {
    // NCAAB uses halves
    if (period === 1) return "1st Half";
    if (period === 2) return "2nd Half";
    return `OT${period - 2}`;
  }
  if (leagueCode === "NHL") {
    if (period <= 3) return `P${period}`;
    if (period === 4) return "OT";
    return "SO";
  }
  // Default: NBA-style quarters
  if (period <= 4) return `Q${period}`;
  return `OT${period - 4}`;
};

export function PbpSection({ plays, leagueCode }: { plays: AdminGameDetail["plays"]; leagueCode?: string }) {
  const [isOpen, setIsOpen] = useState(false);
  const [selectedQuarter, setSelectedQuarter] = useState<number | null>(null);

  const quarters = useMemo(() => {
    const qs = [...new Set(plays.map((p) => p.quarter).filter((q) => q !== null))] as number[];
    return qs.sort((a, b) => a - b);
  }, [plays]);

  const effectiveQuarter = useMemo(() => {
    if (quarters.length === 0) return null;
    if (selectedQuarter === null) return quarters[0];
    return quarters.includes(selectedQuarter) ? selectedQuarter : quarters[0];
  }, [quarters, selectedQuarter]);

  const filteredPlays = useMemo(() => {
    if (effectiveQuarter === null) return plays;
    return plays.filter((p) => p.quarter === effectiveQuarter);
  }, [plays, effectiveQuarter]);

  return (
    <div className={styles.card}>
      <button
        type="button"
        className={styles.collapsibleHeader}
        onClick={() => setIsOpen(!isOpen)}
      >
        <h2>Play-by-Play</h2>
        <span className={styles.chevron}>{isOpen ? "▼" : "▶"}</span>
      </button>
      {isOpen && (
        <div className={styles.collapsibleContent}>
          {plays.length === 0 ? (
            <div style={{ color: "#475569" }}>No play-by-play data found for this game.</div>
          ) : (
            <>
              <div className={styles.quarterTabs}>
                {quarters.map((q) => (
                  <button
                    key={q}
                    type="button"
                    className={`${styles.quarterTab} ${effectiveQuarter === q ? styles.quarterTabActive : ""}`}
                    onClick={() => setSelectedQuarter(q)}
                  >
                    {getPeriodLabel(q, leagueCode)}
                    <span className={styles.quarterCount}>
                      {plays.filter((p) => p.quarter === q).length}
                    </span>
                  </button>
                ))}
              </div>
              <div className={styles.pbpContainer}>
                <table className={styles.table}>
                  <thead>
                    <tr>
                      <th>Time</th>
                      <th>Team</th>
                      <th>Player</th>
                      <th>Description</th>
                      <th>Score</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredPlays.map((play, idx) => (
                      <tr key={`play-${play.play_index}-${idx}`}>
                        <td>{play.game_clock ?? "—"}</td>
                        <td>{play.team_abbreviation ?? "—"}</td>
                        <td>{play.player_name ?? "—"}</td>
                        <td className={styles.pbpDescription}>{play.description ?? "—"}</td>
                        <td>
                          {play.away_score !== null && play.home_score !== null
                            ? `${play.away_score}-${play.home_score}`
                            : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
