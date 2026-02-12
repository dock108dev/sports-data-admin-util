"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import styles from "./page.module.css";
import { listTeams, type TeamSummary } from "@/lib/api/sportsAdmin";
import { SUPPORTED_LEAGUES } from "@/lib/constants/sports";

export default function TeamsAdminPage() {
  const [teams, setTeams] = useState<TeamSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [league, setLeague] = useState<string>("");
  const [search, setSearch] = useState("");
  const [offset, setOffset] = useState(0);
  const limit = 50;

  useEffect(() => {
    async function load() {
      try {
        setLoading(true);
        const response = await listTeams({
          league: league || undefined,
          search: search || undefined,
          limit,
          offset,
        });
        setTeams(response.teams);
        setTotal(response.total);
        setError(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        setLoading(false);
      }
    }

    load();
  }, [league, search, offset]);

  const handleSearchChange = (value: string) => {
    setSearch(value);
    setOffset(0);
  };

  const handleLeagueChange = (value: string) => {
    setLeague(value);
    setOffset(0);
  };

  return (
    <div className={styles.container}>
      <header className={styles.header}>
        <h1 className={styles.title}>Teams</h1>
        <p className={styles.subtitle}>Browse teams across all leagues</p>
      </header>

      <div className={styles.filters}>
        <div className={styles.filterGroup}>
          <span className={styles.filterLabel}>League</span>
          <select
            className={styles.select}
            value={league}
            onChange={(e) => handleLeagueChange(e.target.value)}
          >
            <option value="">All Leagues</option>
            {SUPPORTED_LEAGUES.map((lg) => (
              <option key={lg} value={lg}>{lg}</option>
            ))}
          </select>
        </div>
        <div className={styles.filterGroup}>
          <span className={styles.filterLabel}>Search</span>
          <input
            type="text"
            className={styles.input}
            placeholder="Team name..."
            value={search}
            onChange={(e) => handleSearchChange(e.target.value)}
          />
        </div>
      </div>

      {loading ? (
        <div className={styles.loading}>Loading teams...</div>
      ) : error ? (
        <div className={styles.error}>Error: {error}</div>
      ) : teams.length === 0 ? (
        <div className={styles.empty}>No teams found</div>
      ) : (
        <>
          <div className={styles.teamsGrid}>
            {teams.map((team) => (
              <Link
                key={team.id}
                href={`/admin/sports/teams/${team.id}`}
                className={styles.teamCard}
              >
                <div className={styles.teamHeader}>
                  {team.colorLightHex && (
                    <span
                      className={styles.colorSwatch}
                      style={{ backgroundColor: team.colorLightHex }}
                      title={`Light: ${team.colorLightHex}`}
                    />
                  )}
                  {team.colorDarkHex && (
                    <span
                      className={styles.colorSwatch}
                      style={{ backgroundColor: team.colorDarkHex }}
                      title={`Dark: ${team.colorDarkHex}`}
                    />
                  )}
                  <span className={styles.teamAbbr}>{team.abbreviation}</span>
                  <span className={styles.teamName}>{team.name}</span>
                </div>
                <div className={styles.teamMeta}>
                  <span className={styles.metaItem}>{team.leagueCode}</span>
                  <span className={styles.metaDivider}>•</span>
                  <span className={styles.metaItem}>{team.gamesCount} games</span>
                </div>
              </Link>
            ))}
          </div>

          {total > limit && (
            <div className={styles.pagination}>
              <button
                className={styles.pageButton}
                onClick={() => setOffset(Math.max(0, offset - limit))}
                disabled={offset === 0}
              >
                Previous
              </button>
              <span className={styles.pageButton} style={{ cursor: "default" }}>
                {offset + 1}–{Math.min(offset + limit, total)} of {total}
              </span>
              <button
                className={styles.pageButton}
                onClick={() => setOffset(offset + limit)}
                disabled={offset + limit >= total}
              >
                Next
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}

