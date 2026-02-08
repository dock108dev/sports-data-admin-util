"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import Link from "next/link";
import styles from "./page.module.css";
import {
  listGames,
  runFullPipeline,
  bulkGenerateStoriesAsync,
  getBulkGenerateStatus,
  type GameSummary,
  type RunFullPipelineResponse,
  type BulkGenerateStatusResponse,
} from "@/lib/api/sportsAdmin";
import { SUPPORTED_LEAGUES } from "@/lib/constants/sports";
import { ROUTES } from "@/lib/constants/routes";
import { LogsDrawer, type LogsTab } from "@/components/admin";

const PIPELINE_LOG_TABS: LogsTab[] = [
  { label: "API", container: "sports-api" },
  { label: "API Worker", container: "sports-api-worker" },
];
import { formatDateInput, getDateDaysAgo } from "@/lib/utils/dateFormat";

type GenerationStatus = "idle" | "generating" | "success" | "error";

interface GenerationResult {
  gameId: number;
  status: GenerationStatus;
  response?: RunFullPipelineResponse;
  error?: string;
}

interface BulkJobState {
  jobId: string | null;
  state: BulkGenerateStatusResponse["state"] | null;
  current: number;
  total: number;
  successful: number;
  failed: number;
  skipped: number;
}

/**
 * Flow Generator Page
 *
 * Allows generating game flows for games via the pipeline system.
 * - Search/filter games
 * - Bulk generate flows with date range and league selection
 * - Generate flows for individual games
 * - View generation results
 */
