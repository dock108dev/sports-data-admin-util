"use client";

import { useMemo, useState } from "react";
import type { AdminGameDetail } from "@/lib/api/sportsAdmin";
import styles from "./styles.module.css";

const getQuarterLabel = (quarter: number) => {
  if (quarter <= 4) return `Q${quarter}`;
  return `OT${quarter - 4}`;
};

export function PbpSection({ plays }: { plays: AdminGameDetail["plays"] }) {
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
                    {getQuarterLabel(q)}
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
                      <th>Description</th>
                      <th>Score</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredPlays.map((play, idx) => (
                      <tr key={`play-${play.play_index}-${idx}`}>
                        <td>{play.game_clock ?? "—"}</td>
                        <td>{play.team_abbreviation ?? "—"}</td>
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
