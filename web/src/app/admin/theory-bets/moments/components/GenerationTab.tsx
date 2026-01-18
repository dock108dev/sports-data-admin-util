"use client";

import { useState, useEffect, useCallback } from "react";
import styles from "../styles.module.css";
import {
  generateMissingTimelines,
  listMissingTimelines,
  listExistingTimelines,
  regenerateTimelines,
  runPipelineBatch,
  type MissingTimelineGame,
  type ExistingTimelineGame,
} from "@/lib/api/sportsAdmin";

type SubTab = "missing" | "existing";

interface GenerationTabProps {
  leagueCode: string;
  daysBack: number;
}

/**
 * Tab for generating and regenerating moments.
 * Reuses the timelines generation API.
 */
export function GenerationTab({ leagueCode, daysBack }: GenerationTabProps) {
  const [activeSubTab, setActiveSubTab] = useState<SubTab>("missing");

  // Data state
  const [missingGames, setMissingGames] = useState<MissingTimelineGame[]>([]);
  const [existingGames, setExistingGames] = useState<ExistingTimelineGame[]>([]);

  // Selection state
  const [selectedGameIds, setSelectedGameIds] = useState<Set<number>>(new Set());

  // Loading/status state
  const [loading, setLoading] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // Fetch missing games
  const fetchMissingGames = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await listMissingTimelines({ leagueCode, daysBack });
      setMissingGames(response.games);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [leagueCode, daysBack]);

  // Fetch existing games
  const fetchExistingGames = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await listExistingTimelines({ leagueCode, daysBack });
      setExistingGames(response.games);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [leagueCode, daysBack]);

  // Fetch data when tab or filters change
  useEffect(() => {
    setSelectedGameIds(new Set());
    if (activeSubTab === "missing") {
      fetchMissingGames();
    } else {
      fetchExistingGames();
    }
  }, [activeSubTab, fetchMissingGames, fetchExistingGames]);

  // Handle generate missing timelines
  const handleGenerateMissing = async () => {
    if (missingGames.length === 0) return;
    if (!window.confirm(`Generate moments for ${missingGames.length} games?`)) return;

    setProcessing(true);
    setError(null);
    setSuccess(null);

    try {
      const result = await generateMissingTimelines({ leagueCode, daysBack });
      setSuccess(
        `Generated ${result.games_successful}/${result.games_processed} games.` +
          (result.games_failed > 0 ? ` (${result.games_failed} failed)` : "")
      );
      fetchMissingGames();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setProcessing(false);
    }
  };

  // Handle regenerate all existing timelines
  const handleRegenerateAll = async () => {
    const count = existingGames.length;
    if (count === 0) return;
    if (!window.confirm(`Regenerate ALL ${count} games? This may take a while.`)) return;

    setProcessing(true);
    setError(null);
    setSuccess(null);

    try {
      const result = await regenerateTimelines({ leagueCode, daysBack });
      setSuccess(
        `Regenerated ${result.games_successful}/${result.games_processed} games.` +
          (result.games_failed > 0 ? ` (${result.games_failed} failed)` : "")
      );
      fetchExistingGames();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setProcessing(false);
    }
  };

  // Handle regenerate selected games (old system - no traces)
  const handleRegenerateSelected = async () => {
    if (selectedGameIds.size === 0) return;
    if (!window.confirm(`Regenerate ${selectedGameIds.size} selected games?`)) return;

    setProcessing(true);
    setError(null);
    setSuccess(null);

    try {
      const result = await regenerateTimelines({ gameIds: Array.from(selectedGameIds), leagueCode });
      setSuccess(
        `Regenerated ${result.games_successful}/${result.games_processed} games.` +
          (result.games_failed > 0 ? ` (${result.games_failed} failed)` : "")
      );
      setSelectedGameIds(new Set());
      fetchExistingGames();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setProcessing(false);
    }
  };

  // Handle run pipeline for selected games (new system - with traces)
  const handleRunPipelineSelected = async () => {
    if (selectedGameIds.size === 0) return;
    if (!window.confirm(`Run pipeline for ${selectedGameIds.size} selected games? This creates traces and payload versions.`)) return;

    setProcessing(true);
    setError(null);
    setSuccess(null);

    try {
      const result = await runPipelineBatch(Array.from(selectedGameIds));
      setSuccess(
        `Pipeline completed: ${result.successful}/${result.total} games.` +
          (result.failed > 0 ? ` (${result.failed} failed)` : "") +
          " Traces and payload versions created."
      );
      setSelectedGameIds(new Set());
      fetchExistingGames();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setProcessing(false);
    }
  };

  // Toggle game selection
  const toggleGameSelection = (gameId: number) => {
    setSelectedGameIds((prev) => {
      const next = new Set(prev);
      if (next.has(gameId)) {
        next.delete(gameId);
      } else {
        next.add(gameId);
      }
      return next;
    });
  };

  // Select/deselect all
  const toggleSelectAll = () => {
    if (selectedGameIds.size === existingGames.length) {
      setSelectedGameIds(new Set());
    } else {
      setSelectedGameIds(new Set(existingGames.map((g) => g.game_id)));
    }
  };

  // Format relative time
  const formatRelativeTime = (isoDate: string) => {
    const date = new Date(isoDate);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
    if (diffHours < 1) return "< 1 hour ago";
    if (diffHours < 24) return `${diffHours}h ago`;
    const diffDays = Math.floor(diffHours / 24);
    return `${diffDays}d ago`;
  };

  const currentGames = activeSubTab === "missing" ? missingGames : existingGames;

  return (
    <div>
      {/* Sub-tabs */}
      <div className={styles.tabs} style={{ marginBottom: "1.5rem" }}>
        <button
          className={`${styles.tab} ${activeSubTab === "missing" ? styles.tabActive : ""}`}
          onClick={() => setActiveSubTab("missing")}
          disabled={processing}
        >
          Missing Moments
        </button>
        <button
          className={`${styles.tab} ${activeSubTab === "existing" ? styles.tabActive : ""}`}
          onClick={() => setActiveSubTab("existing")}
          disabled={processing}
        >
          Existing Moments
        </button>
      </div>

      {/* Actions */}
      <div style={{ display: "flex", gap: "0.75rem", marginBottom: "1.5rem" }}>
        {activeSubTab === "missing" ? (
          <button
            onClick={handleGenerateMissing}
            disabled={loading || processing || missingGames.length === 0}
            className={styles.generateButton}
          >
            {processing ? "Generating..." : `Generate All (${missingGames.length})`}
          </button>
        ) : (
          <>
            <button
              onClick={handleRunPipelineSelected}
              disabled={loading || processing || selectedGameIds.size === 0}
              className={styles.generateButton}
              title="Run full pipeline with traces and payload versions"
            >
              {processing ? "Processing..." : `Run Pipeline (${selectedGameIds.size})`}
            </button>
            <button
              onClick={handleRegenerateSelected}
              disabled={loading || processing || selectedGameIds.size === 0}
              className={styles.regenerateButton}
              title="Quick regenerate without traces"
            >
              {processing ? "Processing..." : `Quick Regen (${selectedGameIds.size})`}
            </button>
            <button
              onClick={handleRegenerateAll}
              disabled={loading || processing || existingGames.length === 0}
              className={styles.regenerateButton}
              title="Quick regenerate all without traces"
            >
              {processing ? "Processing..." : `Quick Regen All (${existingGames.length})`}
            </button>
          </>
        )}
        <button
          onClick={activeSubTab === "missing" ? fetchMissingGames : fetchExistingGames}
          disabled={loading || processing}
          className={styles.refreshButton}
        >
          {loading ? "Loading..." : "Refresh"}
        </button>
      </div>

      {/* Status messages */}
      {error && <div className={styles.error}>{error}</div>}
      {success && <div className={styles.success}>{success}</div>}

      {/* Stats */}
      <div className={styles.stats}>
        <div className={styles.statCard}>
          <div className={styles.statValue}>{currentGames.length}</div>
          <div className={styles.statLabel}>
            {activeSubTab === "missing" ? "Games Missing Moments" : "Games with Moments"}
          </div>
        </div>
      </div>

      {/* Table */}
      {loading ? (
        <div className={styles.loading}>Loading games...</div>
      ) : currentGames.length === 0 ? (
        <div className={styles.empty}>
          {activeSubTab === "missing"
            ? `No games found missing moments in the last ${daysBack} days.`
            : `No games found with moments in the last ${daysBack} days.`}
        </div>
      ) : (
        <div className={styles.tableContainer}>
          <table className={styles.table}>
            <thead>
              <tr>
                {activeSubTab === "existing" && (
                  <th>
                    <input
                      type="checkbox"
                      checked={selectedGameIds.size === existingGames.length && existingGames.length > 0}
                      onChange={toggleSelectAll}
                      disabled={processing}
                    />
                  </th>
                )}
                <th>Game ID</th>
                <th>Date</th>
                <th>Matchup</th>
                <th>Status</th>
                {activeSubTab === "existing" && <th>Generated</th>}
              </tr>
            </thead>
            <tbody>
              {activeSubTab === "missing"
                ? missingGames.map((game) => (
                    <tr key={game.game_id}>
                      <td>{game.game_id}</td>
                      <td>{new Date(game.game_date).toLocaleDateString()}</td>
                      <td>{game.away_team} @ {game.home_team}</td>
                      <td><span className={styles.statusBadge}>{game.status}</span></td>
                    </tr>
                  ))
                : existingGames.map((game) => (
                    <tr key={game.game_id}>
                      <td>
                        <input
                          type="checkbox"
                          checked={selectedGameIds.has(game.game_id)}
                          onChange={() => toggleGameSelection(game.game_id)}
                          disabled={processing}
                        />
                      </td>
                      <td>{game.game_id}</td>
                      <td>{new Date(game.game_date).toLocaleDateString()}</td>
                      <td>{game.away_team} @ {game.home_team}</td>
                      <td><span className={styles.statusBadge}>{game.status}</span></td>
                      <td>{formatRelativeTime(game.timeline_generated_at)}</td>
                    </tr>
                  ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
