"use client";

import { useState } from "react";
import type { MomentEntry } from "@/lib/api/sportsAdmin";
import { CollapsibleSection } from "./CollapsibleSection";
import styles from "./styles.module.css";

const MOMENTS_PER_PAGE = 10;

interface HighlightsSectionProps {
  highlights: MomentEntry[];
}

export function HighlightsSection({ highlights }: HighlightsSectionProps) {
  const [page, setPage] = useState(0);
  const moments = highlights || [];

  const totalPages = Math.ceil(moments.length / MOMENTS_PER_PAGE);
  const paginatedMoments = moments.slice(
    page * MOMENTS_PER_PAGE,
    (page + 1) * MOMENTS_PER_PAGE
  );

  const getTypeIcon = (type: string) => {
    switch (type.toUpperCase()) {
      case "RUN":
        return "🏃";
      case "BATTLE":
        return "🔄";
      case "CLOSING":
        return "⏱️";
      default:
        return "📌";
    }
  };

  const getTypeLabel = (type: string) => {
    switch (type.toUpperCase()) {
      case "RUN":
        return "Scoring Run";
      case "BATTLE":
        return "Lead Battle";
      case "CLOSING":
        return "Closing Stretch";
      case "NEUTRAL":
        return "Neutral";
      default:
        return type;
    }
  };

  const getTypeColor = (type: string) => {
    switch (type.toUpperCase()) {
      case "RUN":
        return "#22c55e"; // Green
      case "BATTLE":
        return "#f59e0b"; // Orange
      case "CLOSING":
        return "#dc2626"; // Red
      default:
        return "#64748b"; // Gray
    }
  };

  return (
    <CollapsibleSection title="Highlights" defaultOpen={true}>
      {moments.length === 0 ? (
        <div className={styles.emptyHighlights}>
          <div className={styles.emptyIcon}>📊</div>
          <div>No highlights generated for this game yet.</div>
          <div className={styles.emptyHint}>
            Timeline artifacts may need to be generated or regenerated.
          </div>
        </div>
      ) : (
        <>
          <div className={styles.highlightsSummary}>
            <span>{moments.length} highlights</span>
            <span className={styles.highlightsSummaryDivider}>•</span>
            <span>Chronological</span>
          </div>

          <div className={styles.highlightsGrid}>
            {paginatedMoments.map((moment, idx) => (
              <div key={moment.id || `moment-${idx}`} className={styles.highlightCard}>
                {/* Header: Type + Note */}
                <div className={styles.highlightHeader}>
                  <span className={styles.highlightIcon}>
                    {getTypeIcon(moment.type)}
                  </span>
                  <span className={styles.highlightTitle}>
                    {getTypeLabel(moment.type)}
                  </span>
                  {moment.note && (
                    <span
                      className={styles.phaseBadge}
                      style={{ backgroundColor: getTypeColor(moment.type) }}
                    >
                      {moment.note}
                    </span>
                  )}
                </div>

                {/* Score context */}
                <div className={styles.highlightContext}>
                  <div className={styles.scoreChange}>
                    <span className={styles.contextLabel}>Score:</span>
                    <span className={styles.contextValue}>
                      {moment.score_start} → {moment.score_end}
                    </span>
                  </div>
                  {moment.clock && (
                    <div className={styles.clockRange}>
                      <span className={styles.contextLabel}>When:</span>
                      <span className={styles.contextValue}>{moment.clock}</span>
                    </div>
                  )}
                </div>

                {/* Participants */}
                <div className={styles.highlightParticipants}>
                  {moment.teams.length > 0 && (
                    <div className={styles.teamsInvolved}>
                      {moment.teams.map((team) => (
                        <span key={team} className={styles.teamBadge}>
                          {team}
                        </span>
                      ))}
                    </div>
                  )}
                  {moment.players.length > 0 && (
                    <div className={styles.playersInvolved}>
                      {moment.players.map((player) => (
                        <span key={player.name} className={styles.playerBadge}>
                          <span className={styles.playerName}>{player.name}</span>
                          {player.summary && (
                            <span className={styles.playerStats}>{player.summary}</span>
                          )}
                        </span>
                      ))}
                    </div>
                  )}
                </div>

                {/* Footer: Play range */}
                <div className={styles.highlightFooter}>
                  <span className={styles.playLink}>
                    Plays #{moment.start_play}–#{moment.end_play}
                  </span>
                  <span className={styles.playCount}>
                    ({moment.play_count} plays)
                  </span>
                </div>
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
