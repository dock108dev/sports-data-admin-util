"use client";

import styles from "./RunOriginBadge.module.css";

interface RunOriginBadgeProps {
  scraperType: string;
  requestedBy: string | null;
}

function deriveOrigin(scraperType: string, requestedBy: string | null): { label: string; className: string } {
  if (scraperType === "game_rescrape") {
    return { label: "Rescrape", className: styles.rescrape };
  }
  if (scraperType === "odds_resync") {
    return { label: "Odds Sync", className: styles.oddsSync };
  }
  if (requestedBy && (requestedBy.includes("@") || requestedBy.toLowerCase().includes("admin"))) {
    return { label: "Manual", className: styles.manual };
  }
  return { label: "Scheduled", className: styles.scheduled };
}

export function RunOriginBadge({ scraperType, requestedBy }: RunOriginBadgeProps) {
  const { label, className } = deriveOrigin(scraperType, requestedBy);
  return <span className={`${styles.badge} ${className}`}>{label}</span>;
}
