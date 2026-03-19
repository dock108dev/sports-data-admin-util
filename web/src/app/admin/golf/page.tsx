"use client";

import Link from "next/link";
import { AdminCard } from "@/components/admin";
import styles from "./golf.module.css";

const SECTIONS = [
  {
    href: "/admin/golf/tournaments",
    title: "Tournaments",
    description: "Browse upcoming and past tournaments across tours",
  },
  {
    href: "/admin/golf/players",
    title: "Players",
    description: "Search players by name, view stats and rankings",
  },
  {
    href: "/admin/golf/tournaments?tab=odds",
    title: "Odds",
    description: "Outright odds and implied probabilities by market",
  },
  {
    href: "/admin/golf/tournaments?tab=dfs",
    title: "DFS",
    description: "DraftKings and FanDuel salary projections",
  },
  {
    href: "/admin/control-panel",
    title: "Control Panel",
    description: "Trigger golf data pipelines and scrape tasks",
  },
];

export default function GolfDashboardPage() {
  return (
    <div className={styles.container}>
      <header className={styles.pageHeader}>
        <h1 className={styles.pageTitle}>Golf</h1>
        <p className={styles.pageSubtitle}>
          Tournament data, player stats, odds, and DFS projections
        </p>
      </header>

      <div className={styles.navGrid}>
        {SECTIONS.map((s) => (
          <Link key={s.href} href={s.href} className={styles.navLink}>
            <AdminCard title={s.title} subtitle={s.description}>
              <span className={styles.navArrow}>&rarr;</span>
            </AdminCard>
          </Link>
        ))}
      </div>
    </div>
  );
}
