"use client";

import { type DataStatusResult } from "@/lib/utils/dataStatus";
import styles from "./DataStatusIndicator.module.css";

interface DataStatusIndicatorProps {
  status: DataStatusResult;
  label?: string;
  /** Compact mode for table cells (dot only). Expanded mode shows pill with label text. */
  compact?: boolean;
  /** Optional count to show next to the dot (e.g. play count, social count) */
  count?: number;
}

/**
 * Renders a coloured status dot (or dash) with a tooltip explaining the status.
 *
 * - present:        green dot
 * - missing:        red dot
 * - stale:          amber dot
 * - not_applicable: gray dash
 */
export function DataStatusIndicator({
  status,
  label,
  compact = true,
  count,
}: DataStatusIndicatorProps) {
  if (!compact) {
    // Expanded pill (game detail page)
    const expandedClass =
      status.status === "present"
        ? styles.expandedPresent
        : status.status === "missing"
          ? styles.expandedMissing
          : status.status === "stale"
            ? styles.expandedStale
            : styles.expandedNotApplicable;

    const text =
      status.status === "present"
        ? "Yes"
        : status.status === "missing"
          ? "No"
          : status.status === "stale"
            ? "Stale"
            : "N/A";

    return (
      <span
        className={`${styles.expanded} ${expandedClass}`}
        title={status.reason}
      >
        {label ? `${label}: ${text}` : text}
      </span>
    );
  }

  // Compact mode (table cell)
  if (status.status === "not_applicable") {
    return (
      <span className={styles.wrapper} title={status.reason}>
        <span className={styles.dash} />
      </span>
    );
  }

  const dotClass =
    status.status === "present"
      ? styles.dotPresent
      : status.status === "missing"
        ? styles.dotMissing
        : styles.dotStale;

  return (
    <span className={styles.wrapper} title={status.reason}>
      <span className={`${styles.dot} ${dotClass}`} />
      {count !== undefined && count > 0 && (
        <span className={styles.count}>{count}</span>
      )}
    </span>
  );
}
