"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import { AdminCard, AdminTable } from "@/components/admin";
import { listTournaments } from "@/lib/api/golf";
import type { GolfTournament } from "@/lib/api/golfTypes";
import styles from "../golf.module.css";

const TOUR_OPTIONS = [
  { value: "pga", label: "PGA Tour" },
  { value: "euro", label: "European Tour" },
  { value: "kft", label: "Korn Ferry" },
  { value: "alt", label: "LIV Golf" },
  { value: "opp", label: "Opposite Field" },
];
const STATUS_OPTIONS = ["all", "scheduled", "in_progress", "completed"];

export default function TournamentsPage() {
  const router = useRouter();
  const [tournaments, setTournaments] = useState<GolfTournament[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tour, setTour] = useState("");
  const [status, setStatus] = useState("all");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await listTournaments({
        tour: tour || undefined,
        status: status === "all" ? undefined : status,
      });
      setTournaments(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [tour, status]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className={styles.container}>
      <header className={styles.pageHeader}>
        <h1 className={styles.pageTitle}>Tournaments</h1>
        <p className={styles.pageSubtitle}>
          Browse golf tournaments across tours
        </p>
      </header>

      <div className={styles.filterBar}>
        <div className={styles.formGroup}>
          <label>Tour</label>
          <select value={tour} onChange={(e) => setTour(e.target.value)}>
            <option value="">All Tours</option>
            {TOUR_OPTIONS.map((t) => (
              <option key={t.value} value={t.value}>{t.label}</option>
            ))}
          </select>
        </div>
        <div className={styles.formGroup}>
          <label>Status</label>
          <select value={status} onChange={(e) => setStatus(e.target.value)}>
            {STATUS_OPTIONS.map((s) => (
              <option key={s} value={s}>{s === "all" ? "All" : s.replace("_", " ")}</option>
            ))}
          </select>
        </div>
      </div>

      {error && <div className={styles.error}>{error}</div>}
      {loading && <div className={styles.loading}>Loading tournaments...</div>}

      {!loading && !error && tournaments.length === 0 && (
        <div className={styles.empty}>No tournaments found.</div>
      )}

      {!loading && tournaments.length > 0 && (
        <AdminCard>
          <AdminTable
            headers={["Event Name", "Course", "Dates", "Tour", "Status", "Purse"]}
          >
            {tournaments.map((t) => (
              <tr
                key={t.event_id}
                className={styles.clickableRow}
                onClick={() => router.push(`/admin/golf/tournaments/${t.event_id}`)}
              >
                <td>{t.event_name}</td>
                <td>{t.course ?? "-"}</td>
                <td style={{ fontSize: "0.85rem" }}>
                  {t.start_date}{t.end_date ? ` \u2013 ${t.end_date}` : ""}
                </td>
                <td>{t.tour}</td>
                <td>{t.status}</td>
                <td>{t.purse != null ? `$${t.purse.toLocaleString()}` : "-"}</td>
              </tr>
            ))}
          </AdminTable>
        </AdminCard>
      )}
    </div>
  );
}
