"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import styles from "./page.module.css";
import { AdminCard, AdminStatCard } from "@/components/admin";
import { ROUTES } from "@/lib/constants/routes";
import { listScrapeRuns, listGames, type ScrapeRunResponse, type GameFilters } from "@/lib/api/sportsAdmin";
import { getStatusClass } from "@/lib/utils/status";

interface DashboardStats {
  totalGames: number;
  totalRuns: number;
  pendingRuns: number;
  runningRuns: number;
}

export default function AdminDashboardPage() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [recentRuns, setRecentRuns] = useState<ScrapeRunResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadDashboard() {
      try {
        setLoading(true);
        
        const [runs, gamesResponse] = await Promise.all([
          listScrapeRuns(),
          listGames({ limit: 1, offset: 0 } as GameFilters),
        ]);

        const pending = runs.filter(r => r.status === "pending").length;
        const running = runs.filter(r => r.status === "running").length;

        setStats({
          totalGames: gamesResponse.total,
          totalRuns: runs.length,
          pendingRuns: pending,
          runningRuns: running,
        });

        setRecentRuns(runs.slice(0, 5));
        setError(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        setLoading(false);
      }
    }

    loadDashboard();
  }, []);

  // Use shared status utility
  const getStatusClassName = (status: string) => {
    const baseClass = getStatusClass(status);
    return styles[baseClass] || styles.runStatusPending;
  };

  if (loading) {
    return <div className={styles.loading}>Loading dashboard...</div>;
  }

  if (error) {
    return <div className={styles.error}>Error: {error}</div>;
  }

  return (
    <div className={styles.container}>
      <header className={styles.header}>
        <h1 className={styles.title}>Dashboard</h1>
        <p className={styles.subtitle}>Sports data ingestion overview</p>
      </header>

      <div className={styles.statsGrid}>
        <AdminStatCard
          label="Total Games"
          value={stats?.totalGames.toLocaleString() ?? 0}
          hint="Across all leagues"
        />
        <AdminStatCard
          label="Scrape Runs"
          value={stats?.totalRuns ?? 0}
          hint="Total completed"
        />
        <AdminStatCard
          label="Pending"
          value={stats?.pendingRuns ?? 0}
          hint="Jobs in queue"
        />
        <AdminStatCard
          label="Running"
          value={stats?.runningRuns ?? 0}
          hint="Active workers"
        />
      </div>

      <AdminCard title="Quick actions" subtitle="Jump to common admin workflows">
        <div className={styles.quickLinks}>
          <Link href={ROUTES.SPORTS_INGESTION} className={styles.quickLink}>
            <div className={styles.quickLinkContent}>
              <div className={styles.quickLinkTitle}>New scrape run</div>
              <div className={styles.quickLinkDesc}>Start a new data ingestion job</div>
            </div>
          </Link>
          <Link href={ROUTES.SPORTS_BROWSER} className={styles.quickLink}>
            <div className={styles.quickLinkContent}>
              <div className={styles.quickLinkTitle}>Data browser</div>
              <div className={styles.quickLinkDesc}>Browse games, teams, and scrape runs</div>
            </div>
          </Link>
          <Link href="/admin/sports/runs" className={styles.quickLink}>
            <div className={styles.quickLinkContent}>
              <div className={styles.quickLinkTitle}>Theory runs</div>
              <div className={styles.quickLinkDesc}>View and trace user theory evaluations</div>
            </div>
          </Link>
          <Link href={ROUTES.SPORTS_STORY_GENERATOR} className={styles.quickLink}>
            <div className={styles.quickLinkContent}>
              <div className={styles.quickLinkTitle}>Flow Generator</div>
              <div className={styles.quickLinkDesc}>Generate and inspect game flow data</div>
            </div>
          </Link>
          <Link href={ROUTES.FAIRBET_ODDS} className={styles.quickLink}>
            <div className={styles.quickLinkContent}>
              <div className={styles.quickLinkTitle}>FairBet Odds</div>
              <div className={styles.quickLinkDesc}>Compare odds across books</div>
            </div>
          </Link>
        </div>
      </AdminCard>

      {recentRuns.length > 0 && (
        <AdminCard title="Recent runs">
          <div className={styles.recentRuns}>
            {recentRuns.map((run) => (
              <Link
                key={run.id}
                href={`/admin/sports/ingestion/${run.id}`}
                className={styles.runItem}
              >
                <div className={`${styles.runStatus} ${getStatusClassName(run.status)}`} />
                <div className={styles.runInfo}>
                  <div className={styles.runTitle}>
                    {run.league_code} {run.season} — {run.status}
                  </div>
                  <div className={styles.runMeta}>
                    {run.start_date} to {run.end_date}
                  </div>
                </div>
              </Link>
            ))}
          </div>
        </AdminCard>
      )}
    </div>
  );
}

