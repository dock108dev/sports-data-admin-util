"use client";

import { useState } from "react";
import { LoadoutsPanel } from "./LoadoutsPanel";
import { TrainingPanel } from "./TrainingPanel";
import { EnsemblePanel } from "./EnsemblePanel";
import styles from "../analytics.module.css";

type Tab = "loadouts" | "training" | "ensemble";

export default function WorkbenchPage() {
  const [tab, setTab] = useState<Tab>("loadouts");

  return (
    <div className={styles.container}>
      <header className={styles.pageHeader}>
        <h1 className={styles.pageTitle}>Workbench</h1>
        <p className={styles.pageSubtitle}>
          Build feature loadouts and train models
        </p>
      </header>

      <div style={{ display: "flex", gap: "0.5rem", marginBottom: "1.5rem" }}>
        <button
          className={`${styles.btn} ${tab === "loadouts" ? styles.btnPrimary : ""}`}
          onClick={() => setTab("loadouts")}
        >
          Feature Loadouts
        </button>
        <button
          className={`${styles.btn} ${tab === "training" ? styles.btnPrimary : ""}`}
          onClick={() => setTab("training")}
        >
          Train Model
        </button>
        <button
          className={`${styles.btn} ${tab === "ensemble" ? styles.btnPrimary : ""}`}
          onClick={() => setTab("ensemble")}
        >
          Ensemble Config
        </button>
      </div>

      {tab === "loadouts" ? <LoadoutsPanel /> : tab === "training" ? <TrainingPanel /> : <EnsemblePanel />}
    </div>
  );
}
