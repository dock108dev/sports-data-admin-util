"use client";

import { useState, useEffect, useCallback } from "react";
import { useParams } from "next/navigation";
import { AdminCard, AdminTable } from "@/components/admin";
import {
  fetchTournament,
  fetchTournamentLeaderboard,
  fetchTournamentField,
  fetchTournamentRounds,
  fetchOutrightOdds,
} from "@/lib/api/golf";
import type {
  GolfTournament,
  GolfLeaderboardEntry,
  GolfFieldEntry,
  GolfRound,
  GolfOddsEntry,
} from "@/lib/api/golfTypes";
import styles from "../../golf.module.css";

type Tab = "leaderboard" | "field" | "rounds" | "odds";

const MARKET_OPTIONS = ["win", "top_5", "top_10", "make_cut"];

export default function TournamentDetailPage() {
  const params = useParams<{ eventId: string }>();
  const eventId = params.eventId;

  const [tab, setTab] = useState<Tab>("leaderboard");
  const [tournament, setTournament] = useState<GolfTournament | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Tab data
  const [leaderboard, setLeaderboard] = useState<GolfLeaderboardEntry[]>([]);
  const [field, setField] = useState<GolfFieldEntry[]>([]);
  const [rounds, setRounds] = useState<GolfRound[]>([]);
  const [odds, setOdds] = useState<GolfOddsEntry[]>([]);

  // Filters
  const [selectedRound, setSelectedRound] = useState(1);
  const [market, setMarket] = useState("win");

  // Load tournament info
  useEffect(() => {
    setLoading(true);
    fetchTournament(eventId)
      .then((res) => setTournament(res))
      .catch((err) => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => setLoading(false));
  }, [eventId]);

  // Load tab data
  const loadTabData = useCallback(async () => {
    try {
      if (tab === "leaderboard") {
        const res = await fetchTournamentLeaderboard(eventId);
        setLeaderboard(res);
      } else if (tab === "field") {
        const res = await fetchTournamentField(eventId);
        setField(res);
      } else if (tab === "rounds") {
        const res = await fetchTournamentRounds(eventId, selectedRound);
        setRounds(res);
      } else if (tab === "odds") {
        const res = await fetchOutrightOdds({ tournament_id: tournament?.id, market });
        setOdds(res);
      }
    } catch {
      // Tab data load failure is non-fatal — empty state is shown
    }
  }, [eventId, tab, selectedRound, market, tournament?.id]);

  useEffect(() => {
    loadTabData();
  }, [loadTabData]);

  if (loading) return <div className={styles.loading}>Loading tournament...</div>;
  if (error) return <div className={styles.error}>{error}</div>;

  return (
    <div className={styles.container}>
      <header className={styles.pageHeader}>
        <h1 className={styles.pageTitle}>{tournament?.event_name ?? "Tournament"}</h1>
        <p className={styles.pageSubtitle}>
          {tournament?.course ?? ""} &middot; {tournament?.tour} &middot; {tournament?.status}
        </p>
      </header>

      {/* Tabs */}
      <div className={styles.tabs}>
        {(["leaderboard", "field", "rounds", "odds"] as Tab[]).map((t) => (
          <button
            key={t}
            className={`${styles.tab} ${tab === t ? styles.tabActive : ""}`}
            onClick={() => setTab(t)}
          >
            {t.charAt(0).toUpperCase() + t.slice(1)}
          </button>
        ))}
      </div>

      {/* Leaderboard */}
      {tab === "leaderboard" && (
        <AdminCard>
          {leaderboard.length === 0 ? (
            <div className={styles.empty}>No leaderboard data available.</div>
          ) : (
            <AdminTable
              headers={["Pos", "Player", "Total", "Today", "Thru", "R1", "R2", "R3", "R4", "SG Total", "Win Prob"]}
            >
              {leaderboard.map((e) => (
                <tr key={e.dg_id}>
                  <td>{e.position ?? "-"}</td>
                  <td>{e.player_name ?? "-"}</td>
                  <td>{e.total_score ?? "-"}</td>
                  <td>{e.today_score ?? "-"}</td>
                  <td>{e.thru ?? "-"}</td>
                  <td>{e.r1 ?? "-"}</td>
                  <td>{e.r2 ?? "-"}</td>
                  <td>{e.r3 ?? "-"}</td>
                  <td>{e.r4 ?? "-"}</td>
                  <td>{e.sg_total != null ? e.sg_total.toFixed(2) : "-"}</td>
                  <td>{e.win_prob != null ? `${(e.win_prob * 100).toFixed(1)}%` : "-"}</td>
                </tr>
              ))}
            </AdminTable>
          )}
        </AdminCard>
      )}

      {/* Field */}
      {tab === "field" && (
        <AdminCard>
          {field.length === 0 ? (
            <div className={styles.empty}>No field data available.</div>
          ) : (
            <AdminTable headers={["Player", "Status", "Tee Time R1", "Tee Time R2", "DK Salary", "FD Salary"]}>
              {field.map((e) => (
                <tr key={e.dg_id}>
                  <td>{e.player_name ?? "-"}</td>
                  <td>{e.status}</td>
                  <td>{e.tee_time_r1 ?? "-"}</td>
                  <td>{e.tee_time_r2 ?? "-"}</td>
                  <td>{e.dk_salary != null ? `$${e.dk_salary.toLocaleString()}` : "-"}</td>
                  <td>{e.fd_salary != null ? `$${e.fd_salary.toLocaleString()}` : "-"}</td>
                </tr>
              ))}
            </AdminTable>
          )}
        </AdminCard>
      )}

      {/* Rounds */}
      {tab === "rounds" && (
        <AdminCard>
          <div className={styles.filterBar}>
            <div className={styles.formGroup}>
              <label>Round</label>
              <select
                value={selectedRound}
                onChange={(e) => setSelectedRound(Number(e.target.value))}
              >
                {[1, 2, 3, 4].map((r) => (
                  <option key={r} value={r}>Round {r}</option>
                ))}
              </select>
            </div>
          </div>
          {rounds.length === 0 ? (
            <div className={styles.empty}>No round data available.</div>
          ) : (
            <AdminTable
              headers={["DG ID", "Score", "Strokes", "SG OTT", "SG APP", "SG ARG", "SG Putt", "SG Total"]}
            >
              {rounds.map((e) => (
                <tr key={e.dg_id}>
                  <td>{e.dg_id}</td>
                  <td>{e.score ?? "-"}</td>
                  <td>{e.strokes ?? "-"}</td>
                  <td>{e.sg_ott != null ? e.sg_ott.toFixed(2) : "-"}</td>
                  <td>{e.sg_app != null ? e.sg_app.toFixed(2) : "-"}</td>
                  <td>{e.sg_arg != null ? e.sg_arg.toFixed(2) : "-"}</td>
                  <td>{e.sg_putt != null ? e.sg_putt.toFixed(2) : "-"}</td>
                  <td>{e.sg_total != null ? e.sg_total.toFixed(2) : "-"}</td>
                </tr>
              ))}
            </AdminTable>
          )}
        </AdminCard>
      )}

      {/* Odds */}
      {tab === "odds" && (
        <AdminCard>
          <div className={styles.filterBar}>
            <div className={styles.formGroup}>
              <label>Market</label>
              <select value={market} onChange={(e) => setMarket(e.target.value)}>
                {MARKET_OPTIONS.map((m) => (
                  <option key={m} value={m}>{m.replace("_", " ")}</option>
                ))}
              </select>
            </div>
          </div>
          {odds.length === 0 ? (
            <div className={styles.empty}>No odds data available.</div>
          ) : (
            <AdminTable headers={["Player", "Book", "Market", "Odds", "DG Prob"]}>
              {odds.map((e, i) => (
                <tr key={`${e.dg_id}-${e.book}-${i}`}>
                  <td>{e.player_name ?? "-"}</td>
                  <td>{e.book}</td>
                  <td>{e.market}</td>
                  <td>{e.odds}</td>
                  <td>{e.dg_prob != null ? `${(e.dg_prob * 100).toFixed(1)}%` : "-"}</td>
                </tr>
              ))}
            </AdminTable>
          )}
        </AdminCard>
      )}
    </div>
  );
}
