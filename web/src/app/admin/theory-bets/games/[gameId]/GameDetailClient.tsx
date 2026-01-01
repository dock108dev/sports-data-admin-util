"use client";

import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { fetchGame, rescrapeGame, resyncOdds, type AdminGameDetail } from "@/lib/api/sportsAdmin";
import { SocialMediaRenderer } from "@/components/social/SocialMediaRenderer";
import styles from "./styles.module.css";

/** Collapsible section component */
function CollapsibleSection({ title, defaultOpen = true, children }: { 
  title: string; 
  defaultOpen?: boolean; 
  children: ReactNode;
}) {
  const [isOpen, setIsOpen] = useState(defaultOpen);
  return (
    <div className={styles.card}>
      <button
        type="button"
        className={styles.collapsibleHeader}
        onClick={() => setIsOpen(!isOpen)}
      >
        <h2>{title}</h2>
        <span className={styles.chevron}>{isOpen ? "▼" : "▶"}</span>
      </button>
      {isOpen && <div className={styles.collapsibleContent}>{children}</div>}
    </div>
  );
}

/** Play-by-Play section with quarter tabs */
type PlayEntry = {
  id: number;
  quarter: number | null;
  game_clock: string | null;
  play_index: number;
  play_type: string | null;
  team_abbreviation: string | null;
  player_id: string | null;
  player_name: string | null;
  description: string | null;
  home_score: number | null;
  away_score: number | null;
  raw_data: Record<string, unknown>;
};

function PbpSection({ plays }: { plays: PlayEntry[] }) {
  const [isOpen, setIsOpen] = useState(false);
  const [selectedQuarter, setSelectedQuarter] = useState<number | null>(null);

  // Get unique quarters
  const quarters = useMemo(() => {
    const qs = [...new Set(plays.map((p) => p.quarter).filter((q) => q !== null))] as number[];
    return qs.sort((a, b) => a - b);
  }, [plays]);

  // Initialize selected quarter
  useEffect(() => {
    if (quarters.length > 0 && selectedQuarter === null) {
      setSelectedQuarter(quarters[0]);
    }
  }, [quarters, selectedQuarter]);

  // Filter plays by selected quarter
  const filteredPlays = useMemo(() => {
    if (selectedQuarter === null) return plays;
    return plays.filter((p) => p.quarter === selectedQuarter);
  }, [plays, selectedQuarter]);

  const getQuarterLabel = (q: number) => {
    if (q <= 4) return `Q${q}`;
    return `OT${q - 4}`;
  };

  return (
    <div className={styles.card}>
      <button
        type="button"
        className={styles.collapsibleHeader}
        onClick={() => setIsOpen(!isOpen)}
      >
        <h2>Play-by-Play</h2>
        <span className={styles.chevron}>{isOpen ? "▼" : "▶"}</span>
      </button>
      {isOpen && (
        <div className={styles.collapsibleContent}>
          {plays.length === 0 ? (
            <div style={{ color: "#475569" }}>No play-by-play data found for this game.</div>
          ) : (
            <>
              <div className={styles.quarterTabs}>
                {quarters.map((q) => (
                  <button
                    key={q}
                    type="button"
                    className={`${styles.quarterTab} ${selectedQuarter === q ? styles.quarterTabActive : ""}`}
                    onClick={() => setSelectedQuarter(q)}
                  >
                    {getQuarterLabel(q)}
                    <span className={styles.quarterCount}>
                      {plays.filter((p) => p.quarter === q).length}
                    </span>
                  </button>
                ))}
              </div>
              <div className={styles.pbpContainer}>
                <table className={styles.table}>
                  <thead>
                    <tr>
                      <th>Time</th>
                      <th>Team</th>
                      <th>Description</th>
                      <th>Score</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredPlays.map((play) => (
                      <tr key={play.id}>
                        <td>{play.game_clock ?? "—"}</td>
                        <td>{play.team_abbreviation ?? "—"}</td>
                        <td className={styles.pbpDescription}>{play.description ?? "—"}</td>
                        <td>
                          {play.away_score !== null && play.home_score !== null
                            ? `${play.away_score}-${play.home_score}`
                            : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}

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

  const load = async () => {
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
  };

  useEffect(() => {
    if (isNumericId) {
      load();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isNumericId, gameIdParam]);

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

  // Book selection defaults to FanDuel if available, otherwise first book
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
        {Object.keys(playerStatsByTeam).length === 0 ? (
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

      <CollapsibleSection title="Social Posts" defaultOpen={false}>
        {/* #region agent log */}
        {game.social_posts && game.social_posts.length > 0 && (() => { fetch('http://127.0.0.1:7242/ingest/bbcc1fde-07f2-48ee-a458-9336304655ab',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({location:'GameDetailClient.tsx:socialPosts',message:'Raw social posts from API',data:{postCount:game.social_posts.length,samplePosts:game.social_posts.slice(0,3).map(p=>({id:p.id,media_type:p.media_type,has_video_url:!!p.video_url,has_image_url:!!p.image_url}))},timestamp:Date.now(),sessionId:'debug-session',hypothesisId:'H5'})}).catch(()=>{}); return null; })()}
        {/* #endregion */}
        {!game.social_posts || game.social_posts.length === 0 ? (
          <div style={{ color: "#475569" }}>No social posts found for this game.</div>
        ) : (
          <div className={styles.socialPostsGrid}>
            {([...game.social_posts]
              .sort(
                (a, b) =>
                  new Date(a.posted_at).getTime() - new Date(b.posted_at).getTime()
              )).map((post) => (
              <div key={post.id} className={styles.socialPostCard}>
                <div className={styles.socialPostHeader}>
                  <span className={styles.badge}>{post.team_abbreviation}</span>
                  {post.source_handle && (
                    <span className={styles.handleBadge}>@{post.source_handle}</span>
                  )}
                  {post.media_type === "video" && (
                    <span className={styles.videoBadge}>🎥 Video</span>
                  )}
                  {post.media_type === "image" && (
                    <span className={styles.imageBadge}>🖼️ Image</span>
                  )}
                </div>
                {post.tweet_text && (
                  <div className={styles.tweetText}>{post.tweet_text}</div>
                )}
                {/* Only render media component if there's actual media */}
                {(post.image_url || post.video_url || post.media_type === "video" || post.media_type === "image") ? (
                  <SocialMediaRenderer
                    mediaType={post.media_type}
                    imageUrl={post.image_url}
                    videoUrl={post.video_url}
                    postUrl={post.post_url}
                    linkClassName={styles.socialPostLink}
                  />
                ) : (
                  <a
                    href={post.post_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className={styles.socialPostLink}
                  >
                    View on X →
                  </a>
                )}
                <div className={styles.socialPostMeta}>
                  {new Date(post.posted_at).toLocaleString()}
                </div>
              </div>
            ))}
          </div>
        )}
      </CollapsibleSection>

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
