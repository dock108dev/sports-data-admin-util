"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import { AdminCard, AdminTable } from "@/components/admin";
import { listPools } from "@/lib/api/golfPools";
import type { GolfPool } from "@/lib/api/golfPoolTypes";
import styles from "../golf.module.css";

const CLUB_OPTIONS = ["RVCC", "Crestmont"];
const STATUS_OPTIONS = ["all", "draft", "open", "live", "closed", "completed"];

export default function PoolsPage() {
  const router = useRouter();
  const [pools, setPools] = useState<GolfPool[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [clubCode, setClubCode] = useState("");
  const [status, setStatus] = useState("all");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await listPools({
        club_code: clubCode || undefined,
        status: status === "all" ? undefined : status,
      });
      setPools(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [clubCode, status]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className={styles.container}>
      <header className={styles.pageHeader}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div>
            <h1 className={styles.pageTitle}>Golf Pools</h1>
            <p className={styles.pageSubtitle}>
              Manage country club golf pools
            </p>
          </div>
          <button
            className={styles.primaryButton}
            onClick={() => router.push("/admin/golf/pools/create")}
          >
            Create Pool
          </button>
        </div>
      </header>

      <div className={styles.filterBar}>
        <div className={styles.formGroup}>
          <label>Club</label>
          <select value={clubCode} onChange={(e) => setClubCode(e.target.value)}>
            <option value="">All Clubs</option>
            {CLUB_OPTIONS.map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
        </div>
        <div className={styles.formGroup}>
          <label>Status</label>
          <select value={status} onChange={(e) => setStatus(e.target.value)}>
            {STATUS_OPTIONS.map((s) => (
              <option key={s} value={s}>{s === "all" ? "All" : s.charAt(0).toUpperCase() + s.slice(1)}</option>
            ))}
          </select>
        </div>
      </div>

      {error && <div className={styles.error}>{error}</div>}
      {loading && <div className={styles.loading}>Loading pools...</div>}

      {!loading && !error && pools.length === 0 && (
        <div className={styles.empty}>No pools found.</div>
      )}

      {!loading && pools.length > 0 && (
        <AdminCard>
          <AdminTable
            headers={["Name", "Club", "Tournament", "Status", "Entries", "Deadline", "Last Scored"]}
          >
            {pools.map((p) => (
              <tr
                key={p.id}
                className={styles.clickableRow}
                onClick={() => router.push(`/admin/golf/pools/${p.id}`)}
              >
                <td>{p.name}</td>
                <td>{p.club_code}</td>
                <td>{p.tournament_name ?? "-"}</td>
                <td>{p.status}</td>
                <td>{p.entries_count}</td>
                <td style={{ fontSize: "0.85rem" }}>
                  {p.entry_deadline
                    ? new Date(p.entry_deadline).toLocaleString()
                    : "-"}
                </td>
                <td style={{ fontSize: "0.85rem" }}>
                  {p.last_scored_at
                    ? new Date(p.last_scored_at).toLocaleString()
                    : "-"}
                </td>
              </tr>
            ))}
          </AdminTable>
        </AdminCard>
      )}
    </div>
  );
}
