"use client";

import { useState, useEffect, useCallback } from "react";
import styles from "./styles.module.css";
import {
  generateMissingTimelines,
  listMissingTimelines,
  listExistingTimelines,
  regenerateTimelines,
  type MissingTimelineGame,
  type ExistingTimelineGame,
} from "@/lib/api/sportsAdmin";

type TabMode = "missing" | "existing";

/**
 * Timeline generation admin page.
 *
 * Allows administrators to:
 * - View games missing timeline artifacts and generate them
 * - View games with existing timelines and regenerate them (for fixes)
 */
export default function TimelinesAdminPage() {
  // Tab state
  const [activeTab, setActiveTab] = useState<TabMode>("missing");

  // Filters
  const [leagueCode, setLeagueCode] = useState("NBA");
  const [daysBack, setDaysBack] = useState(7);

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
    if (activeTab === "missing") {
      fetchMissingGames();
    } else {
      fetchExistingGames();
    }
  }, [activeTab, fetchMissingGames, fetchExistingGames]);

  // Handle generate missing timelines
  const handleGenerateMissing = async () => {
    if (missingGames.length === 0) return;
    if (!window.confirm(`Generate timelines for ${missingGames.length} games?`)) return;

    setProcessing(true);
    setError(null);
    setSuccess(null);

    try {
      const result = await generateMissingTimelines({ leagueCode, daysBack });
      setSuccess(
        `Generated ${result.games_successful}/${result.games_processed} timelines.` +
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
    if (!window.confirm(`Regenerate ALL ${count} timelines? This may take a while.`)) return;

    setProcessing(true);
    setError(null);
    setSuccess(null);

    try {
      const result = await regenerateTimelines({ leagueCode, daysBack });
      setSuccess(
        `Regenerated ${result.games_successful}/${result.games_processed} timelines.` +
          (result.games_failed > 0 ? ` (${result.games_failed} failed)` : "")
      );
      fetchExistingGames();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setProcessing(false);
    }
  };

  // Handle regenerate selected games
  const handleRegenerateSelected = async () => {
    if (selectedGameIds.size === 0) return;
    if (!window.confirm(`Regenerate ${selectedGameIds.size} selected timelines?`)) return;

    setProcessing(true);
    setError(null);
    setSuccess(null);

    try {
      const result = await regenerateTimelines({ gameIds: Array.from(selectedGameIds), leagueCode });
      setSuccess(
        `Regenerated ${result.games_successful}/${result.games_processed} timelines.` +
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

  // Current games based on tab
  const currentGames = activeTab === "missing" ? missingGames : existingGames;

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

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h1>Timeline Management</h1>
        <p>Generate and regenerate timeline artifacts for games</p>
      </div>

      {/* Tabs */}
      <div className={styles.tabs}>
        <button
          className={`${styles.tab} ${activeTab === "missing" ? styles.tabActive : ""}`}
          onClick={() => setActiveTab("missing")}
          disabled={processing}
        >
          Missing Timelines
        </button>
        <button
          className={`${styles.tab} ${activeTab === "existing" ? styles.tabActive : ""}`}
          onClick={() => setActiveTab("existing")}
          disabled={processing}
        >
          Existing Timelines
        </button>
      </div>

      {/* Filters */}
      <div className={styles.controls}>
        <div className={styles.filters}>
          <div className={styles.filterGroup}>
            <label htmlFor="league">League</label>
            <select
              id="league"
              value={leagueCode}
              onChange={(e) => setLeagueCode(e.target.value)}
              disabled={loading || processing}
            >
              <option value="NBA">NBA</option>
              <option value="NHL">NHL</option>
              <option value="NCAAB">NCAAB</option>
            </select>
          </div>

          <div className={styles.filterGroup}>
            <label htmlFor="daysBack">Days Back</label>
            <select
              id="daysBack"
              value={daysBack}
              onChange={(e) => setDaysBack(Number(e.target.value))}
              disabled={loading || processing}
            >
              <option value="3">3 days</option>
              <option value="7">7 days</option>
              <option value="14">14 days</option>
              <option value="30">30 days</option>
              <option value="60">60 days</option>
            </select>
          </div>

          <button
            onClick={activeTab === "missing" ? fetchMissingGames : fetchExistingGames}
            disabled={loading || processing}
            className={styles.refreshButton}
          >
            {loading ? "Loading..." : "Refresh"}
          </button>
        </div>

        <div className={styles.actions}>
          {activeTab === "missing" ? (
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
                onClick={handleRegenerateSelected}
                disabled={loading || processing || selectedGameIds.size === 0}
                className={styles.regenerateButton}
              >
                {processing ? "Processing..." : `Regenerate Selected (${selectedGameIds.size})`}
              </button>
              <button
                onClick={handleRegenerateAll}
                disabled={loading || processing || existingGames.length === 0}
                className={styles.generateButton}
              >
                {processing ? "Processing..." : `Regenerate All (${existingGames.length})`}
              </button>
            </>
          )}
        </div>
      </div>

      {/* Status messages */}
      {error && <div className={styles.error}>{error}</div>}
      {success && <div className={styles.success}>{success}</div>}

      {/* Stats */}
      <div className={styles.stats}>
        <div className={styles.statCard}>
          <div className={styles.statValue}>
            {activeTab === "missing" ? missingGames.length : existingGames.length}
          </div>
          <div className={styles.statLabel}>
            {activeTab === "missing" ? "Games Missing Timelines" : "Games with Timelines"}
          </div>
        </div>
      </div>

      {/* Table */}
      {loading ? (
        <div className={styles.loading}>Loading games...</div>
      ) : currentGames.length === 0 ? (
        <div className={styles.empty}>
          {activeTab === "missing"
            ? `No games found missing timeline artifacts in the last ${daysBack} days.`
            : `No games found with timeline artifacts in the last ${daysBack} days.`}
        </div>
      ) : (
        <div className={styles.tableContainer}>
          <table className={styles.table}>
            <thead>
              <tr>
                {activeTab === "existing" && (
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
                {activeTab === "existing" && <th>Generated</th>}
              </tr>
            </thead>
            <tbody>
              {activeTab === "missing"
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
