"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import styles from "./page.module.css";
import { fetchTeam, type TeamDetail } from "@/lib/api/sportsAdmin";

export default function TeamDetailPage() {
  const params = useParams();
  const teamId = Number(params.id);

  const [team, setTeam] = useState<TeamDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        setLoading(true);
        const data = await fetchTeam(teamId);
        setTeam(data);
        setError(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        setLoading(false);
      }
    }

    if (teamId) {
      load();
    }
  }, [teamId]);

  if (loading) {
    return <div className={styles.loading}>Loading team...</div>;
  }

  if (error) {
    return <div className={styles.error}>Error: {error}</div>;
  }

  if (!team) {
    return <div className={styles.error}>Team not found</div>;
  }

  const getResultClass = (result: string) => {
    switch (result) {
      case "W": return styles.resultWin;
      case "L": return styles.resultLoss;
      default: return styles.resultDraw;
    }
  };

  return (
    <div className={styles.container}>
      <Link href="/admin/sports/teams" className={styles.backLink}>
        ← Back to teams
      </Link>

      <header className={styles.header}>
        <div className={styles.teamBadge}>
          <span className={styles.abbr}>{team.abbreviation}</span>
          <h1 className={styles.title}>{team.name}</h1>
        </div>
        <div className={styles.meta}>
          <span className={styles.metaItem}>{team.leagueCode}</span>
          {team.location && (
            <span className={styles.metaItem}>{team.location}</span>
          )}
          <span className={styles.metaItem}>
            {team.recentGames.length} recent games
          </span>
        </div>
      </header>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>Recent Games</h2>
        {team.recentGames.length === 0 ? (
          <div className={styles.empty}>No games found for this team</div>
        ) : (
          <table className={styles.gamesTable}>
            <thead>
              <tr>
                <th>Date</th>
                <th>Opponent</th>
                <th>Location</th>
                <th>Score</th>
                <th>Result</th>
              </tr>
            </thead>
            <tbody>
              {team.recentGames.map((game) => (
                <tr key={game.id}>
                  <td>
                    <Link href={`/admin/boxscores/${game.id}`}>
                      {new Date(game.gameDate).toLocaleDateString()}
                    </Link>
                  </td>
                  <td>{game.opponent}</td>
                  <td>
                    {game.isHome ? (
                      <span>Home</span>
                    ) : (
                      <span>Away</span>
                    )}
                  </td>
                  <td>{game.score}</td>
                  <td className={getResultClass(game.result)}>
                    {game.result}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}

