"use client";

import { useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { AdminCard, AdminTable } from "@/components/admin";
import { searchPlayers } from "@/lib/api/golf";
import type { GolfPlayer } from "@/lib/api/golfTypes";
import styles from "../golf.module.css";

export default function PlayersPage() {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [players, setPlayers] = useState<GolfPlayer[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searched, setSearched] = useState(false);

  const handleSearch = useCallback(async () => {
    if (!query.trim()) return;
    setLoading(true);
    setError(null);
    setSearched(true);
    try {
      const res = await searchPlayers(query.trim());
      setPlayers(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [query]);

  return (
    <div className={styles.container}>
      <header className={styles.pageHeader}>
        <h1 className={styles.pageTitle}>Players</h1>
        <p className={styles.pageSubtitle}>Search golf players by name</p>
      </header>

      <div className={styles.filterBar}>
        <div className={styles.formGroup}>
          <label>Player Name</label>
          <input
            type="text"
            placeholder="Search players..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") handleSearch();
            }}
          />
        </div>
        <button
          className={`${styles.btn} ${styles.btnPrimary}`}
          onClick={handleSearch}
          disabled={loading || !query.trim()}
          style={{ alignSelf: "flex-end" }}
        >
          {loading ? "Searching..." : "Search"}
        </button>
      </div>

      {error && <div className={styles.error}>{error}</div>}
      {loading && <div className={styles.loading}>Searching...</div>}

      {!loading && searched && players.length === 0 && !error && (
        <div className={styles.empty}>No players found.</div>
      )}

      {!loading && players.length > 0 && (
        <AdminCard>
          <AdminTable headers={["Player Name", "Country", "DG ID", "Amateur"]}>
            {players.map((p) => (
              <tr
                key={p.dg_id}
                className={styles.clickableRow}
                onClick={() => router.push(`/admin/golf/players/${p.dg_id}`)}
              >
                <td>{p.player_name}</td>
                <td>{p.country ?? "-"}</td>
                <td>{p.dg_id}</td>
                <td>{p.amateur ? "Yes" : "No"}</td>
              </tr>
            ))}
          </AdminTable>
        </AdminCard>
      )}
    </div>
  );
}
