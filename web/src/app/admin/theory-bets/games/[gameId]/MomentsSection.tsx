"use client";

import { useState } from "react";
import type { MomentEntry } from "@/lib/api/sportsAdmin";
import { CollapsibleSection } from "./CollapsibleSection";
import styles from "./styles.module.css";

const MOMENTS_PER_PAGE = 10;

interface MomentsSectionProps {
  moments: MomentEntry[];
}

/**
 * Displays game moments (narrative segments).
 * 
 * Moments partition the entire game timeline into key narrative units.
 * Each moment has a type indicating what kind of game control change occurred:
 * - FLIP: Leader changed
 * - TIE: Game returned to even
 * - LEAD_BUILD: Lead tier increased
 * - CUT: Lead tier decreased (comeback)
 * - CLOSING_CONTROL: Late-game lock-in
 * - HIGH_IMPACT: Key non-scoring event
 * - OPENER: Period start
 * - NEUTRAL: Normal flow
 */
export function MomentsSection({ moments: allMoments }: MomentsSectionProps) {
  const [page, setPage] = useState(0);
  const [showDebugView, setShowDebugView] = useState(false);
  const moments = allMoments || [];

  const totalPages = Math.ceil(moments.length / MOMENTS_PER_PAGE);
  const paginatedMoments = moments.slice(
    page * MOMENTS_PER_PAGE,
    (page + 1) * MOMENTS_PER_PAGE
  );

  const getTypeIcon = (type: string) => {
    switch (type.toUpperCase()) {
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
      default:
        return "📌";
    }
  };

  const getTypeLabel = (type: string) => {
    switch (type.toUpperCase()) {
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
      default:
        return type.replace(/_/g, " ");
    }
  };

  const getTypeColor = (type: string) => {
    switch (type.toUpperCase()) {
      case "FLIP":
        return "#8b5cf6"; // Purple - most dramatic
      case "TIE":
        return "#f59e0b"; // Orange
      case "CLOSING_CONTROL":
        return "#dc2626"; // Red - clutch
      case "HIGH_IMPACT":
        return "#ef4444"; // Red
      case "LEAD_BUILD":
        return "#22c55e"; // Green - offense
      case "CUT":
        return "#3b82f6"; // Blue - defense/comeback
      case "OPENER":
        return "#6366f1"; // Indigo
      case "NEUTRAL":
        return "#64748b"; // Gray
      default:
        return "#64748b"; // Gray
    }
  };

  const getPeriodFromClock = (clock: string) => {
    if (!clock) return null;
    const match = clock.match(/^Q(\d+)/);
    return match ? parseInt(match[1]) : null;
  };

  const checkPeriodBoundaryCrossed = (moment: MomentEntry, prevMoment?: MomentEntry) => {
    if (!moment.clock || !prevMoment?.clock) return false;
    const currentPeriod = getPeriodFromClock(moment.clock);
    const prevPeriod = getPeriodFromClock(prevMoment.clock);
    return currentPeriod !== null && prevPeriod !== null && currentPeriod !== prevPeriod;
  };

  const checkScoreContinuity = (moment: MomentEntry, prevMoment?: MomentEntry) => {
    if (!prevMoment) return { isValid: true, prevEnd: null, currentStart: null };
    const prevEnd = prevMoment.score_end;
    const currentStart = moment.score_start;
    return {
      isValid: prevEnd === currentStart,
      prevEnd,
      currentStart
    };
  };

  return (
    <CollapsibleSection title="Moments" defaultOpen={true}>
      {moments.length === 0 ? (
        <div className={styles.emptyHighlights}>
          <div className={styles.emptyIcon}>📊</div>
          <div>No moments generated for this game yet.</div>
          <div className={styles.emptyHint}>
            Timeline artifacts may need to be generated or regenerated.
          </div>
        </div>
      ) : (
        <>
          <div className={styles.highlightsSummary}>
            <span>{moments.length} moments</span>
            <span className={styles.highlightsSummaryDivider}>•</span>
            <span>Chronological</span>
            <label className={styles.debugToggle}>
              <input
                type="checkbox"
                checked={showDebugView}
                onChange={(e) => setShowDebugView(e.target.checked)}
              />
              Show Moment Construction
            </label>
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

                {/* Debug Information */}
                {showDebugView && (
                  <div className={styles.debugSection}>
                    <div className={styles.debugHeader}>
                      <strong>Moment #{idx + page * MOMENTS_PER_PAGE + 1} — {moment.type}</strong>
                    </div>

                    <div className={styles.debugItem}>
                      <span className={styles.debugLabel}>Triggered by:</span>
                      <span className={styles.debugValue}>
                        {moment.reason?.trigger || "unknown"}
                        {moment.reason?.control_shift && ` (${moment.reason.control_shift})`}
                      </span>
                    </div>

                    <div className={styles.debugItem}>
                      <span className={styles.debugLabel}>Ladder state:</span>
                      <span className={styles.debugValue}>
                        tier: {moment.ladder_tier_before} → {moment.ladder_tier_after}
                        {moment.team_in_control && `, leader: ${moment.team_in_control.toUpperCase()}`}
                      </span>
                    </div>

                    <div className={styles.debugItem}>
                      <span className={styles.debugLabel}>Play range:</span>
                      <span className={styles.debugValue}>
                        #{moment.start_play}–#{moment.end_play} ({moment.play_count} plays)
                      </span>
                    </div>

                    {(() => {
                      const globalIndex = idx + page * MOMENTS_PER_PAGE;
                      const prevMoment = globalIndex > 0 ? allMoments[globalIndex - 1] : undefined;
                      const periodCrossed = checkPeriodBoundaryCrossed(moment, prevMoment);
                      const continuity = checkScoreContinuity(moment, prevMoment);

                      return (
                        <>
                          <div className={styles.debugItem}>
                            <span className={styles.debugLabel}>Period boundary crossed:</span>
                            <span className={`${styles.debugValue} ${periodCrossed ? styles.debugError : styles.debugSuccess}`}>
                              {periodCrossed ? "YES ❌" : "NO ✅"}
                            </span>
                          </div>

                          <div className={styles.debugItem}>
                            <span className={styles.debugLabel}>Score continuity:</span>
                            <div className={styles.debugContinuity}>
                              <div>Prev moment end: {continuity.prevEnd || "N/A"}</div>
                              <div className={continuity.isValid ? styles.debugSuccess : styles.debugError}>
                                This moment start: {continuity.currentStart} {continuity.isValid ? "✅" : "❌"}
                              </div>
                            </div>
                          </div>

                          {(() => {
                            const issues = [];

                            // Check if moment represents any narrative change
                            const hasScoreChange = moment.score_start !== moment.score_end;
                            const hasControlChange = moment.team_in_control !== undefined;
                            const hasLadderChange = moment.ladder_tier_before !== moment.ladder_tier_after;
                            const hasRun = moment.run_info !== undefined;
                            const hasKeyPlays = moment.key_play_ids && moment.key_play_ids.length > 0;
                            const isHighImpact = moment.type === "HIGH_IMPACT";
                            const isSignificantType = ["FLIP", "TIE", "CLOSING_CONTROL"].includes(moment.type);

                            const isValid = hasScoreChange || hasControlChange || hasLadderChange ||
                                          hasRun || hasKeyPlays || isHighImpact || isSignificantType;

                            if (!isValid) {
                              issues.push("❌ INVALID: No narrative change (should be merged)");
                            }

                            // Check for no-op moments (same score)
                            if (moment.score_start === moment.score_end) {
                              issues.push("❌ No score change");
                            }

                            // Check for micro-moments (1 play, not hard trigger)
                            const hardTriggers = ["flip", "tie", "high_impact"];
                            if (moment.play_count === 1 && !hardTriggers.includes(moment.reason?.trigger || "")) {
                              issues.push("❌ Micro-moment (1 play, not significant)");
                            }

                            // Check for score reset (0-0 unless first moment)
                            if (globalIndex > 0 && moment.score_start === "0–0") {
                              issues.push("❌ Score reset (not first moment)");
                            }

                            // Check for OPENER moments that shouldn't exist
                            if (moment.type === "OPENER" && moment.play_count <= 3) {
                              issues.push("❌ OPENER moment (should be merged)");
                            }

                            return issues.length > 0 ? (
                              <div className={styles.debugItem}>
                                <span className={styles.debugLabel}>Validity:</span>
                                <span className={styles.debugError}>❌ INVALID</span>
                                <div className={styles.debugIssues}>
                                  {issues.map((issue, i) => (
                                    <div key={i} className={styles.debugError}>{issue}</div>
                                  ))}
                                </div>
                              </div>
                            ) : (
                              <div className={styles.debugItem}>
                                <span className={styles.debugLabel}>Validity:</span>
                                <span className={styles.debugSuccess}>✅ VALID</span>
                              </div>
                            );
                          })()}
                        </>
                      );
                    })()}
                  </div>
                )}

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
