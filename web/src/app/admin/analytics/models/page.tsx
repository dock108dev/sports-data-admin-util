"use client";

import { useEffect, useState } from "react";
import { AdminCard, AdminTable } from "@/components/admin";
import {
  listRegisteredModels,
  activateModel,
  type RegisteredModel,
} from "@/lib/api/analytics";
import styles from "../analytics.module.css";

export default function ModelsPage() {
  const [models, setModels] = useState<RegisteredModel[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activating, setActivating] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const res = await listRegisteredModels();
      setModels(res.models);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function handleActivate(m: RegisteredModel) {
    setActivating(m.model_id);
    try {
      await activateModel(m.sport, m.model_type, m.model_id);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setActivating(null);
    }
  }

  const grouped = models.reduce<Record<string, RegisteredModel[]>>((acc, m) => {
    const key = `${m.sport} / ${m.model_type}`;
    if (!acc[key]) acc[key] = [];
    acc[key].push(m);
    return acc;
  }, {});

  return (
    <div className={styles.container}>
      <header className={styles.pageHeader}>
        <h1 className={styles.pageTitle}>Model Registry</h1>
        <p className={styles.pageSubtitle}>
          View trained models, compare metrics, and activate deployments
        </p>
      </header>

      {error && <div className={styles.error}>{error}</div>}

      {loading && <p>Loading models...</p>}

      {!loading && models.length === 0 && (
        <AdminCard title="No Models Registered">
          <p>Train a model using the training pipeline to see it here.</p>
        </AdminCard>
      )}

      {Object.entries(grouped).map(([group, groupModels]) => (
        <AdminCard key={group} title={group.toUpperCase()} subtitle={`${groupModels.length} version(s)`}>
          <AdminTable
            headers={["Model ID", "Version", "Accuracy", "Log Loss", "Brier Score", "Created", "Active", ""]}
          >
            {groupModels.map((m) => (
              <tr key={m.model_id}>
                <td>{m.model_id}</td>
                <td>v{m.version}</td>
                <td>{m.metrics?.accuracy != null ? m.metrics.accuracy.toFixed(3) : "-"}</td>
                <td>{m.metrics?.log_loss != null ? m.metrics.log_loss.toFixed(3) : "-"}</td>
                <td>{m.metrics?.brier_score != null ? m.metrics.brier_score.toFixed(3) : "-"}</td>
                <td>{m.created_at ? new Date(m.created_at).toLocaleDateString() : "-"}</td>
                <td>{m.active ? "Active" : ""}</td>
                <td>
                  {!m.active && (
                    <button
                      className={`${styles.btn} ${styles.btnPrimary}`}
                      onClick={() => handleActivate(m)}
                      disabled={activating === m.model_id}
                    >
                      {activating === m.model_id ? "Activating..." : "Activate"}
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </AdminTable>
        </AdminCard>
      ))}
    </div>
  );
}
