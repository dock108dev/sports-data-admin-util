"use client";

import { useState, useEffect } from "react";
import { useParams } from "next/navigation";
import { AdminCard, AdminTable } from "@/components/admin";
import { fetchPlayer, fetchPlayerStats } from "@/lib/api/golf";
import type { GolfPlayer, GolfPlayerStats } from "@/lib/api/golfTypes";
import styles from "../../golf.module.css";

export default function PlayerDetailPage() {
  const params = useParams<{ dgId: string }>();
  const dgId = Number(params.dgId);

  const [player, setPlayer] = useState<GolfPlayer | null>(null);
  const [stats, setStats] = useState<GolfPlayerStats[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const [playerRes, statsRes] = await Promise.all([
          fetchPlayer(dgId),
          fetchPlayerStats(dgId),
        ]);
        if (!cancelled) {
          setPlayer(playerRes);
          setStats(statsRes);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : String(err));
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    load();

    return () => {
      cancelled = true;
    };
  }, [dgId]);

  if (loading) return <div className={styles.loading}>Loading player...</div>;
  if (error) return <div className={styles.error}>{error}</div>;
  if (!player) return <div className={styles.empty}>Player not found.</div>;

  return (
    <div className={styles.container}>
      <header className={styles.pageHeader}>
        <h1 className={styles.pageTitle}>{player.player_name}</h1>
        <p className={styles.pageSubtitle}>DG ID: {player.dg_id}</p>
      </header>

      <AdminCard title="Player Info">
        <div className={styles.infoCard}>
          <div className={styles.infoItem}>
            <span className={styles.infoLabel}>Country</span>
            <span className={styles.infoValue}>{player.country ?? "-"}</span>
          </div>
          <div className={styles.infoItem}>
            <span className={styles.infoLabel}>Amateur</span>
            <span className={styles.infoValue}>{player.amateur ? "Yes" : "No"}</span>
          </div>
        </div>
      </AdminCard>

      <AdminCard title="Strokes Gained by Period">
        {stats.length === 0 ? (
          <div className={styles.empty}>No stats available.</div>
        ) : (
          <AdminTable
            headers={["Period", "SG Total", "SG OTT", "SG APP", "SG ARG", "SG Putt", "DG Rank", "OWGR"]}
          >
            {stats.map((s) => (
              <tr key={s.period}>
                <td>{s.period}</td>
                <td>{s.sg_total != null ? s.sg_total.toFixed(2) : "-"}</td>
                <td>{s.sg_ott != null ? s.sg_ott.toFixed(2) : "-"}</td>
                <td>{s.sg_app != null ? s.sg_app.toFixed(2) : "-"}</td>
                <td>{s.sg_arg != null ? s.sg_arg.toFixed(2) : "-"}</td>
                <td>{s.sg_putt != null ? s.sg_putt.toFixed(2) : "-"}</td>
                <td>{s.dg_rank ?? "-"}</td>
                <td>{s.owgr ?? "-"}</td>
              </tr>
            ))}
          </AdminTable>
        )}
      </AdminCard>
    </div>
  );
}
