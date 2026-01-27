"use client";

import { useCallback, useEffect, useState } from "react";
import { fetchGameStory } from "@/lib/api/sportsAdmin";
import type { GameStoryResponse, StoryMoment, StoryPlay } from "@/lib/api/sportsAdmin/storyTypes";
import { CollapsibleSection } from "./CollapsibleSection";
import styles from "./styles.module.css";

type StorySectionProps = {
  gameId: number;
  hasStory: boolean;
};

type MomentCardProps = {
  moment: StoryMoment;
  momentIndex: number;
  plays: StoryPlay[];
};

function MomentCard({ moment, momentIndex, plays }: MomentCardProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  // Get plays for this moment
  const momentPlays = plays.filter((p) => moment.playIds.includes(p.playId));
  const explicitPlayIds = new Set(moment.explicitlyNarratedPlayIds);

  // Format score display
  const formatScore = (score: number[]) => {
    if (score.length >= 2) {
      return `${score[0]}-${score[1]}`;
    }
    return "—";
  };

  // Check if score changed
  const scoreChanged =
    moment.scoreBefore[0] !== moment.scoreAfter[0] ||
    moment.scoreBefore[1] !== moment.scoreAfter[1];

  return (
    <div className={styles.momentCard}>
      <div className={styles.momentHeader}>
        <div className={styles.momentMeta}>
          <span className={styles.momentIndex}>#{momentIndex + 1}</span>
          <span className={styles.momentPeriod}>Q{moment.period}</span>
          {moment.startClock && (
            <span className={styles.momentClock}>
              {moment.startClock}
              {moment.endClock && moment.endClock !== moment.startClock && ` → ${moment.endClock}`}
            </span>
          )}
          {scoreChanged && (
            <span className={styles.momentScoreChange}>
              {formatScore(moment.scoreBefore)} → {formatScore(moment.scoreAfter)}
            </span>
          )}
        </div>
        <button
          type="button"
          className={styles.expandButton}
          onClick={() => setIsExpanded(!isExpanded)}
          aria-expanded={isExpanded}
        >
          {isExpanded ? "Hide plays" : `Show ${momentPlays.length} plays`}
        </button>
      </div>

      <div className={styles.momentNarrative}>{moment.narrative}</div>

      {isExpanded && (
        <div className={styles.momentPlays}>
          <table className={styles.playsTable}>
            <thead>
              <tr>
                <th>Clock</th>
                <th>Type</th>
                <th>Description</th>
                <th>Score</th>
              </tr>
            </thead>
            <tbody>
              {momentPlays.map((play) => {
                const isExplicit = explicitPlayIds.has(play.playId);
                return (
                  <tr
                    key={play.playId}
                    className={isExplicit ? styles.explicitPlay : undefined}
                  >
                    <td>{play.clock ?? "—"}</td>
                    <td>{play.playType ?? "—"}</td>
                    <td>{play.description ?? "—"}</td>
                    <td>
                      {play.homeScore !== null && play.awayScore !== null
                        ? `${play.awayScore}-${play.homeScore}`
                        : "—"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <div className={styles.playLegend}>
            <span className={styles.explicitIndicator} /> = Explicitly narrated play
          </div>
        </div>
      )}
    </div>
  );
}

export function StorySection({ gameId, hasStory }: StorySectionProps) {
  const [story, setStory] = useState<GameStoryResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadStory = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchGameStory(gameId);
      setStory(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load story");
    } finally {
      setLoading(false);
    }
  }, [gameId]);

  useEffect(() => {
    if (hasStory) {
      loadStory();
    }
  }, [hasStory, loadStory]);

  // Don't render section if no story
  if (!hasStory) {
    return null;
  }

  return (
    <CollapsibleSection title="Story" defaultOpen={true}>
      {loading && <div className={styles.subtle}>Loading story...</div>}

      {error && <div className={styles.storyError}>Error: {error}</div>}

      {!loading && !error && !story && (
        <div className={styles.subtle}>No story found.</div>
      )}

      {story && (
        <div className={styles.storyContainer}>
          {!story.validationPassed && story.validationErrors.length > 0 && (
            <div className={styles.validationWarning}>
              <strong>Validation issues:</strong>
              <ul>
                {story.validationErrors.map((err, i) => (
                  <li key={i}>{err}</li>
                ))}
              </ul>
            </div>
          )}

          <div className={styles.storySummary}>
            {story.story.moments.length} moments · {story.plays.length} plays
          </div>

          <div className={styles.momentsList}>
            {story.story.moments.map((moment, idx) => (
              <MomentCard
                key={idx}
                moment={moment}
                momentIndex={idx}
                plays={story.plays}
              />
            ))}
          </div>
        </div>
      )}
    </CollapsibleSection>
  );
}
