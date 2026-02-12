"use client";

import { useState, useMemo } from "react";
import type {
  StoryOutput,
  CondensedMoment,
  PlayData,
} from "@/lib/api/sportsAdmin/gameFlowTypes";
import styles from "./FlowViewer.module.css";

/**
 * Story Viewer
 *
 * READ-ONLY display of Story output.
 *
 * This component:
 * - Renders moments in exact order provided
 * - Displays narrative text verbatim (no modification)
 * - Supports expansion to inspect backing plays
 * - Highlights explicitly narrated plays visually
 *
 * This component does NOT:
 * - Generate or modify narrative text
 * - Add headers, titles, or summaries
 * - Reorder moments or plays
 * - Add explanatory captions or tooltips
 * - Recover from validation failures
 */

interface FlowViewerProps {
  /** The Story output to display */
  story: StoryOutput;
  /** All plays for expansion view */
  plays: PlayData[];
  /** Whether validation passed */
  validationPassed: boolean;
  /** Validation errors (if any) */
  validationErrors: string[];
}

export function FlowViewer({
  story,
  plays,
  validationPassed,
  validationErrors,
}: FlowViewerProps) {
  const [expandedMoments, setExpandedMoments] = useState<Set<number>>(
    new Set()
  );
  const [showDebug, setShowDebug] = useState(false);

  // Build play lookup map
  const playMap = useMemo(() => {
    const map = new Map<number, PlayData>();
    for (const play of plays) {
      map.set(play.play_index, play);
    }
    return map;
  }, [plays]);

  // Toggle moment expansion
  const toggleMoment = (momentIndex: number) => {
    const newExpanded = new Set(expandedMoments);
    if (newExpanded.has(momentIndex)) {
      newExpanded.delete(momentIndex);
    } else {
      newExpanded.add(momentIndex);
    }
    setExpandedMoments(newExpanded);
  };

  // Validation failure: show error state, do not attempt recovery
  if (!validationPassed) {
    return (
      <div className={styles.errorState}>
        <p>Story validation failed</p>
        {validationErrors.length > 0 && (
          <ul>
            {validationErrors.map((error, i) => (
              <li key={i}>{error}</li>
            ))}
          </ul>
        )}
      </div>
    );
  }

  // Empty story: show empty state (no filler prose)
  if (!story.moments || story.moments.length === 0) {
    return <div className={styles.emptyState}>No moments</div>;
  }

  return (
    <div className={styles.storyContainer}>
      {/* Debug toggle */}
      <div className={styles.debugToggle}>
        <label>
          <input
            type="checkbox"
            checked={showDebug}
            onChange={(e) => setShowDebug(e.target.checked)}
          />
          Debug
        </label>
      </div>

      {/* Moments - rendered in exact order provided */}
      {story.moments.map((moment, momentIndex) => (
        <MomentCard
          key={momentIndex}
          moment={moment}
          momentIndex={momentIndex}
          isExpanded={expandedMoments.has(momentIndex)}
          onToggle={() => toggleMoment(momentIndex)}
          playMap={playMap}
          showDebug={showDebug}
        />
      ))}
    </div>
  );
}

/**
 * Individual Moment Display
 *
 * Displays:
 * - Narrative (verbatim)
 * - Metadata (period, clock, score) - already present in moment
 * - Expansion: backing plays with explicit plays highlighted
 */
interface MomentCardProps {
  moment: CondensedMoment;
  momentIndex: number;
  isExpanded: boolean;
  onToggle: () => void;
  playMap: Map<number, PlayData>;
  showDebug: boolean;
}

function MomentCard({
  moment,
  momentIndex,
  isExpanded,
  onToggle,
  playMap,
  showDebug,
}: MomentCardProps) {
  // Set of explicitly narrated play IDs for highlighting
  const explicitIds = useMemo(
    () => new Set(moment.explicitly_narrated_play_ids),
    [moment.explicitly_narrated_play_ids]
  );

  // Get plays for this moment
  const momentPlays = useMemo(
    () =>
      moment.play_ids
        .map((pid) => playMap.get(pid))
        .filter((p): p is PlayData => p !== undefined),
    [moment.play_ids, playMap]
  );

  // Format score display
  const formatScore = (score: { home: number; away: number }) =>
    `${score.home}-${score.away}`;

  // Check for score change
  const scoreChanged =
    moment.score_before.home !== moment.score_after.home ||
    moment.score_before.away !== moment.score_after.away;

  return (
    <div className={styles.momentCard}>
      {/* Header - clickable for expansion */}
      <div className={styles.momentHeader} onClick={onToggle}>
        <span className={styles.expandIndicator}>
          {isExpanded ? "▼" : "▶"}
        </span>

        <div className={styles.momentContent}>
          {/* Narrative - displayed verbatim, no modification */}
          <p className={styles.narrative}>{moment.narrative}</p>

          {/* Metadata - only what's already in the moment */}
          <div className={styles.momentMeta}>
            <span className={styles.metaItem}>
              P<span className={styles.metaValue}>{moment.period}</span>
            </span>
            <span className={styles.metaItem}>
              <span className={styles.metaValue}>
                {moment.start_clock}
                {moment.start_clock !== moment.end_clock &&
                  ` → ${moment.end_clock}`}
              </span>
            </span>
            {scoreChanged && (
              <span className={styles.metaItem}>
                <span className={styles.metaValue}>
                  {formatScore(moment.score_before)} →{" "}
                  {formatScore(moment.score_after)}
                </span>
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Expanded View - shows backing plays */}
      {isExpanded && (
        <div className={styles.expandedContent}>
          <div className={styles.playsList}>
            {momentPlays.map((play) => {
              const isExplicit = explicitIds.has(play.play_index);
              return (
                <div
                  key={play.play_index}
                  className={`${styles.playEntry} ${
                    isExplicit ? styles.playEntryExplicit : ""
                  }`}
                >
                  <span className={styles.playIndex}>{play.play_index}</span>
                  <span
                    className={`${styles.playDescription} ${
                      isExplicit ? styles.playDescriptionExplicit : ""
                    }`}
                  >
                    {play.description}
                  </span>
                  {play.game_clock && (
                    <span className={styles.playClock}>{play.game_clock}</span>
                  )}
                  <span className={styles.playScore}>
                    {play.home_score}-{play.away_score}
                  </span>
                </div>
              );
            })}
          </div>

          {/* Debug info - raw data only, no interpretation */}
          {showDebug && (
            <div className={styles.debugInfo}>
              <pre>
                {JSON.stringify(
                  {
                    moment_index: momentIndex,
                    play_ids: moment.play_ids,
                    explicitly_narrated_play_ids:
                      moment.explicitly_narrated_play_ids,
                    period: moment.period,
                    start_clock: moment.start_clock,
                    end_clock: moment.end_clock,
                    score_before: moment.score_before,
                    score_after: moment.score_after,
                  },
                  null,
                  2
                )}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default FlowViewer;
