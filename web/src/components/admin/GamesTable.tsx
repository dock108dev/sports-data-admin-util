"use client";

import Link from "next/link";
import { type GameSummary } from "@/lib/api/sportsAdmin";
import styles from "./GamesTable.module.css";

interface GamesTableProps {
  games: GameSummary[];
  detailLinkPrefix?: string;
  showCompleteness?: boolean;
}

/**
 * Table component for displaying game summaries.
 * Shows game metadata, scores, and data completeness indicators.
 */
export function GamesTable({ games, detailLinkPrefix = "/admin/theory-bets/games", showCompleteness = true }: GamesTableProps) {
  return (
    <>
      <table className={styles.table}>
        <thead>
          <tr>
            <th>ID</th>
            <th>Date</th>
            <th>League</th>
            <th>Teams</th>
            <th>Score</th>
            {showCompleteness && (
              <>
                <th>Boxscore</th>
                <th>Players</th>
                <th>Odds</th>
                <th>Social</th>
                  <th>PBP</th>
                <th>Highlights</th>
              </>
            )}
          </tr>
        </thead>
        <tbody>
          {games.length === 0 ? (
            <tr>
                <td colSpan={showCompleteness ? 11 : 5} className={styles.emptyCell}>
                No games found
              </td>
            </tr>
          ) : (
            games.map((game) => {
              const gameIds = game as unknown as { id?: number | string; game_id?: number | string };
              const gameId = gameIds.id ?? gameIds.game_id;
              const hasValidId = gameId !== undefined && gameId !== null && gameId !== "" && gameId !== "NaN";
              const idContent = hasValidId ? (
                <Link href={`${detailLinkPrefix}/${gameId}`} className={styles.link}>
                  {gameId}
                  </Link>
              ) : (
                "—"
              );

              return (
              <tr key={gameId ?? `${game.away_team}-${game.home_team}-${game.game_date}`}>
                <td>{idContent}</td>
                <td>{new Date(game.game_date).toLocaleDateString()}</td>
                <td>{game.league_code}</td>
                <td>
                  {game.away_team} @ {game.home_team}
                </td>
                <td>
                  {game.away_score !== null && game.home_score !== null
                    ? `${game.away_score} - ${game.home_score}`
                    : "—"}
                </td>
                {showCompleteness && (
                  <>
                    <td>
                      <span className={`${styles.statusDot} ${game.has_boxscore ? styles.dotOk : styles.dotMissing}`} />
                      <span className={styles.statusLabel}>Team</span>
                    </td>
                    <td>
                      <span className={`${styles.statusDot} ${game.has_player_stats ? styles.dotOk : styles.dotMissing}`} />
                      <span className={styles.statusLabel}>Players</span>
                    </td>
                    <td>
                      <span className={`${styles.statusDot} ${game.has_odds ? styles.dotOk : styles.dotMissing}`} />
                      <span className={styles.statusLabel}>Odds</span>
                    </td>
                    <td>
                      <span className={`${styles.statusDot} ${game.has_social ? styles.dotOk : styles.dotMissing}`} />
                      <span className={styles.statusLabel}>
                        {game.social_post_count > 0 ? `${game.social_post_count}` : "—"}
                      </span>
                    </td>
                    <td>
                      <span className={`${styles.statusDot} ${game.has_pbp ? styles.dotOk : styles.dotMissing}`} />
                      <span className={styles.statusLabel}>
                        {game.play_count > 0 ? `${game.play_count}` : "—"}
                      </span>
                    </td>
                    <td>
                      <span className={`${styles.statusDot} ${game.has_highlights ? styles.dotOk : styles.dotMissing}`} />
                      <span className={styles.statusLabel}>
                        {game.highlight_count > 0 ? `${game.highlight_count}` : "—"}
                      </span>
                    </td>
                  </>
                )}
              </tr>
            )})
          )}
        </tbody>
      </table>
    </>
  );
}

