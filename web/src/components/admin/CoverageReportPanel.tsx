"use client";

import { useCallback, useEffect, useState } from "react";
import {
  getCoverageReport,
  type CoverageReportResponse,
  type SportBreakdownEntry,
} from "@/lib/api/sportsAdmin/coverageReport";
import styles from "./CoverageReportPanel.module.css";

function SportRow({ entry }: { entry: SportBreakdownEntry }) {
  const coverage =
    entry.finalsCount > 0
      ? Math.round((entry.flowsCount / entry.finalsCount) * 100)
      : 100;

  return (
    <tr>
      <td className={styles.sportCell}>{entry.sport}</td>
      <td>{entry.finalsCount}</td>
      <td>{entry.flowsCount}</td>
      <td>
        {entry.missingCount > 0 ? (
          <span className={styles.missingBadge}>{entry.missingCount}</span>
        ) : (
          entry.missingCount
        )}
      </td>
      <td>
        {entry.fallbackCount > 0 ? (
          <span className={styles.fallbackBadge}>{entry.fallbackCount}</span>
        ) : (
          entry.fallbackCount
        )}
      </td>
      <td>{coverage}%</td>
      <td>
        {entry.avgQualityScore !== null ? `${entry.avgQualityScore}` : "—"}
      </td>
    </tr>
  );
}

export function CoverageReportPanel() {
  const [data, setData] = useState<CoverageReportResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await getCoverageReport();
      setData(res);
      setError(null);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to load";
      // 404 means no report generated yet — show a friendly message
      setError(msg.includes("404") ? "No report available yet. Report generates daily at 06:00 UTC." : msg);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const coveragePct =
    data && data.totalFinals > 0
      ? Math.round((data.totalFlows / data.totalFinals) * 100)
      : null;

  return (
    <div className={styles.panel}>
      <div className={styles.panelHeader}>
        <div>
          <span className={styles.panelTitle}>Pipeline Coverage Report</span>
          {data && (
            <span className={styles.dateBadge}>
              {data.reportDate}
            </span>
          )}
        </div>
        <div className={styles.headerActions}>
          <button className={styles.refreshBtn} disabled={loading} onClick={load}>
            {loading ? "…" : "Refresh"}
          </button>
        </div>
      </div>

      {error && <div className={styles.errorMsg}>{error}</div>}

      {data && (
        <>
          <div className={styles.summaryRow}>
            <div className={styles.statBlock}>
              <span className={styles.statValue}>{data.totalFinals}</span>
              <span className={styles.statLabel}>Final games</span>
            </div>
            <div className={styles.statBlock}>
              <span className={styles.statValue}>{data.totalFlows}</span>
              <span className={styles.statLabel}>Flows generated</span>
            </div>
            <div className={styles.statBlock}>
              <span className={data.totalMissing > 0 ? styles.statValueWarn : styles.statValue}>
                {data.totalMissing}
              </span>
              <span className={styles.statLabel}>Missing</span>
            </div>
            <div className={styles.statBlock}>
              <span className={data.totalFallbacks > 0 ? styles.statValueWarn : styles.statValue}>
                {data.totalFallbacks}
              </span>
              <span className={styles.statLabel}>Fallbacks</span>
            </div>
            {coveragePct !== null && (
              <div className={styles.statBlock}>
                <span className={styles.statValue}>{coveragePct}%</span>
                <span className={styles.statLabel}>Coverage</span>
              </div>
            )}
            {data.avgQualityScore !== null && (
              <div className={styles.statBlock}>
                <span className={styles.statValue}>{data.avgQualityScore}</span>
                <span className={styles.statLabel}>Avg quality</span>
              </div>
            )}
          </div>

          {data.sportBreakdown.length === 0 ? (
            <div className={styles.emptyMsg}>No final games found for this date.</div>
          ) : (
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>Sport</th>
                  <th>Finals</th>
                  <th>Flows</th>
                  <th>Missing</th>
                  <th>Fallbacks</th>
                  <th>Coverage</th>
                  <th>Avg quality</th>
                </tr>
              </thead>
              <tbody>
                {data.sportBreakdown.map((entry) => (
                  <SportRow key={entry.sport} entry={entry} />
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </div>
  );
}
