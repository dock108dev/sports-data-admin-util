"use client";

import Link from "next/link";
import { useMemo } from "react";
import { type ScrapeRunResponse } from "@/lib/api/sportsAdmin";
import { SCRAPE_RUN_STATUS_COLORS } from "@/lib/constants/sports";
import { formatDateTime } from "@/lib/utils/dateFormat";
import { RunOriginBadge } from "./RunOriginBadge";
import { RunTaskBadges } from "./RunTaskBadges";
import styles from "./ScrapeRunsTable.module.css";

interface ScrapeRunsTableProps {
  runs: ScrapeRunResponse[];
  loading?: boolean;
  onRefresh?: () => void;
  onCancel?: (run: ScrapeRunResponse) => Promise<void>;
  cancellingRunId?: number | null;
  detailLinkPrefix?: string;
}

/**
 * Table component for displaying scrape runs.
 * Shows run metadata, status, origin, tasks, and actions (cancel, view details).
 */
export function ScrapeRunsTable({
  runs,
  loading = false,
  onRefresh,
  onCancel,
  cancellingRunId = null,
  detailLinkPrefix = "/admin/sports/ingestion",
}: ScrapeRunsTableProps) {
  const latestRuns = useMemo(() => runs.slice(0, 25), [runs]);
  const isCancelable = (status: string) => status === "pending" || status === "running";

  return (
    <section className={styles.card}>
      <div className={styles.cardHeader}>
        <h2>Recent Runs</h2>
        {onRefresh && (
          <button onClick={onRefresh} disabled={loading}>
            Refresh
          </button>
        )}
      </div>
      <table className={styles.table}>
        <thead>
          <tr>
            <th>ID</th>
            <th>League</th>
            <th>Status</th>
            <th>Origin</th>
            <th>Tasks</th>
            <th>Season</th>
            <th>Date range</th>
            <th>Summary</th>
            <th>Created</th>
            {onCancel && <th>Actions</th>}
          </tr>
        </thead>
        <tbody>
          {latestRuns.map((run) => (
            <tr key={run.id}>
              <td>
                <Link href={`${detailLinkPrefix}/${run.id}`}>{run.id}</Link>
              </td>
              <td>{run.league_code}</td>
              <td>
                <span
                  className={styles.statusPill}
                  style={{ backgroundColor: SCRAPE_RUN_STATUS_COLORS[run.status] ?? "#5f6368" }}
                >
                  {run.status}
                </span>
              </td>
              <td>
                <RunOriginBadge scraperType={run.scraper_type} requestedBy={run.requested_by} />
              </td>
              <td>
                <RunTaskBadges config={run.config} />
              </td>
              <td>{run.season ?? "—"}</td>
              <td>
                {run.start_date || run.end_date
                  ? `${run.start_date ?? "?"} to ${run.end_date ?? "?"}`
                  : "—"}
              </td>
              <td>{run.summary ?? "—"}</td>
              <td>{formatDateTime(run.created_at)}</td>
              {onCancel && (
                <td className={styles.actionsCell}>
                  {isCancelable(run.status) ? (
                    <button
                      type="button"
                      className={styles.cancelButton}
                      onClick={() => onCancel(run)}
                      disabled={cancellingRunId === run.id}
                    >
                      {cancellingRunId === run.id ? "Canceling..." : "Cancel"}
                    </button>
                  ) : (
                    "—"
                  )}
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
