"use client";

import { useState, useEffect, useCallback } from "react";
import { AdminCard, AdminTable } from "@/components/admin";
import {
  listEnsembleConfigs,
  saveEnsembleConfig,
  type EnsembleConfigResponse,
  type EnsembleProviderWeight,
} from "@/lib/api/analytics";
import styles from "../analytics.module.css";

const KNOWN_PROVIDERS = ["rule_based", "ml", "ensemble"];

export function EnsemblePanel() {
  const [configs, setConfigs] = useState<EnsembleConfigResponse[]>([]);
  const [selected, setSelected] = useState<EnsembleConfigResponse | null>(null);
  const [editing, setEditing] = useState<EnsembleProviderWeight[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await listEnsembleConfigs();
      setConfigs(res.configs);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const handleSelect = (cfg: EnsembleConfigResponse) => {
    setSelected(cfg);
    setEditing(cfg.providers.map((p) => ({ ...p })));
    setMessage(null);
    setError(null);
  };

  const handleWeightChange = (index: number, weight: number) => {
    setEditing((prev) => prev.map((p, i) => (i === index ? { ...p, weight } : p)));
  };

  const handleRemoveProvider = (index: number) => {
    setEditing((prev) => prev.filter((_, i) => i !== index));
  };

  const handleAddProvider = () => {
    const existing = new Set(editing.map((p) => p.name));
    const available = KNOWN_PROVIDERS.filter((n) => !existing.has(n));
    const name = available[0];
    if (!name) return;
    setEditing((prev) => [...prev, { name, weight: 0.5 }]);
  };

  const totalWeight = editing.reduce((sum, p) => sum + p.weight, 0);

  const hasNegativeWeight = editing.some((p) => p.weight < 0);

  const handleSave = async () => {
    if (!selected) return;
    if (editing.length === 0) {
      setError("At least one provider is required");
      return;
    }
    if (editing.some((p) => p.weight < 0)) {
      setError("Weights cannot be negative");
      return;
    }
    if (totalWeight <= 0) {
      setError("At least one provider must have a positive weight");
      return;
    }
    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      const res = await saveEnsembleConfig(selected.sport, selected.model_type, editing);
      setMessage(`Saved ${selected.sport}/${selected.model_type} ensemble config`);
      setSelected({ ...selected, providers: res.providers });
      setEditing(res.providers.map((p) => ({ ...p })));
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  };

  const handleNormalize = () => {
    if (totalWeight === 0) return;
    setEditing((prev) =>
      prev.map((p) => ({
        ...p,
        weight: Math.round((p.weight / totalWeight) * 1000) / 1000,
      })),
    );
  };

  if (loading && !configs.length) {
    return <div className={styles.loading}>Loading ensemble configs...</div>;
  }

  return (
    <div style={{ display: "grid", gridTemplateColumns: "280px 1fr", gap: "1.5rem" }}>
      {/* Left: config list */}
      <div>
        <AdminCard title="Ensemble Configs" subtitle={`${configs.length} configured`}>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
            {configs.map((cfg) => {
              const key = `${cfg.sport}/${cfg.model_type}`;
              const isSelected = selected?.sport === cfg.sport && selected?.model_type === cfg.model_type;
              return (
                <div
                  key={key}
                  style={{
                    padding: "0.5rem",
                    cursor: "pointer",
                    borderRadius: "4px",
                    background: isSelected ? "var(--color-primary-bg, #e8f0fe)" : "transparent",
                    border: isSelected ? "1px solid var(--color-primary, #4285f4)" : "1px solid transparent",
                  }}
                  onClick={() => handleSelect(cfg)}
                >
                  <div style={{ fontWeight: 500, fontSize: "0.875rem" }}>
                    {cfg.sport.toUpperCase()} / {cfg.model_type}
                  </div>
                  <div style={{ fontSize: "0.75rem", color: "#666" }}>
                    {cfg.providers.length} provider{cfg.providers.length !== 1 ? "s" : ""}
                    {" — "}
                    {cfg.providers.map((p) => `${p.name}:${p.weight}`).join(", ")}
                  </div>
                </div>
              );
            })}

            {configs.length === 0 && (
              <p style={{ color: "#666", fontSize: "0.85rem" }}>
                No ensemble configs found. The API returns defaults on first load.
              </p>
            )}
          </div>
        </AdminCard>
      </div>

      {/* Right: editor */}
      <div>
        {error && <div className={styles.error}>{error}</div>}
        {message && <div className={styles.success}>{message}</div>}

        {selected ? (
          <AdminCard
            title={`${selected.sport.toUpperCase()} / ${selected.model_type}`}
            subtitle="Configure probability provider weights for ensemble mode"
          >
            <p style={{ fontSize: "0.85rem", color: "#666", marginBottom: "1rem" }}>
              When <strong>ensemble</strong> probability mode is used, predictions from
              each provider are combined using these weights. Weights are automatically
              normalized to sum to 1.0 at save time.
            </p>

            <AdminTable headers={["Provider", "Weight", "Proportion", ""]}>
              {editing.map((provider, i) => (
                <tr key={i}>
                  <td>
                    <select
                      value={provider.name}
                      onChange={(e) =>
                        setEditing((prev) =>
                          prev.map((p, idx) => (idx === i ? { ...p, name: e.target.value } : p)),
                        )
                      }
                      style={{ padding: "0.25rem", fontSize: "0.85rem" }}
                    >
                      {KNOWN_PROVIDERS.map((n) => (
                        <option key={n} value={n}>
                          {n}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td>
                    <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                      <input
                        type="range"
                        min={0}
                        max={1}
                        step={0.05}
                        value={provider.weight}
                        onChange={(e) => handleWeightChange(i, parseFloat(e.target.value))}
                        style={{ width: "120px" }}
                      />
                      <input
                        type="number"
                        min={0}
                        max={1}
                        step={0.05}
                        value={provider.weight}
                        onChange={(e) => handleWeightChange(i, parseFloat(e.target.value) || 0)}
                        style={{ width: "60px", padding: "0.25rem", fontSize: "0.85rem" }}
                      />
                    </div>
                  </td>
                  <td>
                    <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                      <div
                        style={{
                          width: "80px",
                          height: "16px",
                          background: "#f3f4f6",
                          borderRadius: "3px",
                          overflow: "hidden",
                        }}
                      >
                        <div
                          style={{
                            width: `${totalWeight > 0 ? (provider.weight / totalWeight) * 100 : 0}%`,
                            height: "100%",
                            background: "var(--accent, #3b82f6)",
                            borderRadius: "3px",
                            transition: "width 0.2s",
                          }}
                        />
                      </div>
                      <span style={{ fontSize: "0.8rem", color: "#666" }}>
                        {totalWeight > 0
                          ? `${((provider.weight / totalWeight) * 100).toFixed(0)}%`
                          : "0%"}
                      </span>
                    </div>
                  </td>
                  <td>
                    <button
                      className={styles.btn}
                      style={{ fontSize: "0.7rem", padding: "2px 6px", color: "#c00" }}
                      onClick={() => handleRemoveProvider(i)}
                      disabled={editing.length <= 1}
                    >
                      Remove
                    </button>
                  </td>
                </tr>
              ))}
            </AdminTable>

            <div style={{ display: "flex", gap: "0.5rem", marginTop: "1rem", alignItems: "center" }}>
              <button
                className={`${styles.btn} ${styles.btnPrimary}`}
                onClick={handleSave}
                disabled={saving || editing.length === 0 || hasNegativeWeight || totalWeight <= 0}
              >
                {saving ? "Saving..." : "Save Config"}
              </button>
              <button
                className={styles.btn}
                onClick={handleNormalize}
                disabled={totalWeight === 0}
              >
                Normalize to 1.0
              </button>
              <button
                className={styles.btn}
                onClick={handleAddProvider}
                disabled={editing.length >= KNOWN_PROVIDERS.length}
              >
                + Add Provider
              </button>
              <span style={{
                fontSize: "0.8rem",
                color: hasNegativeWeight || totalWeight <= 0
                  ? "#ef4444"
                  : totalWeight > 0.99 && totalWeight < 1.01
                    ? "#22c55e"
                    : "#f59e0b",
              }}>
                {hasNegativeWeight
                  ? "Negative weights not allowed"
                  : totalWeight <= 0
                    ? "Total weight must be > 0"
                    : `Total weight: ${totalWeight.toFixed(3)}`}
              </span>
            </div>
          </AdminCard>
        ) : (
          <AdminCard title="Ensemble Configuration">
            <p style={{ color: "#666" }}>
              Select an ensemble config from the left panel to edit provider weights.
            </p>
            <p style={{ color: "#999", fontSize: "0.85rem", marginTop: "0.5rem" }}>
              Ensemble mode combines predictions from multiple probability providers
              (rule-based, ML model) using configurable weights. This controls how much
              each source contributes to the final win probability used in simulations.
            </p>
          </AdminCard>
        )}
      </div>
    </div>
  );
}
