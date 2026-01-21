"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import type { GameSummary } from "@/lib/api/sportsAdmin/types";
import { fetchGames } from "@/lib/api/sportsAdmin";
import styles from "./story-generator.module.css";

/**
 * Story Generator Landing Page
 * 
 * ISSUE 13: Admin UI for Chapters-First System
 * 
 * Lists games with story generation status.
 */
export default function StoryGeneratorLandingPage() {
  const [games, setGames] = useState<GameSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadGames();
  }, []);

  const loadGames = async () => {
    setLoading(true);
    setError(null);
    
    try {
      const response = await fetchGames({
        limit: 50,
        offset: 0,
        has_pbp: true,  // Only games with PBP can have stories
      });
      
      setGames(response.games);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load games");
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className={styles.container}>
        <div className={styles.loading}>Loading games...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className={styles.container}>
        <div className={styles.error}>Error: {error}</div>
      </div>
    );
  }

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h1>Story Generator</h1>
        <p className={styles.subtitle}>
          Chapters-First narrative generation for NBA games
        </p>
      </div>

      <div className={styles.gamesGrid}>
        {games.map((game) => (
          <Link
            key={game.id}
            href={`/admin/theory-bets/story-generator/${game.id}`}
            className={styles.gameCard}
          >
            <div className={styles.gameHeader}>
              <span className={styles.gameDate}>
                {new Date(game.game_date).toLocaleDateString()}
              </span>
              <span className={styles.league}>{game.league_code}</span>
            </div>
            
            <div className={styles.gameMatchup}>
              <div className={styles.team}>
                {game.away_team}
                {game.away_score !== null && (
                  <span className={styles.score}>{game.away_score}</span>
                )}
              </div>
              <div className={styles.at}>@</div>
              <div className={styles.team}>
                {game.home_team}
                {game.home_score !== null && (
                  <span className={styles.score}>{game.home_score}</span>
                )}
              </div>
            </div>

            <div className={styles.gameStats}>
              <span className={styles.stat}>
                {game.play_count} plays
              </span>
              {game.has_pbp && (
                <span className={styles.statusBadge}>✓ PBP</span>
              )}
            </div>
          </Link>
        ))}
      </div>

      {games.length === 0 && (
        <div className={styles.emptyState}>
          <p>No games with play-by-play data found.</p>
        </div>
      )}
    </div>
  );
}
