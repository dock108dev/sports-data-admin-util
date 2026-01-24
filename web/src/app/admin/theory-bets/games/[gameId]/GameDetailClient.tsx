"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { fetchGame, rescrapeGame, resyncOdds, type AdminGameDetail } from "@/lib/api/sportsAdmin";
import { CollapsibleSection } from "./CollapsibleSection";
import { PbpSection } from "./PbpSection";
import { SocialPostsSection } from "./SocialPostsSection";
import styles from "./styles.module.css";

export default function GameDetailClient() {
  const params = useParams<{ gameId?: string }>();
  const gameIdParam = params?.gameId ?? "";
  const isNumericId = /^\d+$/.test(gameIdParam);
  const [game, setGame] = useState<AdminGameDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionStatus, setActionStatus] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState<"rescrape" | "odds" | null>(null);
  const [selectedBook, setSelectedBook] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchGame(gameIdParam);
      setGame(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load game");
    } finally {
      setLoading(false);
    }
  }, [gameIdParam]);

  useEffect(() => {
    if (isNumericId) {
      load();
    }
  }, [isNumericId, load]);

  const flags = useMemo(() => {
    if (!game) return [];
    return [
      { label: "Boxscore", ok: game.game.has_boxscore },
      { label: "Player stats", ok: game.game.has_player_stats },
      { label: "Odds", ok: game.game.has_odds },
      { label: `Social (${game.game.social_post_count || 0})`, ok: game.game.has_social },
      { label: `PBP (${game.game.play_count || 0})`, ok: game.game.has_pbp },
    ];
  }, [game]);

  const bookOptions = useMemo(() => {
    if (!game) return [];
    return Array.from(new Set(game.odds.map((o) => o.book)));
  }, [game]);

  useEffect(() => {
    if (!game) return;
    const preferred = bookOptions.find((b) => b === "FanDuel") ?? bookOptions[0] ?? null;
    setSelectedBook(preferred ?? null);
  }, [bookOptions, game]);

  const filteredOdds = useMemo(() => {
    if (!game || !selectedBook) return [];
    return game.odds.filter((o) => o.book === selectedBook);
  }, [game, selectedBook]);

  const oddsByMarket = useMemo(() => {
    const spread = filteredOdds.filter((o) => o.market_type === "spread");
    const total = filteredOdds.filter((o) => o.market_type === "total");
    const moneyline = filteredOdds.filter((o) => o.market_type === "moneyline");
    return { spread, total, moneyline };
  }, [filteredOdds]);

  const playerStatsByTeam = useMemo(() => {
    if (!game) return {};
    return game.player_stats.reduce<Record<string, typeof game.player_stats>>((acc, p) => {
      acc[p.team] = acc[p.team] || [];
      acc[p.team].push(p);
      return acc;
    }, {});
  }, [game]);

  // NHL-specific: Group skaters by team
  const nhlSkatersByTeam = useMemo(() => {
    if (!game || !game.nhl_skaters) return {};
    return game.nhl_skaters.reduce<Record<string, NonNullable<typeof game.nhl_skaters>>>((acc, p) => {
      acc[p.team] = acc[p.team] || [];
      acc[p.team].push(p);
      return acc;
    }, {});
  }, [game]);

  // NHL-specific: Group goalies by team
  const nhlGoaliesByTeam = useMemo(() => {
    if (!game || !game.nhl_goalies) return {};
    return game.nhl_goalies.reduce<Record<string, NonNullable<typeof game.nhl_goalies>>>((acc, p) => {
      acc[p.team] = acc[p.team] || [];
      acc[p.team].push(p);
      return acc;
    }, {});
  }, [game]);

  // Determine if this is an NHL game
  const isNHL = game?.game.league_code === "NHL";

  const handleRescrape = async () => {
    setActionStatus(null);
    setActionLoading("rescrape");
    try {
      const res = await rescrapeGame(Number.parseInt(gameIdParam, 10));
      setActionStatus(res.message || "Rescrape requested");
    } catch (err) {
      setActionStatus(err instanceof Error ? err.message : "Rescrape failed");
    } finally {
      setActionLoading(null);
    }
  };

  const handleResyncOdds = async () => {
    setActionStatus(null);
    setActionLoading("odds");
    try {
      const res = await resyncOdds(Number.parseInt(gameIdParam, 10));
      setActionStatus(res.message || "Odds resync requested");
    } catch (err) {
      setActionStatus(err instanceof Error ? err.message : "Odds resync failed");
    } finally {
      setActionLoading(null);
    }
  };

  if (!isNumericId) return <div className={styles.container}>Invalid game id.</div>;
  if (loading) return <div className={styles.container}>Loading game...</div>;
  if (error) return <div className={styles.container}>Error: {error}</div>;
  if (!game) return <div className={styles.container}>Game not found.</div>;

  const g = game.game;
  const gameDate = new Date(g.game_date).toLocaleString();

  return (
    <div className={styles.container}>
      <Link href="/admin/theory-bets/browser" className={styles.backLink}>
        ← Back to Data Browser
      </Link>

      <div className={styles.card}>
        <h1>
          Game {g.id} — {g.league_code}
        </h1>
        <div className={styles.meta}>
          {gameDate} · {g.season_type ?? "season"} · Last scraped: {g.last_scraped_at ?? "—"}
        </div>
        <div className={styles.scoreLine}>
          <div>
            <strong>{g.away_team}</strong>
            <span>Away</span>
            <span>{g.away_score ?? "—"}</span>
          </div>
          <div>
            <strong>{g.home_team}</strong>
            <span>Home</span>
            <span>{g.home_score ?? "—"}</span>
          </div>
        </div>
        <div style={{ marginTop: "1rem", display: "flex", gap: "0.75rem", flexWrap: "wrap" }}>
          {flags.map((f) => (
            <span
              key={f.label}
              style={{
                padding: "0.35rem 0.75rem",
                borderRadius: "999px",
                background: f.ok ? "#ecfdf3" : "#fef2f2",
                color: f.ok ? "#166534" : "#b91c1c",
                fontWeight: 700,
                fontSize: "0.85rem",
              }}
            >
              {f.label}: {f.ok ? "Yes" : "No"}
            </span>
          ))}
        </div>
        <div style={{ marginTop: "1rem", display: "flex", gap: "0.75rem", flexWrap: "wrap" }}>
          <button
            type="button"
            onClick={handleRescrape}
            disabled={!!actionLoading}
            style={{ padding: "0.55rem 0.9rem", borderRadius: 8, border: "1px solid #cbd5e1" }}
          >
            {actionLoading === "rescrape" ? "Requesting..." : "Rescrape game"}
          </button>
          <button
            type="button"
            onClick={handleResyncOdds}
            disabled={!!actionLoading}
            style={{ padding: "0.55rem 0.9rem", borderRadius: 8, border: "1px solid #cbd5e1" }}
          >
            {actionLoading === "odds" ? "Requesting..." : "Resync odds"}
          </button>
          <button
            type="button"
            onClick={load}
            disabled={!!actionLoading}
            style={{ padding: "0.55rem 0.9rem", borderRadius: 8, border: "1px solid #cbd5e1" }}
          >
            Refresh
          </button>
        </div>
        {actionStatus && <div style={{ marginTop: "0.5rem", color: "#0f172a" }}>{actionStatus}</div>}
      </div>

      <CollapsibleSection title="Team Stats" defaultOpen={false}>
        {game.team_stats.length === 0 ? (
          <div style={{ color: "#475569" }}>No team stats found.</div>
        ) : (
          <div className={styles.teamStatsGrid}>
            {game.team_stats.map((t) => (
              <div key={t.team} className={styles.teamStatsCard}>
                <div className={styles.teamStatsHeader}>
                  <h3>{t.team}</h3>
                  <span className={styles.badge}>{t.is_home ? "Home" : "Away"}</span>
                </div>
                <table className={styles.table}>
                  <tbody>
                    {Object.entries(t.stats || {}).map(([k, v]) => (
                      <tr key={k}>
                        <td>{k}</td>
                        <td>{String(v ?? "—")}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ))}
          </div>
        )}
      </CollapsibleSection>

      <CollapsibleSection title="Player Stats" defaultOpen={false}>
        {isNHL ? (
          // NHL-specific player stats display - one card per team with skaters + goalies
          Object.keys(nhlSkatersByTeam).length === 0 && Object.keys(nhlGoaliesByTeam).length === 0 ? (
            <div style={{ color: "#475569" }}>No player stats found.</div>
          ) : (
            <div className={styles.playerStatsGrid}>
              {/* Get unique teams from both skaters and goalies */}
              {Array.from(new Set([...Object.keys(nhlSkatersByTeam), ...Object.keys(nhlGoaliesByTeam)])).map((team) => (
                <div key={team} className={styles.teamStatsCard}>
                  <div className={styles.teamStatsHeader}>
                    <h3>{team}</h3>
                  </div>

                  {/* Skaters section */}
                  {nhlSkatersByTeam[team] && nhlSkatersByTeam[team].length > 0 && (
                    <>
                      <h4 style={{ margin: "0.75rem 0 0.25rem", fontSize: "0.9rem", color: "#475569" }}>Skaters</h4>
                      <div style={{ overflowX: "auto" }}>
                        <table className={styles.table} style={{ fontSize: "0.85rem" }}>
                          <thead>
                            <tr>
                              <th>Player</th>
                              <th>TOI</th>
                              <th>G</th>
                              <th>A</th>
                              <th>Pts</th>
                              <th>+/-</th>
                              <th>SOG</th>
                              <th>Hits</th>
                              <th>BLK</th>
                              <th>PIM</th>
                            </tr>
                          </thead>
                          <tbody>
                            {nhlSkatersByTeam[team].map((p) => (
                              <tr key={`${team}-skater-${p.player_name}`}>
                                <td>{p.player_name}</td>
                                <td>{p.toi ?? "—"}</td>
                                <td>{p.goals ?? "—"}</td>
                                <td>{p.assists ?? "—"}</td>
                                <td>{p.points ?? "—"}</td>
                                <td>{p.plus_minus ?? "—"}</td>
                                <td>{p.shots_on_goal ?? "—"}</td>
                                <td>{p.hits ?? "—"}</td>
                                <td>{p.blocked_shots ?? "—"}</td>
                                <td>{p.penalty_minutes ?? "—"}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </>
                  )}

                  {/* Goalies section */}
                  {nhlGoaliesByTeam[team] && nhlGoaliesByTeam[team].length > 0 && (
                    <>
                      <h4 style={{ margin: "0.75rem 0 0.25rem", fontSize: "0.9rem", color: "#475569" }}>Goalies</h4>
                      <table className={styles.table} style={{ fontSize: "0.85rem" }}>
                        <thead>
                          <tr>
                            <th>Player</th>
                            <th>TOI</th>
                            <th>SA</th>
                            <th>SV</th>
                            <th>GA</th>
                            <th>SV%</th>
                          </tr>
                        </thead>
                        <tbody>
                          {nhlGoaliesByTeam[team].map((p) => (
                            <tr key={`${team}-goalie-${p.player_name}`}>
                              <td>{p.player_name}</td>
                              <td>{p.toi ?? "—"}</td>
                              <td>{p.shots_against ?? "—"}</td>
                              <td>{p.saves ?? "—"}</td>
                              <td>{p.goals_against ?? "—"}</td>
                              <td>{p.save_percentage != null ? `${(p.save_percentage * 100).toFixed(1)}%` : "—"}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </>
                  )}
                </div>
              ))}
            </div>
          )
        ) : (
          // Generic player stats (NBA, NCAAB, etc.)
          Object.keys(playerStatsByTeam).length === 0 ? (
            <div style={{ color: "#475569" }}>No player stats found.</div>
          ) : (
            <div className={styles.playerStatsGrid}>
              {Object.entries(playerStatsByTeam).map(([team, rows]) => (
                <div key={team} className={styles.teamStatsCard}>
                  <div className={styles.teamStatsHeader}>
                    <h3>{team}</h3>
                  </div>
                  <table className={styles.table}>
                    <thead>
                      <tr>
                        <th>Player</th>
                        <th>Minutes</th>
                        <th>Points</th>
                        <th>Reb</th>
                        <th>Ast</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map((p) => (
                        <tr key={`${team}-${p.player_name}`}>
                          <td>{p.player_name}</td>
                          <td>{p.minutes ?? "—"}</td>
                          <td>{p.points ?? "—"}</td>
                          <td>{p.rebounds ?? "—"}</td>
                          <td>{p.assists ?? "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ))}
            </div>
          )
        )}
      </CollapsibleSection>

      <CollapsibleSection title="Odds" defaultOpen={false}>
        {game.odds.length === 0 ? (
          <div style={{ color: "#475569" }}>No odds found.</div>
        ) : (
          <>
            <div className={styles.oddsHeader}>
              <label>
                Book:
                <select
                  className={styles.oddsBookSelect}
                  value={selectedBook ?? ""}
                  onChange={(e) => setSelectedBook(e.target.value)}
                >
                  {bookOptions.map((b) => (
                    <option key={b} value={b}>
                      {b}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            <div className={styles.oddsGroup}>
              <h3>Spread</h3>
              {oddsByMarket.spread.length === 0 ? (
                <div className={styles.subtle}>No spread odds for {selectedBook}</div>
              ) : (
                <table className={styles.table}>
                  <thead>
                    <tr>
                      <th>Side</th>
                      <th>Line</th>
                      <th>Price</th>
                      <th>Observed</th>
                    </tr>
                  </thead>
                  <tbody>
                    {oddsByMarket.spread.map((o, idx) => (
                      <tr key={`${o.side}-${idx}`}>
                        <td>{o.side ?? "—"}</td>
                        <td>{o.line ?? "—"}</td>
                        <td>{o.price ?? "—"}</td>
                        <td>{o.observed_at ?? "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>

            <div className={styles.oddsGroup}>
              <h3>Total</h3>
              {oddsByMarket.total.length === 0 ? (
                <div className={styles.subtle}>No total odds for {selectedBook}</div>
              ) : (
                <table className={styles.table}>
                  <thead>
                    <tr>
                      <th>Side</th>
                      <th>Line</th>
                      <th>Price</th>
                      <th>Observed</th>
                    </tr>
                  </thead>
                  <tbody>
                    {oddsByMarket.total.map((o, idx) => (
                      <tr key={`${o.side}-${idx}`}>
                        <td>{o.side ?? "—"}</td>
                        <td>{o.line ?? "—"}</td>
                        <td>{o.price ?? "—"}</td>
                        <td>{o.observed_at ?? "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>

            <div className={styles.oddsGroup}>
              <h3>Moneyline</h3>
              {oddsByMarket.moneyline.length === 0 ? (
                <div className={styles.subtle}>No moneyline odds for {selectedBook}</div>
              ) : (
                <table className={styles.table}>
                  <thead>
                    <tr>
                      <th>Side</th>
                      <th>Price</th>
                      <th>Observed</th>
                    </tr>
                  </thead>
                  <tbody>
                    {oddsByMarket.moneyline.map((o, idx) => (
                      <tr key={`${o.side}-${idx}`}>
                        <td>{o.side ?? "—"}</td>
                        <td>{o.price ?? "—"}</td>
                        <td>{o.observed_at ?? "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </>
        )}
      </CollapsibleSection>

      <SocialPostsSection posts={game.social_posts || []} />

      <PbpSection plays={game.plays || []} />

      <CollapsibleSection title="Derived Metrics" defaultOpen={false}>
        {Object.keys(game.derived_metrics || {}).length === 0 ? (
          <div style={{ color: "#475569" }}>No derived metrics.</div>
        ) : (
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Metric</th>
                <th>Value</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(game.derived_metrics).map(([k, v]) => (
                <tr key={k}>
                  <td>{k}</td>
                  <td>{String(v)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </CollapsibleSection>
    </div>
  );
}
