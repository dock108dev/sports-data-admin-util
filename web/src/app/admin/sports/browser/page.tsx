"use client";

import { useState, useMemo, useEffect, useCallback } from "react";
import Link from "next/link";
import styles from "./page.module.css";
import { useGameFilters } from "@/lib/hooks/useGameFilters";
import { GameFiltersForm } from "@/components/admin/GameFiltersForm";
import { GamesTable } from "@/components/admin/GamesTable";
import { getQuickDateRange } from "@/lib/utils/dateFormat";
import { listTeams, listScrapeRuns, type TeamSummary, type ScrapeRunResponse } from "@/lib/api/sportsAdmin";
import { SUPPORTED_LEAGUES } from "@/lib/constants/sports";
import { getStatusClass } from "@/lib/utils/status";

type ViewMode = "games" | "teams" | "runs";

const PAGE_SIZE_OPTIONS = [10, 25, 50, 100];

/**
 * Unified data browser - replaces Dashboard, Games, and Teams pages.
 * Allows switching between Games, Teams, and Scrape Runs with consistent filtering.
 */
export default function UnifiedBrowserPage() {
  const [viewMode, setViewMode] = useState<ViewMode>("games");
  const [teams, setTeams] = useState<TeamSummary[]>([]);
  const [runs, setRuns] = useState<ScrapeRunResponse[]>([]);
  const [teamsLoading, setTeamsLoading] = useState(false);
  const [runsLoading, setRunsLoading] = useState(false);
  const [teamsError, setTeamsError] = useState<string | null>(null);
  const [runsError, setRunsError] = useState<string | null>(null);
  const [teamLeague, setTeamLeague] = useState<string>("");
  const [teamSearch, setTeamSearch] = useState("");
  const [teamOffset, setTeamOffset] = useState(0);
  const [teamsTotal, setTeamsTotal] = useState(0);
  const teamLimit = 50;

  const {
    formFilters,
    setFormFilters,
    appliedFilters,
    games,
    total,
    aggregates,
    loading: gamesLoading,
    error: gamesError,
    applyFilters,
    resetFilters,
  } = useGameFilters({ defaultLimit: 25 });

  const currentPage = Math.floor((appliedFilters.offset || 0) / (appliedFilters.limit || 25)) + 1;
  const totalPages = Math.ceil(total / (appliedFilters.limit || 25));
  const startItem = (appliedFilters.offset || 0) + 1;
  const endItem = Math.min((appliedFilters.offset || 0) + (appliedFilters.limit || 25), total);

  const loadTeams = useCallback(async () => {
    setTeamsLoading(true);
    setTeamsError(null);
    try {
      const response = await listTeams({
        league: teamLeague || undefined,
        search: teamSearch || undefined,
        limit: teamLimit,
        offset: teamOffset,
      });
      setTeams(response.teams);
      setTeamsTotal(response.total);
    } catch (err) {
      setTeamsError(err instanceof Error ? err.message : String(err));
    } finally {
      setTeamsLoading(false);
    }
  }, [teamLeague, teamSearch, teamLimit, teamOffset]);

  const loadRuns = useCallback(async () => {
    setRunsLoading(true);
    setRunsError(null);
    try {
      const response = await listScrapeRuns();
      setRuns(response);
    } catch (err) {
      setRunsError(err instanceof Error ? err.message : String(err));
    } finally {
      setRunsLoading(false);
    }
  }, []);

  // Load teams/runs when view mode changes
  useEffect(() => {
    if (viewMode === "teams") {
      loadTeams();
    } else if (viewMode === "runs") {
      loadRuns();
    }
  }, [viewMode, loadTeams, loadRuns]);

  const handlePageChange = (newPage: number) => {
    const limit = appliedFilters.limit || 25;
    const newOffset = (newPage - 1) * limit;
    const nextFilters = { ...formFilters, offset: newOffset };
    setFormFilters(nextFilters);
    applyFilters(nextFilters);
  };

  const handlePageSizeChange = (newSize: number) => {
    const nextFilters = { ...formFilters, limit: newSize, offset: 0 };
    setFormFilters(nextFilters);
    applyFilters(nextFilters);
  };

  const handleQuickDateRange = (days: number) => {
    const { startDate, endDate } = getQuickDateRange(days);
    setFormFilters((prev) => ({ ...prev, startDate, endDate }));
  };

  // Stats for the full filtered set (aggregates returned by the API)
  const aggregateStats = useMemo(() => {
    if (viewMode === "games" && total > 0 && aggregates) {
      return {
        boxscorePercent: Math.round((aggregates.withBoxscore / total) * 100),
        playerStatsPercent: Math.round((aggregates.withPlayerStats / total) * 100),
        oddsPercent: Math.round((aggregates.withOdds / total) * 100),
        socialPercent: Math.round((aggregates.withSocial / total) * 100),
        pbpPercent: Math.round((aggregates.withPbp / total) * 100),
        storyPercent: Math.round((aggregates.withStory / total) * 100),
      };
    }
    return null;
  }, [aggregates, total, viewMode]);

  return (
    <div className={styles.container}>
      <header className={styles.header}>
        <h1 className={styles.title}>Data Browser</h1>
        <p className={styles.subtitle}>Browse games, teams, and scrape runs</p>
      </header>

      <div className={styles.viewModeTabs}>
        <button
          className={`${styles.tab} ${viewMode === "games" ? styles.tabActive : ""}`}
          onClick={() => setViewMode("games")}
        >
          Games
        </button>
        <button
          className={`${styles.tab} ${viewMode === "teams" ? styles.tabActive : ""}`}
          onClick={() => {
            setViewMode("teams");
            loadTeams();
          }}
        >
          Teams
        </button>
        <button
          className={`${styles.tab} ${viewMode === "runs" ? styles.tabActive : ""}`}
          onClick={() => {
            setViewMode("runs");
            loadRuns();
          }}
        >
          Scrape Runs
        </button>
      </div>

      {viewMode === "games" && (
        <>
          <GameFiltersForm
            filters={formFilters}
            onFiltersChange={setFormFilters}
            onApply={() => applyFilters(formFilters)}
            onReset={resetFilters}
            onQuickDateRange={handleQuickDateRange}
          />

          {/* Stats row - Total is the full filtered count */}
          <div className={styles.statsRow}>
            <div className={styles.stat}>
              <span className={styles.statValue}>{total.toLocaleString()}</span>
              <span className={styles.statLabel}>Total Games</span>
            </div>
            {aggregateStats && (
              <>
                <div className={styles.stat}>
                  <span className={styles.statValue}>{aggregateStats.boxscorePercent}%</span>
                  <span className={styles.statLabel}>Boxscores</span>
                </div>
                <div className={styles.stat}>
                  <span className={styles.statValue}>{aggregateStats.playerStatsPercent}%</span>
                  <span className={styles.statLabel}>Player Stats</span>
                </div>
                <div className={styles.stat}>
                  <span className={styles.statValue}>{aggregateStats.oddsPercent}%</span>
                  <span className={styles.statLabel}>Odds</span>
                </div>
                <div className={styles.stat}>
                  <span className={styles.statValue}>{aggregateStats.socialPercent}%</span>
                  <span className={styles.statLabel}>Social</span>
                </div>
                <div className={styles.stat}>
                  <span className={styles.statValue}>{aggregateStats.pbpPercent}%</span>
                  <span className={styles.statLabel}>Play-by-Play</span>
                </div>
                <div className={styles.stat}>
                  <span className={styles.statValue}>{aggregateStats.storyPercent}%</span>
                  <span className={styles.statLabel}>Flow</span>
                </div>
              </>
            )}
          </div>

          {total > 0 && (
            <div className={styles.paginationControls}>
              <div className={styles.paginationInfo}>
                Showing {startItem.toLocaleString()} - {endItem.toLocaleString()} of {total.toLocaleString()} games
              </div>
              <div className={styles.paginationRight}>
                <label className={styles.pageSizeLabel}>
                  Page size:
                  <select
                    className={styles.pageSizeSelect}
                    value={appliedFilters.limit || 25}
                    onChange={(e) => handlePageSizeChange(Number(e.target.value))}
                  >
                    {PAGE_SIZE_OPTIONS.map((size) => (
                      <option key={size} value={size}>
                        {size}
                      </option>
                    ))}
                  </select>
                </label>
                <div className={styles.paginationButtons}>
                  <button
                    className={styles.paginationButton}
                    type="button"
                    onClick={() => handlePageChange(1)}
                    disabled={currentPage === 1 || gamesLoading}
                  >
                    First
                  </button>
                  <button
                    className={styles.paginationButton}
                    type="button"
                    onClick={() => handlePageChange(currentPage - 1)}
                    disabled={currentPage === 1 || gamesLoading}
                  >
                    Previous
                  </button>
                  <span className={styles.pageInfo}>
                    Page {currentPage} of {totalPages}
                  </span>
                  <button
                    className={styles.paginationButton}
                    type="button"
                    onClick={() => handlePageChange(currentPage + 1)}
                    disabled={currentPage >= totalPages || gamesLoading}
                  >
                    Next
                  </button>
                  <button
                    className={styles.paginationButton}
                    type="button"
                    onClick={() => handlePageChange(totalPages)}
                    disabled={currentPage >= totalPages || gamesLoading}
                  >
                    Last
                  </button>
                </div>
              </div>
            </div>
          )}

          {gamesError && <div className={styles.error}>{gamesError}</div>}
          {gamesLoading && games.length === 0 && <div className={styles.loading}>Loading...</div>}
          {games.length > 0 && <GamesTable games={games} detailLinkPrefix="/admin/sports/games" showCompleteness />}
          {!gamesLoading && games.length === 0 && !gamesError && (
            <div className={styles.empty}>No games found. Try adjusting your filters.</div>
          )}
        </>
      )}

      {viewMode === "teams" && (
        <>
          <div className={styles.filtersCard}>
            <div className={styles.filterRow}>
              <div className={styles.filterGroup}>
                <label className={styles.filterLabel}>League</label>
                <select
                  className={styles.input}
                  value={teamLeague}
                  onChange={(e) => {
                    setTeamLeague(e.target.value);
                    setTeamOffset(0);
                  }}
                >
                  <option value="">All Leagues</option>
                  {SUPPORTED_LEAGUES.map((lg) => (
                    <option key={lg} value={lg}>
                      {lg}
                    </option>
                  ))}
                </select>
              </div>
              <div className={styles.filterGroup}>
                <label className={styles.filterLabel}>Search</label>
                <input
                  type="text"
                  className={styles.input}
                  placeholder="Team name..."
                  value={teamSearch}
                  onChange={(e) => {
                    setTeamSearch(e.target.value);
                    setTeamOffset(0);
                  }}
                />
              </div>
            </div>
          </div>

          {teamsLoading && <div className={styles.loading}>Loading teams...</div>}
          {teamsError && <div className={styles.error}>Error: {teamsError}</div>}
          {!teamsLoading && !teamsError && teams.length === 0 && <div className={styles.empty}>No teams found</div>}
          {!teamsLoading && !teamsError && teams.length > 0 && (
            <>
              <div className={styles.teamsGrid}>
                {teams.map((team) => (
                  <Link key={team.id} href={`/admin/teams/${team.id}`} className={styles.teamCard}>
                    <div className={styles.teamHeader}>
                      <span className={styles.teamAbbr}>{team.abbreviation}</span>
                      <span className={styles.teamName}>{team.name}</span>
                    </div>
                    <div className={styles.teamMeta}>
                      <span className={styles.metaItem}>🏆 {team.leagueCode}</span>
                      <span className={styles.metaItem}>🎮 {team.gamesCount} games</span>
                    </div>
                  </Link>
                ))}
              </div>

              {teamsTotal > teamLimit && (
                <div className={styles.pagination}>
                  <button
                    className={styles.paginationButton}
                    onClick={() => setTeamOffset(Math.max(0, teamOffset - teamLimit))}
                    disabled={teamOffset === 0}
                  >
                    ← Previous
                  </button>
                  <span className={styles.pageInfo}>
                    {teamOffset + 1}–{Math.min(teamOffset + teamLimit, teamsTotal)} of {teamsTotal}
                  </span>
                  <button
                    className={styles.paginationButton}
                    onClick={() => setTeamOffset(teamOffset + teamLimit)}
                    disabled={teamOffset + teamLimit >= teamsTotal}
                  >
                    Next →
                  </button>
                </div>
              )}
            </>
          )}
        </>
      )}

      {viewMode === "runs" && (
        <>
          {runsLoading && <div className={styles.loading}>Loading scrape runs...</div>}
          {runsError && <div className={styles.error}>Error: {runsError}</div>}
          {!runsLoading && !runsError && runs.length === 0 && <div className={styles.empty}>No scrape runs found</div>}
          {!runsLoading && !runsError && runs.length > 0 && (
            <div className={styles.runsList}>
              {runs.map((run) => (
                <Link key={run.id} href={`/admin/sports/ingestion/${run.id}`} className={styles.runCard}>
                  <div className={styles.runHeader}>
                    <span className={`${styles.runStatus} ${styles[getStatusClass(run.status)]}`} />
                    <div className={styles.runInfo}>
                      <div className={styles.runTitle}>
                        {run.league_code} {run.season || ""} — {run.status}
                      </div>
                      <div className={styles.runMeta}>
                        {run.start_date} to {run.end_date}
                      </div>
                    </div>
                  </div>
                </Link>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
