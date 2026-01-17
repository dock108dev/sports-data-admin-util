"use client";

import { useState } from "react";
import type { MomentEntry } from "@/lib/api/sportsAdmin";
import { CollapsibleSection } from "./CollapsibleSection";
import styles from "./styles.module.css";

const MOMENTS_PER_PAGE = 10;

interface MomentsSectionProps {
  moments: MomentEntry[];
  /** If true, only show notable moments. If false, show all moments. */
  notableOnly?: boolean;
}

/**
 * Displays game moments (narrative segments).
 * 
 * Moments partition the entire game timeline. Each moment has a type
 * indicating what kind of game control change occurred:
 * - FLIP: Leader changed
 * - TIE: Game returned to even
 * - LEAD_BUILD: Lead tier increased
 * - CUT: Lead tier decreased (comeback)
 * - CLOSING_CONTROL: Late-game lock-in
 * - HIGH_IMPACT: Key non-scoring event
 * - OPENER: Period start
 * - NEUTRAL: Normal flow
 * 
 * Notable moments (is_notable=true) are the "highlights" of the game.
 */
export function MomentsSection({ moments: allMoments, notableOnly = true }: MomentsSectionProps) {
  const [page, setPage] = useState(0);
  
  // Filter to notable moments if requested
  const moments = notableOnly 
    ? (allMoments || []).filter(m => m.is_notable)
    : (allMoments || []);

  const totalPages = Math.ceil(moments.length / MOMENTS_PER_PAGE);
  const paginatedMoments = moments.slice(
    page * MOMENTS_PER_PAGE,
    (page + 1) * MOMENTS_PER_PAGE
  );

  const getTypeIcon = (type: string) => {
    switch (type.toUpperCase()) {
      // Lead Ladder types
      case "LEAD_BUILD":
        return "📈";
      case "CUT":
        return "✂️";
      case "TIE":
        return "⚖️";
      case "FLIP":
        return "🔄";
      case "CLOSING_CONTROL":
        return "🔒";
      case "HIGH_IMPACT":
        return "⚡";
      case "OPENER":
        return "🎬";
      case "NEUTRAL":
        return "📊";
      // Legacy types (cached data)
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
      // Lead Ladder types
      case "LEAD_BUILD":
        return "Lead Extended";
      case "CUT":
        return "Comeback";
      case "TIE":
        return "Game Tied";
      case "FLIP":
        return "Lead Change";
      case "CLOSING_CONTROL":
        return "Game Control";
      case "HIGH_IMPACT":
        return "Key Moment";
      case "OPENER":
        return "Period Start";
      case "NEUTRAL":
        return "Game Flow";
      // Legacy types (cached data)
      case "RUN":
        return "Scoring Run";
      case "BATTLE":
        return "Lead Battle";
      case "CLOSING":
        return "Closing Stretch";
      default:
        return type.replace(/_/g, " ");
    }
  };

  const getTypeColor = (type: string) => {
    switch (type.toUpperCase()) {
      // Notable types (always significant)
      case "FLIP":
        return "#8b5cf6"; // Purple - most dramatic
      case "TIE":
        return "#f59e0b"; // Orange
      case "CLOSING_CONTROL":
        return "#dc2626"; // Red - clutch
      case "HIGH_IMPACT":
        return "#ef4444"; // Red
      // Conditionally notable types
      case "LEAD_BUILD":
        return "#22c55e"; // Green - offense
      case "CUT":
        return "#3b82f6"; // Blue - defense/comeback
      case "OPENER":
        return "#6366f1"; // Indigo
      case "NEUTRAL":
        return "#64748b"; // Gray
      // Legacy types (cached data)
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

  const sectionTitle = notableOnly ? "Notable Moments" : "All Moments";

  return (
    <CollapsibleSection title={sectionTitle} defaultOpen={true}>
      {moments.length === 0 ? (
        <div className={styles.emptyHighlights}>
          <div className={styles.emptyIcon}>📊</div>
          <div>No {notableOnly ? "notable " : ""}moments generated for this game yet.</div>
          <div className={styles.emptyHint}>
            Timeline artifacts may need to be generated or regenerated.
          </div>
        </div>
      ) : (
        <>
          <div className={styles.highlightsSummary}>
            <span>{moments.length} {notableOnly ? "notable " : ""}moments</span>
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
                  {moment.team_in_control && (
                    <div className={styles.clockRange}>
                      <span className={styles.contextLabel}>Control:</span>
                      <span className={styles.contextValue}>
                        {moment.team_in_control.toUpperCase()}
                      </span>
                    </div>
                  )}
                  {moment.run_info && (
                    <div className={styles.clockRange}>
                      <span className={styles.contextLabel}>Run:</span>
                      <span className={styles.contextValue}>
                        {moment.run_info.points}-0 {moment.run_info.team}
                      </span>
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
