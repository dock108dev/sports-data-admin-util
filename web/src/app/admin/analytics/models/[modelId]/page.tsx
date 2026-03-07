"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { AdminCard } from "@/components/admin";
import { getModelDetails, type ModelDetails } from "@/lib/api/analytics";
import styles from "../../analytics.module.css";

export default function ModelDetailPage() {
  const params = useParams();
  const modelId = decodeURIComponent(params.modelId as string);
  const [model, setModel] = useState<ModelDetails | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const res = await getModelDetails(modelId);
        setModel(res);
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [modelId]);

  if (loading) return <div className={styles.container}><p>Loading model details...</p></div>;
  if (error) return <div className={styles.container}><div className={styles.error}>{error}</div></div>;
  if (!model) return <div className={styles.container}><p>Model not found.</p></div>;

  const metricEntries = Object.entries(model.metrics || {}).filter(
    ([, v]) => typeof v === "number",
  );

  return (
    <div className={styles.container}>
      <header className={styles.pageHeader}>
        <p style={{ marginBottom: "0.5rem" }}>
          <Link href="/admin/analytics/models" style={{ textDecoration: "underline" }}>
            &larr; Back to Models
          </Link>
        </p>
        <h1 className={styles.pageTitle}>{model.model_id}</h1>
        <p className={styles.pageSubtitle}>
          {model.sport?.toUpperCase()} / {model.model_type}
        </p>
      </header>

      {/* Overview */}
      <AdminCard title="Overview">
        <div className={styles.metricsGrid}>
          <div className={styles.metricItem}>
            <span className={styles.metricLabel}>Version</span>
            <span className={styles.metricValue}>v{model.version}</span>
          </div>
          <div className={styles.metricItem}>
            <span className={styles.metricLabel}>Status</span>
            <span className={styles.metricValue}>
              {model.active ? (
                <span style={{ color: "#22c55e" }}>Active</span>
              ) : (
                "Inactive"
              )}
            </span>
          </div>
          <div className={styles.metricItem}>
            <span className={styles.metricLabel}>Created</span>
            <span className={styles.metricValue}>
              {model.created_at ? new Date(model.created_at).toLocaleDateString() : "-"}
            </span>
          </div>
          {model.training_row_count != null && (
            <div className={styles.metricItem}>
              <span className={styles.metricLabel}>Training Rows</span>
              <span className={styles.metricValue}>
                {model.training_row_count.toLocaleString()}
              </span>
            </div>
          )}
        </div>
      </AdminCard>

      {/* Evaluation Metrics */}
      {metricEntries.length > 0 && (
        <AdminCard title="Evaluation Metrics" subtitle="Stored metrics from training evaluation">
          <div className={styles.metricsGrid}>
            {metricEntries.map(([key, val]) => (
              <div key={key} className={styles.metricItem}>
                <span className={styles.metricLabel}>{key}</span>
                <span className={styles.metricValue}>
                  {(val as number).toFixed(4)}
                </span>
              </div>
            ))}
          </div>
        </AdminCard>
      )}

      {/* Artifact Info */}
      <AdminCard title="Artifact Details">
        <table style={{ width: "100%", fontSize: "0.9rem" }}>
          <tbody>
            {model.artifact_path && (
              <tr>
                <td style={{ padding: "0.4rem 0", color: "var(--text-muted)", width: "180px" }}>Artifact Path</td>
                <td style={{ padding: "0.4rem 0", fontFamily: "monospace", fontSize: "0.85rem" }}>{model.artifact_path}</td>
              </tr>
            )}
            {model.metadata_path && (
              <tr>
                <td style={{ padding: "0.4rem 0", color: "var(--text-muted)" }}>Metadata Path</td>
                <td style={{ padding: "0.4rem 0", fontFamily: "monospace", fontSize: "0.85rem" }}>{model.metadata_path}</td>
              </tr>
            )}
            {model.feature_config && (
              <tr>
                <td style={{ padding: "0.4rem 0", color: "var(--text-muted)" }}>Feature Config</td>
                <td style={{ padding: "0.4rem 0" }}>{model.feature_config}</td>
              </tr>
            )}
            {model.random_state != null && (
              <tr>
                <td style={{ padding: "0.4rem 0", color: "var(--text-muted)" }}>Random State</td>
                <td style={{ padding: "0.4rem 0" }}>{model.random_state}</td>
              </tr>
            )}
          </tbody>
        </table>
      </AdminCard>
    </div>
  );
}
