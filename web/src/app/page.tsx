"use client";

import Link from "next/link";
import { ROUTES } from "@/lib/constants/routes";
import styles from "./page.module.css";

export default function Home() {
  return (
    <div className={styles.container}>
      <div className={styles.hero}>
        <h1>Sports Data Admin</h1>
        <p>Run scrapers and browse sports data in one place.</p>
      </div>

      <div className={styles.links}>
        <Link href={ROUTES.RUNS} className={styles.card}>
          <div className={styles.cardTitle}>Runs</div>
          <div className={styles.cardBody}>Schedule and monitor boxscore + odds scrapes.</div>
        </Link>
        <Link href={ROUTES.GAMES} className={styles.card}>
          <div className={styles.cardTitle}>Games</div>
          <div className={styles.cardBody}>Explore games, teams, and scrape runs.</div>
        </Link>
        <Link href={ROUTES.FAIRBET_ODDS} className={styles.card}>
          <div className={styles.cardTitle}>FairBet Odds</div>
          <div className={styles.cardBody}>Compare odds across sportsbooks.</div>
        </Link>
      </div>
    </div>
  );
}

