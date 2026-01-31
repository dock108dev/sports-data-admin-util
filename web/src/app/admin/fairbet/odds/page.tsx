"use client";

import { useEffect, useState } from "react";
import styles from "./styles.module.css";
import {
  fetchFairbetOdds,
  formatOdds,
  formatSelectionKey,
  formatMarketKey,
  getBestOdds,
  type BetDefinition,
  type FairbetOddsFilters,
} from "@/lib/api/fairbet";
import { createScrapeRun } from "@/lib/api/sportsAdmin";

const LEAGUES = ["NBA", "NHL", "NCAAB"];

export default function FairbetOddsPage() {
  const [bets, setBets] = useState<BetDefinition[]>([]);
  const [booksAvailable, setBooksAvailable] = useState<string[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [selectedLeague, setSelectedLeague] = useState<string>("");
  const [limit] = useState(50);
  const [offset, setOffset] = useState(0);

  // Sync state
  const [syncing, setSyncing] = useState(false);
  const [syncMessage, setSyncMessage] = useState<string | null>(null);

  useEffect(() => {
    loadOdds();
  }, [selectedLeague, offset]);

  async function syncOdds() {
    setSyncing(true);
    setSyncMessage(null);
    setError(null);

    try {
      // Get today's date for the sync
      const today = new Date().toISOString().split("T")[0];

      // If a league is selected, sync just that one; otherwise sync all
      const leaguesToSync = selectedLeague ? [selectedLeague] : LEAGUES;

      const results = await Promise.all(
        leaguesToSync.map((league) =>
          createScrapeRun({
            requestedBy: "fairbet-ui",
            config: {
              leagueCode: league,
              startDate: today,
              endDate: today,
              boxscores: false,
              odds: true,
              social: false,
              pbp: false,
            },
          })
        )
      );

      const runIds = results.map((r) => r.id).join(", ");
      const leagueNames = leaguesToSync.join(", ");
      setSyncMessage(
        `Odds sync started for ${leagueNames} (Run #${runIds}). Refresh in a moment to see results.`
      );

      // Reload odds after a short delay
      setTimeout(() => {
        loadOdds();
      }, 5000);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSyncing(false);
    }
  }

  async function loadOdds() {
    try {
      setLoading(true);
      setError(null);

      const filters: FairbetOddsFilters = {
        limit,
        offset,
      };
      if (selectedLeague) {
        filters.league = selectedLeague;
      }

      const response = await fetchFairbetOdds(filters);
      setBets(response.bets);
      setBooksAvailable(response.books_available);
      setTotal(response.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  function formatGameDate(dateStr: string): string {
    const date = new Date(dateStr);
    return date.toLocaleDateString("en-US", {
      weekday: "short",
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
    });
  }

  function formatLineValue(line: number, marketKey: string): string {
    // 0 is sentinel for no line (moneyline)
    if (line === 0 && marketKey.toLowerCase().includes("h2h")) {
      return "";
    }
    if (line === 0 && marketKey.toLowerCase().includes("moneyline")) {
      return "";
    }
    if (line > 0) {
      return `+${line}`;
    }
    return line.toString();
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
      <header className={styles.header}>
        <h1 className={styles.title}>FairBet Odds Comparison</h1>
        <p className={styles.subtitle}>
          Cross-book odds for upcoming games ({total} bets)
        </p>
      </header>

      <div className={styles.filters}>
        <div className={styles.filterGroup}>
          <label className={styles.filterLabel}>League</label>
          <select
            className={styles.filterSelect}
            value={selectedLeague}
            onChange={(e) => {
              setSelectedLeague(e.target.value);
              setOffset(0);
            }}
          >
            <option value="">All Leagues</option>
            {LEAGUES.map((league) => (
              <option key={league} value={league}>
                {league}
              </option>
            ))}
          </select>
        </div>

        <div className={styles.filterGroup}>
          <span className={styles.filterLabel}>Books Available</span>
          <span className={styles.bookCount}>{booksAvailable.length}</span>
        </div>

        <div className={styles.filterGroup} style={{ marginLeft: "auto" }}>
          <button
            className={styles.syncButton}
            onClick={syncOdds}
            disabled={syncing}
          >
            {syncing
              ? "Syncing..."
              : selectedLeague
              ? `Sync ${selectedLeague} Odds`
              : "Sync All Odds"}
          </button>
        </div>
      </div>

      {syncMessage && (
        <div className={styles.syncMessage}>{syncMessage}</div>
      )}

      {loading ? (
        <div className={styles.loading}>Loading odds...</div>
      ) : bets.length === 0 ? (
        <div className={styles.empty}>
          No upcoming bets found.
          {selectedLeague && " Try selecting a different league."}
        </div>
      ) : (
        <>
          <div className={styles.betsGrid}>
            {bets.map((bet, idx) => {
              const bestBook = getBestOdds(bet.books);
              return (
                <div key={idx} className={styles.betCard}>
                  <div className={styles.betHeader}>
                    <span className={styles.leagueBadge}>{bet.league_code}</span>
                    <span className={styles.gameDate}>
                      {formatGameDate(bet.game_date)}
                    </span>
                  </div>

                  <div className={styles.matchup}>
                    {bet.away_team} @ {bet.home_team}
                  </div>

                  <div className={styles.betType}>
                    <span className={styles.marketType}>
                      {formatMarketKey(bet.market_key)}
                    </span>
                    <span className={styles.selection}>
                      {formatSelectionKey(bet.selection_key)}
                      {formatLineValue(bet.line_value, bet.market_key) && (
                        <span className={styles.line}>
                          {" "}
                          {formatLineValue(bet.line_value, bet.market_key)}
                        </span>
                      )}
                    </span>
                  </div>

                  <div className={styles.booksGrid}>
                    {bet.books.map((book, bookIdx) => (
                      <div
                        key={bookIdx}
                        className={`${styles.bookOdds} ${
                          bestBook && book.book === bestBook.book
                            ? styles.bestOdds
                            : ""
                        }`}
                      >
                        <span className={styles.bookName}>{book.book}</span>
                        <span className={styles.bookPrice}>
                          {formatOdds(book.price)}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>

          <div className={styles.pagination}>
            <button
              className={styles.pageButton}
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - limit))}
            >
              Previous
            </button>
            <span className={styles.pageInfo}>
              Showing {offset + 1}-{Math.min(offset + limit, total)} of {total}
            </span>
            <button
              className={styles.pageButton}
              disabled={offset + limit >= total}
              onClick={() => setOffset(offset + limit)}
            >
              Next
            </button>
          </div>
        </>
      )}
    </div>
  );
}