export default function StoryGeneratorPage() {
  // Date range state
  const [startDate, setStartDate] = useState<string>(() => {
    return formatDateInput(getDateDaysAgo(7));
  });
  const [endDate, setEndDate] = useState<string>(() => {
    return formatDateInput(new Date());
  });

  // League selection state
  const [selectedLeagues, setSelectedLeagues] = useState<Set<string>>(
    new Set(["NBA"])
  );

  // Force regenerate option
  const [forceRegenerate, setForceRegenerate] = useState(false);
  const [logsOpen, setLogsOpen] = useState(false);

  // Games list state (for preview/individual generation)
  const [games, setGames] = useState<GameSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [nextOffset, setNextOffset] = useState<number | null>(null);
  const [totalGames, setTotalGames] = useState<number>(0);
  const [error, setError] = useState<string | null>(null);
  const [generationResults, setGenerationResults] = useState<
    Map<number, GenerationResult>
  >(new Map());

  // Bulk job state
  const [bulkJob, setBulkJob] = useState<BulkJobState>({
    jobId: null,
    state: null,
    current: 0,
    total: 0,
    successful: 0,
    failed: 0,
    skipped: 0,
  });
  const pollingRef = useRef<NodeJS.Timeout | null>(null);

  // Toggle league selection
  const toggleLeague = (league: string) => {
    setSelectedLeagues((prev) => {
      const next = new Set(prev);
      if (next.has(league)) {
        next.delete(league);
      } else {
        next.add(league);
      }
      return next;
    });
  };

  // Load games for preview (initial load)
  const loadGames = useCallback(async () => {
    if (selectedLeagues.size === 0) {
      setError("Please select at least one league");
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const response = await listGames({
        leagues: Array.from(selectedLeagues),
        startDate,
        endDate,
        hasPbp: true,  // Filter server-side to only games with PBP data
        limit: 200,  // Max allowed by API
      });

      setGames(response.games);
      setNextOffset(response.nextOffset);
      setTotalGames(response.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [selectedLeagues, startDate, endDate]);

  // Load more games (pagination)
  const loadMoreGames = useCallback(async () => {
    if (nextOffset === null || loadingMore) return;

    setLoadingMore(true);
    try {
      const response = await listGames({
        leagues: Array.from(selectedLeagues),
        startDate,
        endDate,
        hasPbp: true,
        limit: 200,
        offset: nextOffset,
      });

      setGames((prev) => [...prev, ...response.games]);
      setNextOffset(response.nextOffset);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoadingMore(false);
    }
  }, [selectedLeagues, startDate, endDate, nextOffset, loadingMore]);

  // Start bulk generation job
  const startBulkGeneration = useCallback(async () => {
    if (selectedLeagues.size === 0) {
      setError("Please select at least one league");
      return;
    }

    setError(null);
    try {
      const response = await bulkGenerateStoriesAsync({
        start_date: startDate,
        end_date: endDate,
        leagues: Array.from(selectedLeagues),
        force: forceRegenerate,
      });

      setBulkJob({
        jobId: response.job_id,
        state: "PENDING",
        current: 0,
        total: 0,
        successful: 0,
        failed: 0,
        skipped: 0,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [selectedLeagues, startDate, endDate, forceRegenerate]);

  // Poll for job status
  useEffect(() => {
    if (!bulkJob.jobId || bulkJob.state === "SUCCESS" || bulkJob.state === "FAILURE") {
      return;
    }

    const pollStatus = async () => {
      try {
        const status = await getBulkGenerateStatus(bulkJob.jobId!);
        setBulkJob({
          jobId: status.job_id,
          state: status.state,
          current: status.current,
          total: status.total,
          successful: status.successful,
          failed: status.failed,
          skipped: status.skipped,
        });

        // If job is complete, reload games to show updated status
        if (status.state === "SUCCESS") {
          loadGames();
        }
      } catch (err) {
        console.error("Failed to poll job status:", err);
      }
    };

    pollingRef.current = setInterval(pollStatus, 2000);

    return () => {
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
      }
    };
  }, [bulkJob.jobId, bulkJob.state, loadGames]);

  // Individual game generation
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
          status: response.status === "completed" ? "success" : "error",
          response,
          error: response.status === "completed" ? undefined : response.message,
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

  const getResultStatus = (gameId: number): GenerationResult | undefined => {
    return generationResults.get(gameId);
  };

  const gamesWithStory = games.filter((g) => g.hasStory);
  const gamesWithoutStory = games.filter((g) => !g.hasStory);
  const isBulkRunning = bulkJob.state === "PENDING" || bulkJob.state === "PROGRESS";

  return (
    <div className={styles.container}>
      <header className={styles.header}>
        <div className={styles.titleRow}>
          <h1 className={styles.title}>Flow Generator</h1>
          <button className={styles.logsButton} onClick={() => setLogsOpen(true)}>
            View Logs
          </button>
        </div>
        <p className={styles.subtitle}>
          Generate game flow from play-by-play data
        </p>
      </header>

      <div className={styles.filtersCard}>
        <div className={styles.filterSection}>
          <h3 className={styles.filterSectionTitle}>Date Range</h3>
          <div className={styles.dateRangeRow}>
            <div className={styles.filterGroup}>
              <label className={styles.filterLabel}>Start Date</label>
              <input
                type="date"
                className={styles.input}
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                disabled={isBulkRunning}
              />
            </div>
            <div className={styles.filterGroup}>
              <label className={styles.filterLabel}>End Date</label>
              <input
                type="date"
                className={styles.input}
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                disabled={isBulkRunning}
              />
            </div>
          </div>
        </div>

        <div className={styles.filterSection}>
          <h3 className={styles.filterSectionTitle}>Leagues</h3>
          <div className={styles.leagueCheckboxes}>
            {SUPPORTED_LEAGUES.map((league) => (
              <label key={league} className={styles.checkboxLabel}>
                <input
                  type="checkbox"
                  checked={selectedLeagues.has(league)}
                  onChange={() => toggleLeague(league)}
                  disabled={isBulkRunning}
                />
                <span>{league}</span>
              </label>
            ))}
          </div>
        </div>

        <div className={styles.filterSection}>
          <h3 className={styles.filterSectionTitle}>Options</h3>
          <label className={styles.checkboxLabel}>
            <input
              type="checkbox"
              checked={forceRegenerate}
              onChange={(e) => setForceRegenerate(e.target.checked)}
              disabled={isBulkRunning}
            />
            <span>Force regenerate (overwrite existing flows)</span>
          </label>
        </div>

        <div className={styles.filterActions}>
          <button
            className={styles.secondaryButton}
            onClick={loadGames}
            disabled={loading || isBulkRunning}
          >
            {loading ? "Loading..." : "Preview Games"}
          </button>
          <button
            className={styles.primaryButton}
            onClick={startBulkGeneration}
            disabled={isBulkRunning || selectedLeagues.size === 0}
          >
            {isBulkRunning ? "Running..." : "Start Bulk Generation"}
          </button>
        </div>
      </div>

      {error && <div className={styles.error}>{error}</div>}

      {/* Bulk Job Progress */}
      {bulkJob.jobId && (
        <div className={styles.progressCard}>
          <h3 className={styles.progressTitle}>Bulk Generation Progress</h3>
          <div className={styles.progressStatus}>
            <span
              className={`${styles.statusBadge} ${
                bulkJob.state === "SUCCESS"
                  ? styles.statusSuccess
                  : bulkJob.state === "FAILURE"
                  ? styles.statusError
                  : styles.statusRunning
              }`}
            >
              {bulkJob.state}
            </span>
          </div>
          <div className={styles.progressBar}>
            <div
              className={styles.progressFill}
              style={{
                width: bulkJob.total > 0 ? `${(bulkJob.current / bulkJob.total) * 100}%` : "0%",
              }}
            />
          </div>
          <div className={styles.progressStats}>
            <div className={styles.progressStat}>
              <span className={styles.progressStatValue}>
                {bulkJob.current} / {bulkJob.total}
              </span>
              <span className={styles.progressStatLabel}>Games Processed</span>
            </div>
            <div className={styles.progressStat}>
              <span className={`${styles.progressStatValue} ${styles.successText}`}>
                {bulkJob.successful}
              </span>
              <span className={styles.progressStatLabel}>Successful</span>
            </div>
            <div className={styles.progressStat}>
              <span className={`${styles.progressStatValue} ${styles.errorText}`}>
                {bulkJob.failed}
              </span>
              <span className={styles.progressStatLabel}>Failed</span>
            </div>
            <div className={styles.progressStat}>
              <span className={styles.progressStatValue}>{bulkJob.skipped}</span>
              <span className={styles.progressStatLabel}>Skipped</span>
            </div>
          </div>
        </div>
      )}

      {games.length > 0 && (
        <>
          <div className={styles.statsRow}>
            <div className={styles.stat}>
              <span className={styles.statValue}>{games.length}{totalGames > games.length ? ` / ${totalGames}` : ""}</span>
              <span className={styles.statLabel}>Games Loaded</span>
            </div>
            <div className={styles.stat}>
              <span className={styles.statValue}>{gamesWithStory.length}</span>
              <span className={styles.statLabel}>Has Flow</span>
            </div>
            <div className={styles.stat}>
              <span className={styles.statValue}>{gamesWithoutStory.length}</span>
              <span className={styles.statLabel}>No Flow</span>
            </div>
          </div>

          <div className={styles.gamesSection}>
            <h2 className={styles.sectionTitle}>Games Without Flow</h2>
            {gamesWithoutStory.length === 0 ? (
              <p className={styles.emptyMessage}>All games have flow data!</p>
            ) : (
              <div className={styles.gamesList}>
                {gamesWithoutStory.map((game) => {
                  const result = getResultStatus(game.id);
                  return (
                    <div key={game.id} className={styles.gameCard}>
                      <div className={styles.gameInfo}>
                        <div className={styles.gameMatchup}>
                          {game.awayTeam} @ {game.homeTeam}
                        </div>
                        <div className={styles.gameMeta}>
                          {game.gameDate} | {game.playCount} plays
                        </div>
                      </div>
                      <div className={styles.gameActions}>
                        {result?.status === "generating" && (
                          <span className={styles.statusGenerating}>
                            Generating...
                          </span>
                        )}
                        {result?.status === "success" && (
                          <span className={styles.statusSuccess}>Done</span>
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
                            disabled={
                              result?.status === "generating" || isBulkRunning
                            }
                          >
                            Generate
                          </button>
                        )}
                        <Link
                          href={ROUTES.SPORTS_GAME(game.id)}
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
              <h2 className={styles.sectionTitle}>Games With Flow</h2>
              <div className={styles.gamesList}>
                {gamesWithStory.map((game) => (
                  <div key={game.id} className={styles.gameCard}>
                    <div className={styles.gameInfo}>
                      <div className={styles.gameMatchup}>
                        {game.awayTeam} @ {game.homeTeam}
                      </div>
                      <div className={styles.gameMeta}>
                        {game.gameDate} | {game.playCount} plays
                      </div>
                    </div>
                    <div className={styles.gameActions}>
                      <span className={styles.statusComplete}>Has Flow</span>
                      <button
                        className={styles.regenerateButton}
                        onClick={() => generateStory(game.id)}
                        disabled={
                          getResultStatus(game.id)?.status === "generating" ||
                          isBulkRunning
                        }
                      >
                        Regenerate
                      </button>
                      <Link
                        href={ROUTES.SPORTS_GAME(game.id)}
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

          {nextOffset !== null && (
            <div className={styles.loadMoreContainer}>
              <button
                className={styles.secondaryButton}
                onClick={loadMoreGames}
                disabled={loadingMore || isBulkRunning}
              >
                {loadingMore ? "Loading..." : `Load More (${totalGames - games.length} remaining)`}
              </button>
            </div>
          )}
        </>
      )}

      {!loading && games.length === 0 && !error && (
        <div className={styles.emptyState}>
          <p>
            Configure date range and leagues, then click &quot;Preview
            Games&quot; to see eligible games.
          </p>
          <p className={styles.hint}>
            Or click &quot;Start Bulk Generation&quot; to generate flows for all
            matching games.
          </p>
        </div>
      )}

      <LogsDrawer open={logsOpen} onClose={() => setLogsOpen(false)} tabs={PIPELINE_LOG_TABS} />
    </div>
  );
}
