"use client";

import { useState } from "react";
import { PregameSimulator } from "./PregameSimulator";
import { LiveSimulator } from "./LiveSimulator";
import { BatchSimulator } from "./BatchSimulator";
import styles from "../analytics.module.css";

type Mode = "pregame" | "live" | "batch";

export default function SimulatorPage() {
  const [mode, setMode] = useState<Mode>("pregame");

  return (
    <div className={styles.container}>
      <header className={styles.pageHeader}>
        <h1 className={styles.pageTitle}>Game Simulator</h1>
        <p className={styles.pageSubtitle}>
          Run Monte Carlo simulations for pregame or live game states
        </p>
      </header>

      <div className={styles.formRow} style={{ marginBottom: "1rem" }}>
        <button
          className={`${styles.btn} ${mode === "pregame" ? styles.btnPrimary : ""}`}
          onClick={() => setMode("pregame")}
        >
          Pregame
        </button>
        <button
          className={`${styles.btn} ${mode === "live" ? styles.btnPrimary : ""}`}
          onClick={() => setMode("live")}
        >
          Live Game
        </button>
        <button
          className={`${styles.btn} ${mode === "batch" ? styles.btnPrimary : ""}`}
          onClick={() => setMode("batch")}
        >
          Batch Upcoming
        </button>
      </div>

      {mode === "pregame" ? <PregameSimulator /> : mode === "live" ? <LiveSimulator /> : <BatchSimulator />}
    </div>
  );
}
