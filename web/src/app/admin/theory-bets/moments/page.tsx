"use client";

import { useState, useEffect, useCallback } from "react";
import styles from "./styles.module.css";
import { MomentsTab } from "./components/MomentsTab";
import { GenerationTab } from "./components/GenerationTab";
import { VersionsTab } from "./components/VersionsTab";
import {
  listGames,
  type GameSummary,
} from "@/lib/api/sportsAdmin";

type TabMode = "moments" | "generation" | "versions";

/**
 * Moments Admin Page
 *
 * Unified view for:
 * - Inspecting moments with full trace (why each moment exists)
 * - Generating/regenerating moments for games
 * - Viewing payload version history with diffs
 */
export default function MomentsAdminPage() {
  const [activeTab, setActiveTab] = useState<TabMode>("moments");

  // Filters
  const [leagueCode, setLeagueCode] = useState("NBA");
  const [daysBack, setDaysBack] = useState(7);

  // Game selection
  const [games, setGames] = useState<GameSummary[]>([]);
  const [selectedGameId, setSelectedGameId] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Fetch games
  const fetchGames = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const startDate = new Date();
      startDate.setDate(startDate.getDate() - daysBack);
      const response = await listGames({
        leagues: [leagueCode],
        startDate: startDate.toISOString().split("T")[0],
        limit: 100,
      });
      setGames(response.games);
      // Auto-select first game if none selected
      if (response.games.length > 0 && !selectedGameId) {
        setSelectedGameId(response.games[0].id);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [leagueCode, daysBack, selectedGameId]);

  useEffect(() => {
    fetchGames();
  }, [fetchGames]);

  const selectedGame = games.find((g) => g.id === selectedGameId) || null;

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h1>Moments</h1>
        <p>Inspect, generate, and trace game moments with full visibility</p>
      </div>

      {/* Tabs */}
      <div className={styles.tabs}>
        <button
          className={`${styles.tab} ${activeTab === "moments" ? styles.tabActive : ""}`}
          onClick={() => setActiveTab("moments")}
        >
          Inspect Moments
        </button>
        <button
          className={`${styles.tab} ${activeTab === "generation" ? styles.tabActive : ""}`}
          onClick={() => setActiveTab("generation")}
        >
          Generation
        </button>
        <button
          className={`${styles.tab} ${activeTab === "versions" ? styles.tabActive : ""}`}
          onClick={() => setActiveTab("versions")}
        >
          Payload Versions
        </button>
      </div>

      {/* Controls */}
      <div className={styles.controls}>
        <div className={styles.filters}>
          <div className={styles.filterGroup}>
            <label htmlFor="league">League</label>
            <select
              id="league"
              value={leagueCode}
              onChange={(e) => {
                setLeagueCode(e.target.value);
                setSelectedGameId(null);
              }}
              disabled={loading}
            >
              <option value="NBA">NBA</option>
              <option value="NHL">NHL</option>
              <option value="NCAAB">NCAAB</option>
              <option value="NFL">NFL</option>
              <option value="NCAAF">NCAAF</option>
              <option value="MLB">MLB</option>
            </select>
          </div>

          <div className={styles.filterGroup}>
            <label htmlFor="daysBack">Days Back</label>
            <select
              id="daysBack"
              value={daysBack}
              onChange={(e) => setDaysBack(Number(e.target.value))}
              disabled={loading}
            >
              <option value="3">3 days</option>
              <option value="7">7 days</option>
              <option value="14">14 days</option>
              <option value="30">30 days</option>
            </select>
          </div>

          {activeTab === "moments" && (
            <div className={styles.filterGroup}>
              <label htmlFor="game">Game</label>
              <select
                id="game"
                value={selectedGameId ?? ""}
                onChange={(e) => setSelectedGameId(Number(e.target.value))}
                disabled={loading || games.length === 0}
              >
                {games.length === 0 && <option value="">No games found</option>}
                {games.map((game) => (
                  <option key={game.id} value={game.id}>
                    {game.away_team} @ {game.home_team} ({new Date(game.game_date).toLocaleDateString()})
                  </option>
                ))}
              </select>
            </div>
          )}

          <button
            onClick={fetchGames}
            disabled={loading}
            className={styles.refreshButton}
          >
            {loading ? "Loading..." : "Refresh"}
          </button>
        </div>
      </div>

      {/* Error display */}
      {error && <div className={styles.error}>{error}</div>}

      {/* Tab content */}
      {activeTab === "moments" && (
        <MomentsTab
          gameId={selectedGameId}
          game={selectedGame}
          loading={loading}
        />
      )}
      {activeTab === "generation" && (
        <GenerationTab
          leagueCode={leagueCode}
          daysBack={daysBack}
        />
      )}
      {activeTab === "versions" && (
        <VersionsTab
          gameId={selectedGameId}
          game={selectedGame}
        />
      )}
    </div>
  );
}
