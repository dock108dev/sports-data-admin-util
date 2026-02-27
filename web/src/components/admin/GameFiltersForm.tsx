"use client";

import { SUPPORTED_LEAGUES } from "@/lib/constants/sports";
import { getQuickDateRange } from "@/lib/utils/dateFormat";
import { type GameFilters } from "@/lib/api/sportsAdmin";
import styles from "./GameFiltersForm.module.css";

interface GameFiltersFormProps {
  filters: GameFilters;
  onFiltersChange: (filters: GameFilters) => void;
  onApply: () => void;
  onReset: () => void;
  onQuickDateRange?: (days: number) => void;
}

/**
 * Reusable form component for filtering games.
 * Supports league selection, season, team search, date ranges, and missing data filters.
 */
export function GameFiltersForm({
  filters,
  onFiltersChange,
  onApply,
  onReset,
  onQuickDateRange,
}: GameFiltersFormProps) {
  const handleLeagueToggle = (code: string) => {
    const exists = filters.leagues.includes(code);
    onFiltersChange({
      ...filters,
      leagues: exists ? filters.leagues.filter((lg) => lg !== code) : [...filters.leagues, code],
    });
  };

  const handleQuickDateRange = (days: number) => {
    if (onQuickDateRange) {
      onQuickDateRange(days);
    } else {
      const { startDate, endDate } = getQuickDateRange(days);
      onFiltersChange({ ...filters, startDate, endDate });
    }
  };

  return (
    <section className={styles.filtersCard}>
      <div className={styles.filterSection}>
        <div className={styles.filterLabel}>Leagues</div>
        <div className={styles.leagueChips}>
          {SUPPORTED_LEAGUES.map((lg) => (
            <button
              key={lg}
              type="button"
              className={`${styles.chip} ${filters.leagues.includes(lg) ? styles.chipActive : ""}`}
              onClick={() => handleLeagueToggle(lg)}
            >
              {lg}
            </button>
          ))}
        </div>
      </div>

      <div className={styles.filterRow}>
        <div className={styles.filterGroup}>
          <label className={styles.filterLabel}>Season</label>
          <input
            type="number"
            className={styles.input}
            placeholder="e.g. 2024"
            value={filters.season ?? ""}
            onChange={(e) =>
              onFiltersChange({
                ...filters,
                season: e.target.value ? Number(e.target.value) : undefined,
              })
            }
          />
        </div>

        <div className={styles.filterGroup}>
          <label className={styles.filterLabel}>Team</label>
          <input
            type="text"
            className={styles.input}
            placeholder="Search team name"
            value={filters.team ?? ""}
            onChange={(e) => onFiltersChange({ ...filters, team: e.target.value })}
          />
        </div>

        <div className={styles.filterGroup}>
          <label className={styles.filterLabel}>Start Date</label>
          <input
            type="date"
            className={styles.input}
            value={filters.startDate ?? ""}
            onChange={(e) => onFiltersChange({ ...filters, startDate: e.target.value || undefined })}
          />
        </div>

        <div className={styles.filterGroup}>
          <label className={styles.filterLabel}>End Date</label>
          <input
            type="date"
            className={styles.input}
            value={filters.endDate ?? ""}
            onChange={(e) => onFiltersChange({ ...filters, endDate: e.target.value || undefined })}
          />
        </div>
      </div>

      {onQuickDateRange && (
        <div className={styles.quickDateRow}>
          <span className={styles.filterLabel}>Quick ranges:</span>
          <button type="button" onClick={() => handleQuickDateRange(7)} className={styles.quickButton}>
            Last 7 days
          </button>
          <button type="button" onClick={() => handleQuickDateRange(30)} className={styles.quickButton}>
            Last 30 days
          </button>
          <button type="button" onClick={() => handleQuickDateRange(90)} className={styles.quickButton}>
            Last 90 days
          </button>
        </div>
      )}

      <div className={styles.filterRow}>
        <div className={styles.filterGroup}>
          <label className={styles.checkboxLabel}>
            <input
              type="checkbox"
              checked={filters.missingBoxscore ?? false}
              onChange={(e) => onFiltersChange({ ...filters, missingBoxscore: e.target.checked })}
            />
            Missing boxscore
          </label>
        </div>
        <div className={styles.filterGroup}>
          <label className={styles.checkboxLabel}>
            <input
              type="checkbox"
              checked={filters.missingPlayerStats ?? false}
              onChange={(e) => onFiltersChange({ ...filters, missingPlayerStats: e.target.checked })}
            />
            Missing player stats
          </label>
        </div>
        <div className={styles.filterGroup}>
          <label className={styles.checkboxLabel}>
            <input
              type="checkbox"
              checked={filters.missingOdds ?? false}
              onChange={(e) => onFiltersChange({ ...filters, missingOdds: e.target.checked })}
            />
            Missing odds
          </label>
        </div>
        <div className={styles.filterGroup}>
          <label className={styles.checkboxLabel}>
            <input
              type="checkbox"
              checked={filters.missingSocial ?? false}
              onChange={(e) => onFiltersChange({ ...filters, missingSocial: e.target.checked })}
            />
            Missing social
          </label>
        </div>
        <div className={styles.filterGroup}>
          <label className={styles.checkboxLabel}>
            <input
              type="checkbox"
              checked={filters.missingAny ?? false}
              onChange={(e) => onFiltersChange({ ...filters, missingAny: e.target.checked })}
            />
            Missing any data
          </label>
        </div>
        <div className={styles.filterGroup}>
          <label className={styles.checkboxLabel}>
            <input
              type="checkbox"
              checked={filters.finalOnly ?? false}
              onChange={(e) => onFiltersChange({ ...filters, finalOnly: e.target.checked })}
            />
            Final games only
          </label>
        </div>
      </div>

      <div className={styles.actionsRow}>
        <button type="button" onClick={onApply} className={styles.applyButton}>
          Apply Filters
        </button>
        <button type="button" onClick={onReset} className={styles.resetButton}>
          Reset
        </button>
      </div>
    </section>
  );
}

