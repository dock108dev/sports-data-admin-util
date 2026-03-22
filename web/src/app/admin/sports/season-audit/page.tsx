"use client";

import { useState } from "react";
import styles from "./page.module.css";
import { getSeasonAudit, type SeasonAuditResponse } from "@/lib/api/sportsAdmin";
import { SUPPORTED_LEAGUES } from "@/lib/constants/sports";

const SEASON_TYPES = ["regular", "playoff", "preseason"] as const;

function barColor(pct: number): string {
  if (pct >= 90) return styles.barGreen;
  if (pct >= 70) return styles.barYellow;
  return styles.barRed;
}

function textColor(pct: number): string {
  if (pct >= 90) return styles.green;
  if (pct >= 70) return styles.yellow;
  return styles.red;
}

interface CoverageRow {
  label: string;
  count: number;
  pct: number;
}

export default function SeasonAuditPage() {
  const [league, setLeague] = useState<string>("NBA");
  const [season, setSeason] = useState<number>(new Date().getFullYear());
  const [seasonType, setSeasonType] = useState<string>("regular");
  const [data, setData] = useState<SeasonAuditResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleAudit = async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await getSeasonAudit({ league, season, seasonType });
      setData(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setData(null);
    } finally {
      setLoading(false);
    }
  };

  const coverageRows: CoverageRow[] = data
    ? [
        { label: "Boxscores", count: data.withBoxscore, pct: data.boxscorePct },
        { label: "Player Stats", count: data.withPlayerStats, pct: data.playerStatsPct },
        { label: "Odds", count: data.withOdds, pct: data.oddsPct },
        { label: "Play-by-Play", count: data.withPbp, pct: data.pbpPct },
        { label: "Social", count: data.withSocial, pct: data.socialPct },
        { label: "Game Flow", count: data.withFlow, pct: data.flowPct },
        { label: "Advanced Stats", count: data.withAdvancedStats, pct: data.advancedStatsPct },
      ]
    : [];

  return (
    <div className={styles.container}>
      <header className={styles.header}>
        <h1 className={styles.title}>Season Audit</h1>
        <p className={styles.subtitle}>Check data completeness for a league season</p>
      </header>

      <div className={styles.controls}>
        <div className={styles.field}>
          <span className={styles.fieldLabel}>League</span>
          <select
            className={styles.select}
            value={league}
            onChange={(e) => setLeague(e.target.value)}
          >
            {SUPPORTED_LEAGUES.map((lg) => (
              <option key={lg} value={lg}>
                {lg}
              </option>
            ))}
          </select>
        </div>

        <div className={styles.field}>
          <span className={styles.fieldLabel}>Season</span>
          <input
            className={styles.input}
            type="number"
            value={season}
            onChange={(e) => setSeason(Number(e.target.value))}
            min={2000}
            max={2099}
          />
        </div>

        <div className={styles.field}>
          <span className={styles.fieldLabel}>Type</span>
          <select
            className={styles.select}
            value={seasonType}
            onChange={(e) => setSeasonType(e.target.value)}
          >
            {SEASON_TYPES.map((st) => (
              <option key={st} value={st}>
                {st}
              </option>
            ))}
          </select>
        </div>

        <button className={styles.button} onClick={handleAudit} disabled={loading}>
          {loading ? "Auditing..." : "Audit"}
        </button>
      </div>

      {error && <div className={styles.error}>{error}</div>}

      {data && (
        <div className={styles.summaryCard}>
          <div className={styles.summaryHeader}>
            <span className={styles.summaryTitle}>
              {data.leagueCode} {data.season} ({data.seasonType})
            </span>
            <span className={styles.summaryMeta}>
              {data.teamsWithGames} teams
              {data.expectedTeams != null && ` / ${data.expectedTeams} expected`}
            </span>
          </div>

          {/* Big numbers */}
          <div className={styles.bigNumbers}>
            <div className={styles.bigNumber}>
              <div className={styles.bigNumberValue}>
                {data.totalGames.toLocaleString()}
              </div>
              <div className={styles.bigNumberLabel}>Games Found</div>
            </div>
            {data.expectedGames != null && (
              <div className={styles.bigNumber}>
                <div className={styles.bigNumberValue}>
                  {data.expectedGames.toLocaleString()}
                </div>
                <div className={styles.bigNumberLabel}>Expected</div>
              </div>
            )}
            {data.coveragePct != null && (
              <div className={styles.bigNumber}>
                <div className={`${styles.bigNumberValue} ${textColor(data.coveragePct)}`}>
                  {data.coveragePct}%
                </div>
                <div className={styles.bigNumberLabel}>Season Coverage</div>
              </div>
            )}
          </div>

          {/* Coverage progress bar */}
          {data.expectedGames != null && (
            <div style={{ marginBottom: "1.5rem" }}>
              <div className={styles.progressBarOuter}>
                <div
                  className={`${styles.progressBarInner} ${barColor(data.coveragePct ?? 0)}`}
                  style={{ width: `${Math.min(data.coveragePct ?? 0, 100)}%` }}
                />
              </div>
            </div>
          )}

          {/* Data type rows */}
          <div className={styles.progressRows}>
            {coverageRows.map((row) => (
              <div key={row.label} className={styles.progressRow}>
                <span className={styles.progressLabel}>{row.label}</span>
                <div className={styles.progressBarOuter}>
                  <div
                    className={`${styles.progressBarInner} ${barColor(row.pct)}`}
                    style={{ width: `${Math.min(row.pct, 100)}%` }}
                  />
                </div>
                <span className={`${styles.progressPct} ${textColor(row.pct)}`}>
                  {row.pct}%
                </span>
                <span className={styles.progressCount}>
                  {row.count.toLocaleString()}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {!data && !loading && !error && (
        <div className={styles.empty}>Select a league and season, then click Audit.</div>
      )}
    </div>
  );
}
