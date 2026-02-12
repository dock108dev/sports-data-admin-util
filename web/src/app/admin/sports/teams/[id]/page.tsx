"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import styles from "./page.module.css";
import { fetchTeam, updateTeamColors, type TeamDetail } from "@/lib/api/sportsAdmin";

export default function TeamDetailPage() {
  const params = useParams();
  const teamId = Number(params.id);

  const [team, setTeam] = useState<TeamDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lightColor, setLightColor] = useState("#6366f1");
  const [darkColor, setDarkColor] = useState("#6366f1");
  const [colorSaving, setColorSaving] = useState(false);

  useEffect(() => {
    async function load() {
      try {
        setLoading(true);
        const data = await fetchTeam(teamId);
        setTeam(data);
        setLightColor(data.colorLightHex || "#6366f1");
        setDarkColor(data.colorDarkHex || "#6366f1");
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

  async function handleSaveColors() {
    setColorSaving(true);
    try {
      const updated = await updateTeamColors(teamId, {
        colorLightHex: lightColor,
        colorDarkHex: darkColor,
      });
      setTeam(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setColorSaving(false);
    }
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
        <h2 className={styles.sectionTitle}>Team Colors</h2>
        <div className={styles.colorEditor}>
          <div className={styles.colorField}>
            <label className={styles.colorLabel}>Light Mode</label>
            <input
              type="color"
              className={styles.colorInput}
              value={lightColor}
              onChange={(e) => setLightColor(e.target.value)}
            />
            <span className={styles.hexLabel}>{team.colorLightHex || "Not set"}</span>
          </div>
          <div className={styles.colorField}>
            <label className={styles.colorLabel}>Dark Mode</label>
            <input
              type="color"
              className={styles.colorInput}
              value={darkColor}
              onChange={(e) => setDarkColor(e.target.value)}
            />
            <span className={styles.hexLabel}>{team.colorDarkHex || "Not set"}</span>
          </div>
          <button
            className={styles.saveButton}
            onClick={handleSaveColors}
            disabled={colorSaving}
          >
            {colorSaving ? "Saving..." : "Save Colors"}
          </button>
        </div>
        <div className={styles.colorPreview}>
          <span
            className={styles.previewBadge}
            style={{ background: lightColor, color: "#fff" }}
          >
            {team.abbreviation} (Light)
          </span>
          <span
            className={styles.previewBadge}
            style={{ background: darkColor, color: "#fff" }}
          >
            {team.abbreviation} (Dark)
          </span>
        </div>
      </section>

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

