"use client";

import { useState, useCallback } from "react";
import Link from "next/link";
import styles from "./page.module.css";
import {
  listGames,
  runFullPipeline,
  type GameSummary,
  type RunFullPipelineResponse,
} from "@/lib/api/sportsAdmin";
import { SUPPORTED_LEAGUES } from "@/lib/constants/sports";

type GenerationStatus = "idle" | "generating" | "success" | "error";

interface GenerationResult {
  gameId: number;
  status: GenerationStatus;
  response?: RunFullPipelineResponse;
  error?: string;
}

/**
 * Story Generator Page
 *
 * Allows generating stories for games via the pipeline system.
 * - Search/filter games
 * - Generate stories for individual games
 * - View generation results
 */
export default function StoryGeneratorPage() {
  const [league, setLeague] = useState<string>("NBA");
  const [daysBack, setDaysBack] = useState<number>(7);
  const [games, setGames] = useState<GameSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [generationResults, setGenerationResults] = useState<Map<number, GenerationResult>>(new Map());
  const [batchGenerating, setBatchGenerating] = useState(false);

  const loadGames = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const endDate = new Date().toISOString().split("T")[0];
      const startDate = new Date(Date.now() - daysBack * 24 * 60 * 60 * 1000)
        .toISOString()
        .split("T")[0];

      const response = await listGames({
        leagues: [league],
        startDate,
        endDate,
        limit: 100,
      });

      // Filter to games with PBP data (eligible for story generation)
      const eligibleGames = response.games.filter((g) => g.has_pbp);
      setGames(eligibleGames);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [league, daysBack]);

  const generateStory = useCallback(async (gameId: number) => {
    setGenerationResults((prev) => {
      const next = new Map(prev);
      next.set(gameId, { gameId, status: "generating" });
      return next;
    });

    try {
      const response = await runFullPipeline(gameId, "admin_ui");
      setGenerationResults((prev) => {
        const next = new Map(prev);
        next.set(gameId, {
          gameId,
          status: response.story_saved ? "success" : "error",
          response,
          error: response.story_saved ? undefined : response.message,
        });
        return next;
      });
    } catch (err) {
      setGenerationResults((prev) => {
        const next = new Map(prev);
        next.set(gameId, {
          gameId,
          status: "error",
          error: err instanceof Error ? err.message : String(err),
        });
        return next;
      });
    }
  }, []);

  const generateBatch = useCallback(async () => {
    setBatchGenerating(true);
    const gamesWithoutStory = games.filter((g) => !g.has_story);

    for (const game of gamesWithoutStory) {
      await generateStory(game.id);
    }

    setBatchGenerating(false);
  }, [games, generateStory]);

  const getResultStatus = (gameId: number): GenerationResult | undefined => {
    return generationResults.get(gameId);
  };

  const gamesWithStory = games.filter((g) => g.has_story);
  const gamesWithoutStory = games.filter((g) => !g.has_story);

  return (
    <div className={styles.container}>
      <header className={styles.header}>
        <h1 className={styles.title}>Story Generator</h1>
        <p className={styles.subtitle}>
          Generate condensed moment stories from play-by-play data
        </p>
      </header>

      <div className={styles.filtersCard}>
        <div className={styles.filterRow}>
          <div className={styles.filterGroup}>
            <label className={styles.filterLabel}>League</label>
            <select
              className={styles.input}
              value={league}
              onChange={(e) => setLeague(e.target.value)}
            >
              {SUPPORTED_LEAGUES.map((lg) => (
                <option key={lg} value={lg}>
                  {lg}
                </option>
              ))}
            </select>
          </div>
          <div className={styles.filterGroup}>
            <label className={styles.filterLabel}>Days Back</label>
            <select
              className={styles.input}
              value={daysBack}
              onChange={(e) => setDaysBack(Number(e.target.value))}
            >
              <option value={3}>3 days</option>
              <option value={7}>7 days</option>
              <option value={14}>14 days</option>
              <option value={30}>30 days</option>
            </select>
          </div>
          <div className={styles.filterGroup}>
            <button
              className={styles.primaryButton}
              onClick={loadGames}
              disabled={loading}
            >
              {loading ? "Loading..." : "Load Games"}
            </button>
          </div>
        </div>
      </div>

      {error && <div className={styles.error}>{error}</div>}

      {games.length > 0 && (
        <>
          <div className={styles.statsRow}>
            <div className={styles.stat}>
              <span className={styles.statValue}>{games.length}</span>
              <span className={styles.statLabel}>Total Games</span>
            </div>
            <div className={styles.stat}>
              <span className={styles.statValue}>{gamesWithStory.length}</span>
              <span className={styles.statLabel}>With Story</span>
            </div>
            <div className={styles.stat}>
              <span className={styles.statValue}>{gamesWithoutStory.length}</span>
              <span className={styles.statLabel}>Missing Story</span>
            </div>
          </div>

          {gamesWithoutStory.length > 0 && (
            <div className={styles.batchSection}>
              <button
                className={styles.batchButton}
                onClick={generateBatch}
                disabled={batchGenerating}
              >
                {batchGenerating
                  ? "Generating..."
                  : `Generate All Missing (${gamesWithoutStory.length})`}
              </button>
            </div>
          )}

          <div className={styles.gamesSection}>
            <h2 className={styles.sectionTitle}>Games Missing Stories</h2>
            {gamesWithoutStory.length === 0 ? (
              <p className={styles.emptyMessage}>All games have stories!</p>
            ) : (
              <div className={styles.gamesList}>
                {gamesWithoutStory.map((game) => {
                  const result = getResultStatus(game.id);
                  return (
                    <div key={game.id} className={styles.gameCard}>
                      <div className={styles.gameInfo}>
                        <div className={styles.gameMatchup}>
                          {game.away_team} @ {game.home_team}
                        </div>
                        <div className={styles.gameMeta}>
                          {game.game_date} | {game.play_count} plays
                        </div>
                      </div>
                      <div className={styles.gameActions}>
                        {result?.status === "generating" && (
                          <span className={styles.statusGenerating}>Generating...</span>
                        )}
                        {result?.status === "success" && (
                          <span className={styles.statusSuccess}>
                            Done ({result.response?.moment_count} moments)
                          </span>
                        )}
                        {result?.status === "error" && (
                          <span className={styles.statusError} title={result.error}>
                            Failed
                          </span>
                        )}
                        {(!result || result.status === "error") && (
                          <button
                            className={styles.generateButton}
                            onClick={() => generateStory(game.id)}
                            disabled={result?.status === "generating" || batchGenerating}
                          >
                            Generate
                          </button>
                        )}
                        <Link
                          href={`/admin/sports/games/${game.id}`}
                          className={styles.viewLink}
                        >
                          View
                        </Link>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {gamesWithStory.length > 0 && (
            <div className={styles.gamesSection}>
              <h2 className={styles.sectionTitle}>Games With Stories</h2>
              <div className={styles.gamesList}>
                {gamesWithStory.map((game) => (
                  <div key={game.id} className={styles.gameCard}>
                    <div className={styles.gameInfo}>
                      <div className={styles.gameMatchup}>
                        {game.away_team} @ {game.home_team}
                      </div>
                      <div className={styles.gameMeta}>
                        {game.game_date} | {game.play_count} plays
                      </div>
                    </div>
                    <div className={styles.gameActions}>
                      <span className={styles.statusComplete}>Has Story</span>
                      <button
                        className={styles.regenerateButton}
                        onClick={() => generateStory(game.id)}
                        disabled={
                          getResultStatus(game.id)?.status === "generating" ||
                          batchGenerating
                        }
                      >
                        Regenerate
                      </button>
                      <Link
                        href={`/admin/sports/games/${game.id}`}
                        className={styles.viewLink}
                      >
                        View
                      </Link>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}

      {!loading && games.length === 0 && !error && (
        <div className={styles.emptyState}>
          <p>Select a league and click "Load Games" to find games for story generation.</p>
          <p className={styles.hint}>
            Only final games with play-by-play data are eligible for story generation.
          </p>
        </div>
      )}
    </div>
  );
}
