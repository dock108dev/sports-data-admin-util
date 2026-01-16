"use client";

import { useMemo, useState } from "react";
import type { HighlightEntry } from "@/lib/api/sportsAdmin";
import { CollapsibleSection } from "./CollapsibleSection";
import styles from "./styles.module.css";

const HIGHLIGHTS_PER_PAGE = 15;

interface HighlightsSectionProps {
  highlights: HighlightEntry[];
}

export function HighlightsSection({ highlights }: HighlightsSectionProps) {
  const [page, setPage] = useState(0);

  const sortedHighlights = useMemo(() => {
    // Sort by segment_id to maintain chronological order
    // segment_id can be a string like "segment_2" or a number
    const extractSegmentNum = (id: string | number | null): number => {
      if (id === null) return 0;
      if (typeof id === "number") return id;
      const match = id.match(/(\d+)/);
      return match ? parseInt(match[1], 10) : 0;
    };
    return [...(highlights || [])].sort((a, b) => {
      const segA = extractSegmentNum(a.segment_id);
      const segB = extractSegmentNum(b.segment_id);
      return segA - segB;
    });
  }, [highlights]);

  const totalPages = Math.ceil(sortedHighlights.length / HIGHLIGHTS_PER_PAGE);
  const paginatedHighlights = sortedHighlights.slice(
    page * HIGHLIGHTS_PER_PAGE,
    (page + 1) * HIGHLIGHTS_PER_PAGE
  );

  const getImportanceColor = (importance: string | null) => {
    switch (importance) {
      case "high":
        return "#dc2626";
      case "medium":
        return "#f59e0b";
      case "low":
        return "#22c55e";
      default:
        return "#64748b";
    }
  };

  const getTypeIcon = (type: string) => {
    switch (type) {
      case "scoring_run":
        return "🏃";
      case "momentum_shift":
        return "📈";
      case "key_play":
        return "⭐";
      case "clutch_moment":
        return "🔥";
      case "defensive_stop":
        return "🛡️";
      case "quarter_end":
        return "⏱️";
      case "overtime":
        return "⚡";
      default:
        return "📌";
    }
  };

  return (
    <CollapsibleSection title="Highlights" defaultOpen={false}>
      {sortedHighlights.length === 0 ? (
        <div style={{ color: "#475569" }}>
          No highlights generated for this game yet.{" "}
          <span style={{ color: "#94a3b8", fontSize: "0.9rem" }}>
            (Timeline artifacts may need to be generated)
          </span>
        </div>
      ) : (
        <>
          <div style={{ marginBottom: "1rem", color: "#64748b", fontSize: "0.9rem" }}>
            Showing {page * HIGHLIGHTS_PER_PAGE + 1}–
            {Math.min((page + 1) * HIGHLIGHTS_PER_PAGE, sortedHighlights.length)} of{" "}
            {sortedHighlights.length} highlights
          </div>

          <div className={styles.highlightsGrid}>
            {paginatedHighlights.map((highlight, idx) => (
              <div key={`${highlight.segment_id}-${idx}`} className={styles.highlightCard}>
                <div className={styles.highlightHeader}>
                  <span className={styles.highlightIcon}>{getTypeIcon(highlight.type)}</span>
                  <span className={styles.highlightType}>{highlight.type.replace(/_/g, " ")}</span>
                  {highlight.segment_id !== null && (
                    <span className={styles.segmentBadge}>Seg #{highlight.segment_id}</span>
                  )}
                  {highlight.importance && (
                    <span
                      className={styles.importanceBadge}
                      style={{ backgroundColor: getImportanceColor(highlight.importance) }}
                    >
                      {highlight.importance}
                    </span>
                  )}
                </div>
                <div className={styles.highlightDescription}>{highlight.description}</div>
              </div>
            ))}
          </div>

          {totalPages > 1 && (
            <div className={styles.paginationControls}>
              <button
                type="button"
                onClick={() => setPage((p) => Math.max(0, p - 1))}
                disabled={page === 0}
                className={styles.paginationButton}
              >
                ← Previous
              </button>
              <span className={styles.paginationInfo}>
                Page {page + 1} of {totalPages}
              </span>
              <button
                type="button"
                onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
                disabled={page === totalPages - 1}
                className={styles.paginationButton}
              >
                Next →
              </button>
            </div>
          )}
        </>
      )}
    </CollapsibleSection>
  );
}
