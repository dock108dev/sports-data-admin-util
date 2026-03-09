"use client";

import { useState, useEffect } from "react";
import { AdminCard, AdminTable } from "@/components/admin";
import {
  runLiveSimulation,
  type LiveSimulateResult,
} from "@/lib/api/analytics";
import { WinProbabilityTimeline } from "../charts";
import styles from "../analytics.module.css";

const LIVE_SIM_STORAGE_KEY = "live-sim-timeline";

function loadPersistedTimeline(): LiveSimulateResult[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = sessionStorage.getItem(LIVE_SIM_STORAGE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function persistTimeline(timeline: LiveSimulateResult[]) {
  try {
    sessionStorage.setItem(LIVE_SIM_STORAGE_KEY, JSON.stringify(timeline));
  } catch {
    // storage full or unavailable — silently ignore
  }
}

export function LiveSimulator() {
  const [sport, setSport] = useState("mlb");
  const [inning, setInning] = useState(1);
  const [half, setHalf] = useState<"top" | "bottom">("top");
  const [outs, setOuts] = useState(0);
  const [first, setFirst] = useState(false);
  const [second, setSecond] = useState(false);
  const [third, setThird] = useState(false);
  const [homeScore, setHomeScore] = useState(0);
  const [awayScore, setAwayScore] = useState(0);
  const [iterations, setIterations] = useState(2000);
  const [result, setResult] = useState<LiveSimulateResult | null>(null);
  const [timeline, setTimeline] = useState<LiveSimulateResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Restore timeline from session storage on mount
  useEffect(() => {
    const saved = loadPersistedTimeline();
    if (saved.length > 0) {
      setTimeline(saved);
      setResult(saved[saved.length - 1]);
    }
  }, []);

  async function handleSimulate() {
    setLoading(true);
    setError(null);
    try {
      const res = await runLiveSimulation({
        sport,
        inning,
        half,
        outs,
        bases: { first, second, third },
        score: { home: homeScore, away: awayScore },
        iterations,
      });
      setResult(res);
      setTimeline((prev) => {
        const next = [...prev, res];
        persistTimeline(next);
        return next;
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setResult(null);
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <AdminCard title="Live Game State">
        <div className={styles.formRow}>
          <div className={styles.formGroup}>
            <label>Sport</label>
            <select value={sport} onChange={(e) => setSport(e.target.value)}>
              <option value="mlb">MLB</option>
            </select>
          </div>
          <div className={styles.formGroup}>
            <label>Inning</label>
            <input type="number" value={inning} onChange={(e) => setInning(Math.max(1, parseInt(e.target.value) || 1))} min={1} max={20} />
          </div>
          <div className={styles.formGroup}>
            <label>Half</label>
            <select value={half} onChange={(e) => setHalf(e.target.value as "top" | "bottom")}>
              <option value="top">Top</option>
              <option value="bottom">Bottom</option>
            </select>
          </div>
          <div className={styles.formGroup}>
            <label>Outs</label>
            <select value={outs} onChange={(e) => setOuts(parseInt(e.target.value))}>
              <option value={0}>0</option>
              <option value={1}>1</option>
              <option value={2}>2</option>
            </select>
          </div>
        </div>

        <div className={styles.formRow}>
          <div className={styles.formGroup}>
            <label>Home Score</label>
            <input type="number" value={homeScore} onChange={(e) => setHomeScore(Math.max(0, parseInt(e.target.value) || 0))} min={0} />
          </div>
          <div className={styles.formGroup}>
            <label>Away Score</label>
            <input type="number" value={awayScore} onChange={(e) => setAwayScore(Math.max(0, parseInt(e.target.value) || 0))} min={0} />
          </div>
          <div className={styles.formGroup}>
            <label>Iterations</label>
            <input type="number" value={iterations} onChange={(e) => setIterations(Math.max(1, parseInt(e.target.value) || 1))} min={1} max={50000} />
          </div>
        </div>

        <div className={styles.formRow}>
          <label style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <input type="checkbox" checked={first} onChange={(e) => setFirst(e.target.checked)} />
            Runner on 1st
          </label>
          <label style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <input type="checkbox" checked={second} onChange={(e) => setSecond(e.target.checked)} />
            Runner on 2nd
          </label>
          <label style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <input type="checkbox" checked={third} onChange={(e) => setThird(e.target.checked)} />
            Runner on 3rd
          </label>
        </div>

        <div className={styles.formRow} style={{ marginTop: "0.75rem" }}>
          <button className={`${styles.btn} ${styles.btnPrimary}`} onClick={handleSimulate} disabled={loading}>
            {loading ? "Simulating..." : "Run Live Simulation"}
          </button>
          {timeline.length > 0 && (
            <button className={styles.btn} onClick={() => { setTimeline([]); persistTimeline([]); }}>
              Clear Timeline
            </button>
          )}
        </div>
      </AdminCard>

      {error && <div className={styles.error}>{error}</div>}

      {result && (
        <div className={styles.resultsSection}>
          <AdminCard
            title="Win Probability"
            subtitle={`${half === "top" ? "Top" : "Bot"} ${inning} | ${outs} out${outs !== 1 ? "s" : ""} | Score: ${awayScore}-${homeScore}`}
          >
            <div className={styles.statsRow}>
              <div className={styles.statBox}>
                <div className={styles.statValue}>{(result.home_win_probability * 100).toFixed(1)}%</div>
                <div className={styles.statLabel}>Home Win</div>
              </div>
              <div className={styles.statBox}>
                <div className={styles.statValue}>{(result.away_win_probability * 100).toFixed(1)}%</div>
                <div className={styles.statLabel}>Away Win</div>
              </div>
            </div>

            <div className={styles.probBar}>
              <span className={styles.probLabel}>Home</span>
              <div className={styles.probTrack}>
                <div className={styles.probFill} style={{ width: `${result.home_win_probability * 100}%` }} />
              </div>
              <span className={styles.probLabel} style={{ textAlign: "right" }}>Away</span>
            </div>
          </AdminCard>

          <AdminCard title="Expected Final Score">
            <div className={styles.statsRow}>
              <div className={styles.statBox}>
                <div className={styles.statValue}>{result.expected_final_score.home}</div>
                <div className={styles.statLabel}>Home</div>
              </div>
              <div className={styles.statBox}>
                <div className={styles.statValue}>{result.expected_final_score.away}</div>
                <div className={styles.statLabel}>Away</div>
              </div>
              <div className={styles.statBox}>
                <div className={styles.statValue}>{result.iterations.toLocaleString()}</div>
                <div className={styles.statLabel}>Iterations</div>
              </div>
            </div>
          </AdminCard>
        </div>
      )}

      {timeline.length > 1 && (
        <AdminCard title="Win Probability Timeline">
          <WinProbabilityTimeline
            data={timeline.map((snap) => ({
              label: `${snap.half === "top" ? "T" : "B"}${snap.inning}`,
              home: +(snap.home_win_probability * 100).toFixed(1),
              away: +(snap.away_win_probability * 100).toFixed(1),
            }))}
          />
          <div style={{ marginTop: "1rem" }}>
            <AdminTable headers={["State", "Home WP", "Away WP", "Score"]}>
              {timeline.map((snap, i) => (
                <tr key={i}>
                  <td>{snap.half === "top" ? "T" : "B"}{snap.inning}</td>
                  <td>{(snap.home_win_probability * 100).toFixed(1)}%</td>
                  <td>{(snap.away_win_probability * 100).toFixed(1)}%</td>
                  <td>{snap.score.away}-{snap.score.home}</td>
                </tr>
              ))}
            </AdminTable>
          </div>
        </AdminCard>
      )}
    </>
  );
}
