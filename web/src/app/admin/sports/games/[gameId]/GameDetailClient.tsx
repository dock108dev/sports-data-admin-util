"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { fetchGame, rescrapeGame, resyncOdds, type AdminGameDetail } from "@/lib/api/sportsAdmin";
import { ROUTES } from "@/lib/constants/routes";
import { CollapsibleSection } from "./CollapsibleSection";
import { PbpSection } from "./PbpSection";
import { SocialPostsSection } from "./SocialPostsSection";
import { FlowSection } from "./FlowSection";
import { OddsSection } from "./OddsSection";
import { PlayerStatsSection } from "./PlayerStatsSection";
import { ComputedFieldsSection } from "./ComputedFieldsSection";
import { flattenStats, FieldLabel } from "./gameDetailUtils";
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
      { label: "Boxscore", ok: game.game.hasBoxscore },
      { label: "Player stats", ok: game.game.hasPlayerStats },
      { label: "Odds", ok: game.game.hasOdds },
      { label: `Social (${game.game.socialPostCount || 0})`, ok: game.game.hasSocial },
      { label: `PBP (${game.game.playCount || 0})`, ok: game.game.hasPbp },
      { label: "Flow", ok: game.game.hasFlow },
    ];
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
  const gameDate = new Date(g.gameDate).toLocaleString();

  return (
    <div className={styles.container}>
      <Link href={ROUTES.SPORTS_BROWSER} className={styles.backLink}>
        ← Back to Data Browser
      </Link>

      <div className={styles.card}>
        <h1>
          Game {g.id} — {g.leagueCode}
        </h1>
        <div className={styles.meta}>
          <FieldLabel label={gameDate} field="gameDate" /> · {g.seasonType ?? "season"} · Last scraped: {g.lastScrapedAt ?? "—"}
        </div>
        <div className={styles.scoreLine}>
          <div>
            <strong><FieldLabel label={g.awayTeam} field="awayTeam" /></strong>
            <span>Away</span>
            <span><FieldLabel label={String(g.awayScore ?? "—")} field="awayScore" /></span>
          </div>
          <div>
            <strong><FieldLabel label={g.homeTeam} field="homeTeam" /></strong>
            <span>Home</span>
            <span><FieldLabel label={String(g.homeScore ?? "—")} field="homeScore" /></span>
          </div>
        </div>
        <div style={{ marginTop: "1rem", display: "flex", gap: "0.75rem", flexWrap: "wrap" }}>
          {flags.map((f) => (
            <span
              key={f.label}
              title={`API field: ${f.label.toLowerCase().includes("boxscore") ? "hasBoxscore" : f.label.toLowerCase().includes("player") ? "hasPlayerStats" : f.label.toLowerCase().includes("odds") ? "hasOdds" : f.label.toLowerCase().includes("social") ? "hasSocial" : f.label.toLowerCase().includes("pbp") ? "hasPbp" : f.label.toLowerCase().includes("flow") ? "hasFlow" : f.label}`}
              style={{
                padding: "0.35rem 0.75rem",
                borderRadius: "999px",
                background: f.ok ? "#ecfdf3" : "#fef2f2",
                color: f.ok ? "#166534" : "#b91c1c",
                fontWeight: 700,
                fontSize: "0.85rem",
                cursor: "help",
                borderBottom: "1px dotted #94a3b8",
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
        {game.teamStats.length === 0 ? (
          <div style={{ color: "#475569" }}>No team stats found.</div>
        ) : (
          <div className={styles.teamStatsGrid}>
            {game.teamStats.map((t) => {
              const flattened = flattenStats(t.stats || {});
              return (
                <div key={t.team} className={styles.teamStatsCard}>
                  <div className={styles.teamStatsHeader}>
                    <h3>{t.team}</h3>
                    <span className={styles.badge}>{t.isHome ? "Home" : "Away"}</span>
                  </div>
                  <table className={styles.table}>
                    <tbody>
                      {flattened.map(({ key, label, value }) => (
                        <tr key={key}>
                          <td>{label}</td>
                          <td>{value}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              );
            })}
          </div>
        )}
      </CollapsibleSection>

      <PlayerStatsSection
        playerStats={game.playerStats}
        nhlSkaters={game.nhlSkaters}
        nhlGoalies={game.nhlGoalies}
        isNHL={g.leagueCode === "NHL"}
      />

      <OddsSection odds={game.odds} />

      <SocialPostsSection posts={game.socialPosts || []} />

      <PbpSection plays={game.plays || []} groupedPlays={game.groupedPlays} leagueCode={g.leagueCode} />

      <FlowSection gameId={g.id} hasFlow={g.hasFlow} leagueCode={g.leagueCode} />

      <ComputedFieldsSection derivedMetrics={game.derivedMetrics || {}} />
    </div>
  );
}
