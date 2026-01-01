"use client";

import { useState } from "react";
import styles from "./styles.module.css";
import { cancelScrapeRun, createScrapeRun, type ScrapeRunResponse } from "@/lib/api/sportsAdmin";
import { useScrapeRuns } from "@/lib/hooks/useScrapeRuns";
import { ScrapeRunForm, type ScrapeRunFormData } from "@/components/admin/ScrapeRunForm";
import { ScrapeRunsTable } from "@/components/admin/ScrapeRunsTable";

/**
 * Sports data ingestion admin page.
 * 
 * Allows administrators to:
 * - Configure scrape runs (league, season, date range, boxscores/odds)
 * - Monitor scrape run status and results
 * - View scrape run history and summaries
 * 
 * Scrape runs are executed by the theory-bets-scraper Celery workers
 * via the theory-engine-api backend.
 */
export default function IngestionAdminPage() {
  const { runs, loading, error: runsError, refetch: fetchRuns } = useScrapeRuns();
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [cancellingRunId, setCancellingRunId] = useState<number | null>(null);

  const displayError = error || runsError;

  const handleSubmit = async (formData: ScrapeRunFormData) => {
    setCreating(true);
    setError(null);
    setSuccess(null);
    try {
      const startDate = formData.startDate?.trim() || undefined;
      const endDate = formData.endDate?.trim() || undefined;

      const result = await createScrapeRun({
        requestedBy: formData.requestedBy,
        config: {
          leagueCode: formData.leagueCode,
          season: formData.season ? Number(formData.season) : undefined,
          startDate,
          endDate,
          boxscores: formData.boxscores,
          odds: formData.odds,
          social: formData.social,
          pbp: formData.pbp,
          onlyMissing: formData.onlyMissing,
          updatedBefore: formData.updatedBefore || undefined,
        },
      });
      setSuccess(`Scrape run #${result.id} scheduled successfully!`);
      fetchRuns();
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : String(err);
      setError(errorMessage);
    } finally {
      setCreating(false);
    }
  };

  const handleCancelRun = async (run: ScrapeRunResponse) => {
    if (cancellingRunId) return;
    if (typeof window !== "undefined") {
      const confirmed = window.confirm(`Cancel scrape run #${run.id}? This cannot be undone.`);
      if (!confirmed) return;
    }

    setCancellingRunId(run.id);
    setError(null);
    setSuccess(null);

    try {
      await cancelScrapeRun(run.id);
      setSuccess(`Scrape run #${run.id} canceled`);
      fetchRuns();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setCancellingRunId(null);
    }
  };

  return (
    <div className={styles.container}>
      <h1>Sports Data Ingestion</h1>
      <p className={styles.subtitle}>Configure and monitor boxscore, odds, and social post scrapes.</p>

      <ScrapeRunForm
        onSubmit={handleSubmit}
        loading={creating}
        error={displayError}
        success={success}
      />

      <ScrapeRunsTable
        runs={runs}
        loading={loading}
        onRefresh={fetchRuns}
        onCancel={handleCancelRun}
        cancellingRunId={cancellingRunId}
      />
    </div>
  );
}

