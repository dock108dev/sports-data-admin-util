"use client";

import { useEffect, useState } from "react";
import { getFullSeasonDates, shouldAutoFillDates, type LeagueCode } from "@/lib/utils/seasonDates";
import { SUPPORTED_LEAGUES, DEFAULT_SCRAPE_RUN_FORM } from "@/lib/constants/sports";
import styles from "./ScrapeRunForm.module.css";

export type ScrapeRunFormData = typeof DEFAULT_SCRAPE_RUN_FORM;

interface ScrapeRunFormProps {
  onSubmit: (data: ScrapeRunFormData) => Promise<void>;
  loading?: boolean;
  error?: string | null;
  success?: string | null;
}

/**
 * Simplified form for creating scrape runs.
 * - Data type toggles: boxscores, odds, social, pbp
 * - Shared filters: only_missing, updated_before
 */
export function ScrapeRunForm({ onSubmit, loading = false, error, success }: ScrapeRunFormProps) {
  const [form, setForm] = useState<ScrapeRunFormData>(DEFAULT_SCRAPE_RUN_FORM);

  useEffect(() => {
    if (shouldAutoFillDates(form.leagueCode as LeagueCode, form.season, form.startDate, form.endDate)) {
      const seasonYear = Number(form.season);
      if (!isNaN(seasonYear) && seasonYear >= 2000 && seasonYear <= 2100) {
        const dates = getFullSeasonDates(form.leagueCode as LeagueCode, seasonYear);
        setForm((prev) => ({
          ...prev,
          startDate: dates.startDate,
          endDate: dates.endDate,
        }));
      }
    }
  }, [form.leagueCode, form.season]);

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const startDate = form.startDate?.trim() || undefined;
    const endDate = form.endDate?.trim() || undefined;

    if (startDate && !/^\d{4}-\d{2}-\d{2}$/.test(startDate)) {
      throw new Error(`Invalid start date format: ${startDate}. Expected YYYY-MM-DD`);
    }
    if (endDate && !/^\d{4}-\d{2}-\d{2}$/.test(endDate)) {
      throw new Error(`Invalid end date format: ${endDate}. Expected YYYY-MM-DD`);
    }

    await onSubmit(form);
  };

  return (
    <section className={styles.card}>
      <h2>Create Scrape Run</h2>
      {success && <p className={styles.success}>{success}</p>}
      {error && <p className={styles.error}>{error}</p>}
      <form className={styles.form} onSubmit={handleSubmit}>
        <label>
          League
          <select
            value={form.leagueCode}
            onChange={(e) => setForm((prev) => ({ ...prev, leagueCode: e.target.value as LeagueCode }))}
          >
            {SUPPORTED_LEAGUES.map((code) => (
              <option key={code} value={code}>
                {code}
              </option>
            ))}
          </select>
        </label>

        <label>
          Season (optional - auto-fills dates if provided)
          <input
            type="number"
            value={form.season}
            onChange={(e) => setForm((prev) => ({ ...prev, season: e.target.value }))}
            placeholder="2024"
          />
        </label>

        <div className={styles.row}>
          <label>
            Start date
            <input
              type="date"
              value={form.startDate}
              onChange={(e) => setForm((prev) => ({ ...prev, startDate: e.target.value }))}
            />
          </label>
          <label>
            End date
            <input
              type="date"
              value={form.endDate}
              onChange={(e) => setForm((prev) => ({ ...prev, endDate: e.target.value }))}
            />
          </label>
        </div>
        {form.season && !form.startDate && !form.endDate && (
          <p className={styles.hint}>
            Dates will be auto-filled for the full {form.season} season
          </p>
        )}

        <h3 className={styles.sectionTitle}>Data Types</h3>
        <div className={styles.toggles}>
          <label>
            <input
              type="checkbox"
              checked={form.boxscores}
              onChange={(e) => setForm((prev) => ({ ...prev, boxscores: e.target.checked }))}
            />
            Boxscores
          </label>
          <label>
            <input
              type="checkbox"
              checked={form.odds}
              onChange={(e) => setForm((prev) => ({ ...prev, odds: e.target.checked }))}
            />
            Odds
          </label>
          <label>
            <input
              type="checkbox"
              checked={form.social}
              onChange={(e) => setForm((prev) => ({ ...prev, social: e.target.checked }))}
            />
            Social / X Posts
          </label>
          <label>
            <input
              type="checkbox"
              checked={form.pbp}
              onChange={(e) => setForm((prev) => ({ ...prev, pbp: e.target.checked }))}
            />
            Play-by-Play
          </label>
        </div>

        <h3 className={styles.sectionTitle}>Filters</h3>
        <div className={styles.toggles}>
          <label>
            <input
              type="checkbox"
              checked={form.onlyMissing}
              onChange={(e) => setForm((prev) => ({ ...prev, onlyMissing: e.target.checked }))}
            />
            Only missing data
          </label>
        </div>
        <label>
          Updated before (only scrape if last updated before this date)
          <input
            type="date"
            value={form.updatedBefore}
            onChange={(e) => setForm((prev) => ({ ...prev, updatedBefore: e.target.value }))}
          />
        </label>
        <p className={styles.hint}>
          Leave blank to scrape all games in range. Set a date to only rescrape stale data.
        </p>

        <button type="submit" disabled={loading}>
          {loading ? "Scheduling..." : "Schedule Run"}
        </button>
      </form>
    </section>
  );
}
