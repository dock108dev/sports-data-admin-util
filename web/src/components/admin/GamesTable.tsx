"use client";

import Link from "next/link";
import { type GameSummary } from "@/lib/api/sportsAdmin";
import { ROUTES } from "@/lib/constants/routes";
import styles from "./GamesTable.module.css";

interface GamesTableProps {
  games: GameSummary[];
  detailLinkPrefix?: string;
  showCompleteness?: boolean;
}

/**
 * Table component for displaying game summaries.
 * Shows game metadata and data completeness indicators.
 */
export function GamesTable({ games, detailLinkPrefix = "/admin/sports/games", showCompleteness = true }: GamesTableProps) {
  return (
    <>
      <table className={styles.table}>
        <thead>
          <tr>
            <th>ID</th>
            <th>Date</th>
            <th>League</th>
            <th>Teams</th>
            {showCompleteness && (
              <>
                <th>Boxscore</th>
                <th>Players</th>
                <th>Odds</th>
                <th>Social</th>
                <th>PBP</th>
                <th>Flow</th>
              </>
            )}
          </tr>
        </thead>
        <tbody>
          {games.length === 0 ? (
            <tr>
                <td colSpan={showCompleteness ? 10 : 4} className={styles.emptyCell}>
                No games found
              </td>
            </tr>
          ) : (
            games.map((game) => {
              const gameId = game.id;
              const hasValidId = gameId !== undefined && gameId !== null;
              const idContent = hasValidId ? (
                <Link href={`${detailLinkPrefix}/${gameId}`} className={styles.link}>
                  {gameId}
                  </Link>
              ) : (
                "—"
              );

              return (
              <tr key={gameId ?? `${game.awayTeam}-${game.homeTeam}-${game.gameDate}`}>
                <td>{idContent}</td>
                <td>{new Date(game.gameDate).toLocaleDateString()}</td>
                <td>{game.leagueCode}</td>
                <td>
                  {game.awayTeam} @ {game.homeTeam}
                </td>
                {showCompleteness && (
                  <>
                    <td>
                      <span className={`${styles.statusDot} ${game.hasBoxscore ? styles.dotOk : styles.dotMissing}`} />
                    </td>
                    <td>
                      <span className={`${styles.statusDot} ${game.hasPlayerStats ? styles.dotOk : styles.dotMissing}`} />
                    </td>
                    <td>
                      <span className={`${styles.statusDot} ${game.hasOdds ? styles.dotOk : styles.dotMissing}`} />
                    </td>
                    <td>
                      <span className={`${styles.statusDot} ${game.hasSocial ? styles.dotOk : styles.dotMissing}`} />
                      {game.socialPostCount > 0 && (
                        <span className={styles.statusLabel}>{game.socialPostCount}</span>
                      )}
                    </td>
                    <td>
                      <span className={`${styles.statusDot} ${game.hasPbp ? styles.dotOk : styles.dotMissing}`} />
                      {game.playCount > 0 && (
                        <span className={styles.statusLabel}>{game.playCount}</span>
                      )}
                    </td>
                    <td>
                      <span className={`${styles.statusDot} ${game.hasStory ? styles.dotOk : styles.dotMissing}`} />
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
