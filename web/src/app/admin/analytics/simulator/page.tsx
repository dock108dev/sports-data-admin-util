"use client";

import { PregameSimulator } from "./PregameSimulator";
import styles from "../analytics.module.css";

export default function SimulatorPage() {
  return (
    <div className={styles.container}>
      <header className={styles.pageHeader}>
        <h1 className={styles.pageTitle}>Game Simulator</h1>
        <p className={styles.pageSubtitle}>
          Run lineup-aware Monte Carlo pregame simulations
        </p>
      </header>

      <PregameSimulator />
    </div>
  );
}
