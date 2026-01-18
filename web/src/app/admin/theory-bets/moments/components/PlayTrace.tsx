"use client";

import { useState, useEffect } from "react";
import styles from "../styles.module.css";
import { fetchGame, type PlayEntry } from "@/lib/api/sportsAdmin";

interface PlayTraceProps {
  gameId: number;
  startPlay: number;
  endPlay: number;
}

/**
 * Shows the plays that contributed to a moment.
 * Highlights scoring plays and shows entity resolution status.
 */
export function PlayTrace({ gameId, startPlay, endPlay }: PlayTraceProps) {
  const [plays, setPlays] = useState<PlayEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setError(null);
      try {
        const game = await fetchGame(String(gameId));
        if (cancelled) return;
        
        // Filter plays in range
        const filtered = (game.plays || []).filter(
          (p) => p.play_index >= startPlay && p.play_index <= endPlay
        );
        setPlays(filtered);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : String(err));
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    load();

    return () => {
      cancelled = true;
    };
  }, [gameId, startPlay, endPlay]);

  if (loading) {
    return <div style={{ color: "#64748b", fontSize: "0.85rem" }}>Loading plays...</div>;
  }

  if (error) {
    return <div style={{ color: "#dc2626", fontSize: "0.85rem" }}>{error}</div>;
  }

  if (plays.length === 0) {
    return <div style={{ color: "#64748b", fontSize: "0.85rem" }}>No plays in range.</div>;
  }

  return (
    <div className={styles.playsList}>
      {plays.map((play) => {
        // Detect scoring plays by checking if score changed
        const isScoring = play.play_type?.toLowerCase().includes("score") ||
          play.play_type?.toLowerCase().includes("made") ||
          play.play_type?.toLowerCase().includes("point") ||
          play.description?.toLowerCase().includes("makes");

        return (
          <div
            key={play.play_index}
            className={`${styles.playItem} ${isScoring ? styles.scoringPlay : ""}`}
          >
            <span className={styles.playIndex}>#{play.play_index}</span>
            <div className={styles.playDescription}>
              <div>
                {play.description || "No description"}
              </div>
              <div style={{ 
                fontSize: "0.75rem", 
                color: "#94a3b8", 
                marginTop: "0.25rem",
                display: "flex",
                gap: "0.5rem",
                flexWrap: "wrap"
              }}>
                {play.quarter && (
                  <span>Q{play.quarter}</span>
                )}
                {play.game_clock && (
                  <span>{play.game_clock}</span>
                )}
                {play.team_abbreviation && (
                  <span
                    style={{
                      background: "#e2e8f0",
                      padding: "0.1rem 0.4rem",
                      borderRadius: "4px",
                      fontWeight: 600,
                    }}
                  >
                    {play.team_abbreviation}
                  </span>
                )}
                {play.player_name && (
                  <span
                    style={{
                      background: "#dbeafe",
                      padding: "0.1rem 0.4rem",
                      borderRadius: "4px",
                      color: "#1d4ed8",
                    }}
                  >
                    {play.player_name}
                  </span>
                )}
                {play.play_type && (
                  <span style={{ fontStyle: "italic" }}>{play.play_type}</span>
                )}
              </div>
            </div>
            <span className={styles.playScore}>
              {play.away_score ?? 0} - {play.home_score ?? 0}
            </span>
          </div>
        );
      })}
    </div>
  );
}
