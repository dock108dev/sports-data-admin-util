"use client";

import React, { useState } from "react";
import styles from "./TheoryBuilder.module.css";

interface Props {
  selected: string[];
  available: string[];
  loading: boolean;
  onToggle: (stat: string) => void;
  onSelectAll: () => void;
  onClear: () => void;
}

export function BaseStatsSelector({
  selected,
  available,
  loading,
  onToggle,
  onSelectAll,
  onClear,
}: Props) {
  const [search, setSearch] = useState("");
  const [expanded, setExpanded] = useState(false);

  const filtered = available.filter((stat) =>
    stat.toLowerCase().includes(search.toLowerCase())
  );

  if (loading) {
    return (
      <div className={styles.statsSelector}>
        <div className={styles.loadingMessage}>Loading available stats…</div>
      </div>
    );
  }

  if (available.length === 0) {
    return (
      <div className={styles.statsSelector}>
        <div className={styles.emptyMessage}>
          No stats available. Select a league to load stats.
        </div>
      </div>
    );
  }

  // Collapsed summary view
  if (!expanded && selected.length > 0) {
    return (
      <div className={styles.statsSelector}>
        <button
          type="button"
          className={styles.statsSummary}
          onClick={() => setExpanded(true)}
          aria-expanded={false}
        >
          <span className={styles.statsSummaryLabel}>
            <strong>{selected.length}</strong> stats selected
          </span>
          <span className={styles.statsSummaryList}>
            {selected.slice(0, 5).join(", ")}
            {selected.length > 5 && ` +${selected.length - 5} more`}
          </span>
          <span className={styles.expandIcon}>▼</span>
        </button>
      </div>
    );
  }

  return (
    <div className={styles.statsSelector}>
      <div className={styles.statsHeader}>
        <input
          type="text"
          className={styles.searchInput}
          placeholder="Search stats…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <div className={styles.statActions}>
          <button type="button" className={styles.linkButton} onClick={onSelectAll}>
            Select all
          </button>
          <button type="button" className={styles.linkButton} onClick={onClear}>
            Clear
          </button>
          {selected.length > 0 && (
            <button
              type="button"
              className={styles.linkButton}
              onClick={() => setExpanded(false)}
            >
              Collapse
            </button>
          )}
        </div>
        <span className={styles.statCount}>
          {selected.length} / {available.length}
        </span>
      </div>

      <div className={styles.statsGrid} role="group" aria-label="Available stats">
        {filtered.map((stat) => {
          const isSelected = selected.includes(stat);
          return (
            <button
              key={stat}
              type="button"
              role="checkbox"
              aria-checked={isSelected}
              className={`${styles.statChip} ${isSelected ? styles.statChipSelected : ""}`}
              onClick={() => onToggle(stat)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  onToggle(stat);
                }
              }}
            >
              {isSelected && <span className={styles.statCheck}>✓</span>}
              <span className={styles.statName}>{stat}</span>
            </button>
          );
        })}
      </div>

      {filtered.length === 0 && search && (
        <div className={styles.emptyMessage}>No stats match “{search}”</div>
      )}
    </div>
  );
}

