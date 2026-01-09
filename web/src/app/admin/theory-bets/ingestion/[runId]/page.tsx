import Link from "next/link";
import styles from "./styles.module.css";
import { fetchScrapeRun } from "@/lib/api/sportsAdmin";

type Params = {
  params: Promise<{
    runId: string;
  }>;
};

/**
 * Scrape run detail page.
 * 
 * Displays comprehensive information about a specific scrape run including:
 * - Run metadata (league, season, status, timestamps)
 * - Configuration payload used for the run
 * - Summary/result message from the scraper
 * 
 * This is a server component that fetches run data at request time.
 */
export default async function RunDetailPage({ params }: Params) {
  const { runId: runIdParam } = await params;
  const runId = Number(runIdParam);
  const run = await fetchScrapeRun(runId);

  return (
    <div className={styles.container}>
      <Link href="/admin/theory-bets/ingestion" className={styles.backLink}>
        ← Back to runs
      </Link>

      <section className={styles.card}>
        <h1>Run #{run.id}</h1>
        <div className={styles.metaGrid}>
          <div>
            <span className={styles.label}>League</span>
            <p>{run.league_code}</p>
          </div>
          <div>
            <span className={styles.label}>Status</span>
            <p className={styles.status}>{run.status}</p>
          </div>
          <div>
            <span className={styles.label}>Job ID</span>
            <p>{run.job_id ?? "—"}</p>
          </div>
          <div>
            <span className={styles.label}>Season</span>
            <p>{run.season ?? "—"}</p>
          </div>
          <div>
            <span className={styles.label}>Requested by</span>
            <p>{run.requested_by ?? "—"}</p>
          </div>
          <div>
            <span className={styles.label}>Created</span>
            <p>{new Date(run.created_at).toLocaleString()}</p>
          </div>
          <div>
            <span className={styles.label}>Finished</span>
            <p>{run.finished_at ? new Date(run.finished_at).toLocaleString() : "—"}</p>
          </div>
        </div>

        <div className={styles.configBlock}>
          <h2>Config</h2>
          <pre>{JSON.stringify(run.config ?? {}, null, 2)}</pre>
        </div>
        {run.error_details && (
          <div className={styles.summary}>
            <h2>Error</h2>
            <pre>{run.error_details}</pre>
          </div>
        )}
        {run.summary && (
          <div className={styles.summary}>
            <h2>Summary</h2>
            <p>{run.summary}</p>
          </div>
        )}
      </section>
    </div>
  );
}

