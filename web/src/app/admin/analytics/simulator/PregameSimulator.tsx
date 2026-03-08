"use client";

import { useState, useEffect } from "react";
import { AdminCard } from "@/components/admin";
import {
  runSimulation,
  listMLBTeams,
  listEnsembleConfigs,
  saveEnsembleConfig,
  type SimulationResult,
  type MLBTeam,
  type EnsembleProviderWeight,
  type EnsembleConfigResponse,
} from "@/lib/api/analytics";
import { ScoreDistributionChart, PAProbabilitiesChart } from "../charts";
import styles from "../analytics.module.css";

export function PregameSimulator() {
  const [sport] = useState("mlb");
  const [homeTeam, setHomeTeam] = useState("");
  const [awayTeam, setAwayTeam] = useState("");
  const [iterations, setIterations] = useState(5000);
  const [rollingWindow, setRollingWindow] = useState(30);
  const [probabilityMode, setProbabilityMode] = useState<"ml" | "ensemble">("ml");
  const [result, setResult] = useState<SimulationResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // MLB teams for dropdowns
  const [teams, setTeams] = useState<MLBTeam[]>([]);
  const [teamsLoading, setTeamsLoading] = useState(true);

  // Ensemble config
  const [ensembleConfigs, setEnsembleConfigs] = useState<EnsembleConfigResponse[]>([]);
  const [ruleWeight, setRuleWeight] = useState(0.5);
  const [mlWeight, setMlWeight] = useState(0.5);
  const [savingEnsemble, setSavingEnsemble] = useState(false);

  // Load teams on mount
  useEffect(() => {
    (async () => {
      try {
        const res = await listMLBTeams();
        setTeams(res.teams);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load teams");
      } finally {
        setTeamsLoading(false);
      }
    })();
  }, []);

  // Load ensemble config on mount
  useEffect(() => {
    (async () => {
      try {
        const res = await listEnsembleConfigs();
        setEnsembleConfigs(res.configs);
        const gameConfig = res.configs.find(
          (c) => c.sport === "mlb" && c.model_type === "game",
        );
        if (gameConfig) {
          const rb = gameConfig.providers.find((p) => p.name === "rule_based");
          const ml = gameConfig.providers.find((p) => p.name === "ml");
          if (rb) setRuleWeight(rb.weight);
          if (ml) setMlWeight(ml.weight);
        }
      } catch (err) {
        console.warn("Failed to load ensemble configs, using defaults:", err);
      }
    })();
  }, []);

  const teamsWithStats = teams.filter((t) => t.games_with_stats > 0);

  async function handleSimulate() {
    if (!homeTeam || !awayTeam) return;
    setLoading(true);
    setError(null);
    try {
      const res = await runSimulation({
        sport,
        home_team: homeTeam,
        away_team: awayTeam,
        iterations,
        probability_mode: probabilityMode,
        rolling_window: rollingWindow,
      });
      setResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setResult(null);
    } finally {
      setLoading(false);
    }
  }

  async function handleSaveEnsemble() {
    setSavingEnsemble(true);
    try {
      const providers: EnsembleProviderWeight[] = [
        { name: "rule_based", weight: ruleWeight },
        { name: "ml", weight: mlWeight },
      ];
      await saveEnsembleConfig("mlb", "game", providers);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save ensemble config");
    } finally {
      setSavingEnsemble(false);
    }
  }

  return (
    <>
      <AdminCard title="Pregame Setup">
        <div className={styles.formRow}>
          <div className={styles.formGroup}>
            <label>Sport</label>
            <select value={sport} disabled>
              <option value="mlb">MLB</option>
            </select>
          </div>
          <div className={styles.formGroup}>
            <label>Home Team</label>
            {teamsLoading ? (
              <select disabled><option>Loading...</option></select>
            ) : (
              <select value={homeTeam} onChange={(e) => setHomeTeam(e.target.value)}>
                <option value="">Select home team</option>
                {teamsWithStats.map((t) => (
                  <option key={t.id} value={t.abbreviation} disabled={t.abbreviation === awayTeam}>
                    {t.abbreviation} — {t.name} ({t.games_with_stats} games)
                  </option>
                ))}
              </select>
            )}
          </div>
          <div className={styles.formGroup}>
            <label>Away Team</label>
            {teamsLoading ? (
              <select disabled><option>Loading...</option></select>
            ) : (
              <select value={awayTeam} onChange={(e) => setAwayTeam(e.target.value)}>
                <option value="">Select away team</option>
                {teamsWithStats.map((t) => (
                  <option key={t.id} value={t.abbreviation} disabled={t.abbreviation === homeTeam}>
                    {t.abbreviation} — {t.name} ({t.games_with_stats} games)
                  </option>
                ))}
              </select>
            )}
          </div>
        </div>
        <div className={styles.formRow}>
          <div className={styles.formGroup}>
            <label>Iterations</label>
            <input type="number" value={iterations} onChange={(e) => setIterations(Math.max(100, parseInt(e.target.value) || 100))} min={100} max={50000} />
          </div>
          <div className={styles.formGroup}>
            <label>Rolling Window: {rollingWindow}</label>
            <input type="range" min={5} max={80} step={5} value={rollingWindow} onChange={(e) => setRollingWindow(parseInt(e.target.value))} />
          </div>
          <div className={styles.formGroup}>
            <label>Probability Mode</label>
            <select value={probabilityMode} onChange={(e) => setProbabilityMode(e.target.value as "ml" | "ensemble")}>
              <option value="ml">ML Model</option>
              <option value="ensemble">Ensemble (ML + Rule Based)</option>
            </select>
          </div>
        </div>

        {/* Inline ensemble weight config */}
        {probabilityMode === "ensemble" && (
          <div className={styles.formRow} style={{ alignItems: "flex-end", gap: "1rem", marginTop: "0.5rem" }}>
            <div className={styles.formGroup} style={{ flex: 1 }}>
              <label>Rule-Based Weight: {(ruleWeight * 100).toFixed(0)}%</label>
              <input
                type="range"
                min={0}
                max={100}
                step={5}
                value={ruleWeight * 100}
                onChange={(e) => {
                  const v = parseInt(e.target.value) / 100;
                  setRuleWeight(v);
                  setMlWeight(Math.round((1 - v) * 100) / 100);
                }}
              />
            </div>
            <div className={styles.formGroup} style={{ flex: 1 }}>
              <label>ML Weight: {(mlWeight * 100).toFixed(0)}%</label>
              <input
                type="range"
                min={0}
                max={100}
                step={5}
                value={mlWeight * 100}
                onChange={(e) => {
                  const v = parseInt(e.target.value) / 100;
                  setMlWeight(v);
                  setRuleWeight(Math.round((1 - v) * 100) / 100);
                }}
              />
            </div>
            <button
              className={styles.btn}
              onClick={handleSaveEnsemble}
              disabled={savingEnsemble}
              style={{ whiteSpace: "nowrap" }}
            >
              {savingEnsemble ? "Saving..." : "Save Weights"}
            </button>
          </div>
        )}

        <div className={styles.formRow} style={{ marginTop: "0.75rem" }}>
          <button className={`${styles.btn} ${styles.btnPrimary}`} onClick={handleSimulate} disabled={loading || !homeTeam || !awayTeam || homeTeam === awayTeam}>
            {loading ? "Simulating..." : "Run Simulation"}
          </button>
          {homeTeam && awayTeam && homeTeam === awayTeam && (
            <span style={{ color: "#ef4444", fontSize: "0.85rem" }}>Home and away must be different teams</span>
          )}
        </div>
      </AdminCard>

      {error && <div className={styles.error}>{error}</div>}

      {result && (
        <div className={styles.resultsSection}>
          <AdminCard title="Win Probability">
            <div className={styles.statsRow}>
              <div className={styles.statBox}>
                <div className={styles.statValue}>{(result.home_win_probability * 100).toFixed(1)}%</div>
                <div className={styles.statLabel}>{result.home_team} (Home)</div>
              </div>
              <div className={styles.statBox}>
                <div className={styles.statValue}>{(result.away_win_probability * 100).toFixed(1)}%</div>
                <div className={styles.statLabel}>{result.away_team} (Away)</div>
              </div>
            </div>
            <div className={styles.probBar}>
              <span className={styles.probLabel}>{result.home_team}</span>
              <div className={styles.probTrack}>
                <div className={styles.probFill} style={{ width: `${result.home_win_probability * 100}%` }} />
              </div>
              <span className={styles.probLabel} style={{ textAlign: "right" }}>{result.away_team}</span>
            </div>
          </AdminCard>

          {/* Model Prediction (if game model ran) */}
          {result.model_home_win_probability != null && (
            <AdminCard title="Game Model Prediction" subtitle="Trained model win probability">
              <div className={styles.statsRow}>
                <div className={styles.statBox}>
                  <div className={styles.statValue}>{(result.model_home_win_probability * 100).toFixed(1)}%</div>
                  <div className={styles.statLabel}>{result.home_team} (Model)</div>
                </div>
                <div className={styles.statBox}>
                  <div className={styles.statValue}>{((1 - result.model_home_win_probability) * 100).toFixed(1)}%</div>
                  <div className={styles.statLabel}>{result.away_team} (Model)</div>
                </div>
              </div>
            </AdminCard>
          )}

          {/* PA Probabilities used */}
          {result.home_pa_probabilities && result.away_pa_probabilities && (
            <AdminCard title="PA Probabilities" subtitle={`From rolling ${result.profile_meta?.rolling_window ?? 30}-game profiles`}>
              <PAProbabilitiesChart
                homeProbs={result.home_pa_probabilities}
                awayProbs={result.away_pa_probabilities}
                homeLabel={result.home_team}
                awayLabel={result.away_team}
              />
            </AdminCard>
          )}

          {result.profile_meta && !result.profile_meta.has_profiles && (
            <AdminCard title="Profile Status">
              <p style={{ color: "#ef4444", fontSize: "0.9rem" }}>
                Could not load team profiles. Using league-average defaults.
                Make sure team abbreviations are correct and games have advanced stats ingested.
              </p>
            </AdminCard>
          )}

          <AdminCard title="Average Score" subtitle={`Based on ${result.iterations.toLocaleString()} simulations`}>
            <div className={styles.statsRow}>
              <div className={styles.statBox}>
                <div className={styles.statValue}>{result.average_home_score}</div>
                <div className={styles.statLabel}>{result.home_team} Avg</div>
              </div>
              <div className={styles.statBox}>
                <div className={styles.statValue}>{result.average_away_score}</div>
                <div className={styles.statLabel}>{result.away_team} Avg</div>
              </div>
              <div className={styles.statBox}>
                <div className={styles.statValue}>{result.average_total}</div>
                <div className={styles.statLabel}>Avg Total</div>
              </div>
              <div className={styles.statBox}>
                <div className={styles.statValue}>{result.median_total}</div>
                <div className={styles.statLabel}>Median Total</div>
              </div>
            </div>
          </AdminCard>

          {result.most_common_scores.length > 0 && (
            <AdminCard title="Most Common Scores">
              <ScoreDistributionChart data={result.most_common_scores} />
            </AdminCard>
          )}
        </div>
      )}
    </>
  );
}
