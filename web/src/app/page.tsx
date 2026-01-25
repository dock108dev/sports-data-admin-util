"use client";

import Link from "next/link";
import styles from "./page.module.css";

export default function Home() {
  return (
    <div className={styles.container}>
      <div className={styles.hero}>
        <h1>Sports Data Admin</h1>
        <p>Run scrapers and browse sports data in one place.</p>
      </div>

      <div className={styles.links}>
        <Link href="/admin/sports/ingestion" className={styles.card}>
          <div className={styles.cardTitle}>Sports Data Ingestion</div>
          <div className={styles.cardBody}>Schedule and monitor boxscore + odds scrapes.</div>
        </Link>
        <Link href="/admin/sports/browser" className={styles.card}>
          <div className={styles.cardTitle}>Data Browser</div>
          <div className={styles.cardBody}>Explore games, teams, and scrape runs.</div>
        </Link>
      </div>
    </div>
  );
}

