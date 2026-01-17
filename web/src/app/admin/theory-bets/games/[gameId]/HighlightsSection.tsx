"use client";

import { useMemo, useState } from "react";
import type { HighlightEntry } from "@/lib/api/sportsAdmin";
import { CollapsibleSection } from "./CollapsibleSection";
import styles from "./styles.module.css";

const HIGHLIGHTS_PER_PAGE = 10;

interface HighlightsSectionProps {
  highlights: HighlightEntry[];
}

export function HighlightsSection({ highlights }: HighlightsSectionProps) {
  const [page, setPage] = useState(0);

  // Sort by importance score (highest first)
  const sortedHighlights = useMemo(() => {
    return [...(highlights || [])].sort((a, b) => {
      return (b.importance_score ?? 0.5) - (a.importance_score ?? 0.5);
    });
  }, [highlights]);

  const totalPages = Math.ceil(sortedHighlights.length / HIGHLIGHTS_PER_PAGE);
  const paginatedHighlights = sortedHighlights.slice(
    page * HIGHLIGHTS_PER_PAGE,
    (page + 1) * HIGHLIGHTS_PER_PAGE
  );

  const getTypeIcon = (type: string) => {
    switch (type.toUpperCase()) {
      case "SCORING_RUN":
        return "🏃";
      case "LEAD_CHANGE":
        return "🔄";
      case "MOMENTUM_SHIFT":
        return "📈";
      case "STAR_TAKEOVER":
        return "⭐";
      case "GAME_DECIDING_STRETCH":
        return "🏆";
      case "COMEBACK":
        return "🔥";
      case "BLOWOUT_START":
        return "💨";
      default:
        return "📌";
    }
  };

  const getPhaseLabel = (phase: string) => {
    switch (phase) {
      case "early":
        return "Early Game";
      case "mid":
        return "Mid Game";
      case "late":
        return "Late Game";
      case "closing":
        return "Closing Stretch";
      default:
        return phase;
    }
  };

  const getPhaseColor = (phase: string) => {
    switch (phase) {
      case "early":
        return "#22c55e";
      case "mid":
        return "#3b82f6";
      case "late":
        return "#f59e0b";
      case "closing":
        return "#dc2626";
      default:
        return "#64748b";
    }
  };

  return (
    <CollapsibleSection title="Highlights" defaultOpen={true}>
      {sortedHighlights.length === 0 ? (
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
            <span>{sortedHighlights.length} highlights detected</span>
            <span className={styles.highlightsSummaryDivider}>•</span>
            <span>Sorted by importance</span>
          </div>

          <div className={styles.highlightsGrid}>
            {paginatedHighlights.map((highlight, idx) => (
              <div
                key={highlight.highlight_id || `hl-${idx}`}
                className={styles.highlightCard}
              >
                {/* Header: Type icon + Title + Phase badge */}
                <div className={styles.highlightHeader}>
                  <span className={styles.highlightIcon}>
                    {getTypeIcon(highlight.type)}
                  </span>
                  <span className={styles.highlightTitle}>{highlight.title}</span>
                  <span
                    className={styles.phaseBadge}
                    style={{ backgroundColor: getPhaseColor(highlight.game_phase) }}
                  >
                    {getPhaseLabel(highlight.game_phase)}
                  </span>
                </div>

                {/* Description */}
                <div className={styles.highlightDescription}>
                  {highlight.description}
                </div>

                {/* Context row: Score change + Clock range */}
                <div className={styles.highlightContext}>
                  {highlight.score_change && (
                    <div className={styles.scoreChange}>
                      <span className={styles.contextLabel}>Score:</span>
                      <span className={styles.contextValue}>{highlight.score_change}</span>
                    </div>
                  )}
                  {highlight.game_clock_range && (
                    <div className={styles.clockRange}>
                      <span className={styles.contextLabel}>When:</span>
                      <span className={styles.contextValue}>{highlight.game_clock_range}</span>
                    </div>
                  )}
                </div>

                {/* Participants row: Teams + Players with stats */}
                <div className={styles.highlightParticipants}>
                  {highlight.involved_teams.length > 0 && (
                    <div className={styles.teamsInvolved}>
                      {highlight.involved_teams.map((team) => (
                        <span key={team} className={styles.teamBadge}>
                          {team}
                        </span>
                      ))}
                    </div>
                  )}
                  {highlight.involved_players.length > 0 && (
                    <div className={styles.playersInvolved}>
                      {highlight.involved_players.map((player) => (
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

                {/* Footer: Play links */}
                <div className={styles.highlightFooter}>
                  <span className={styles.playLink}>
                    Plays #{highlight.start_play_id}–#{highlight.end_play_id}
                  </span>
                  {highlight.key_play_ids.length > 0 && (
                    <span className={styles.keyPlays}>
                      Key: {highlight.key_play_ids.map((id) => `#${id}`).join(", ")}
                    </span>
                  )}
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
