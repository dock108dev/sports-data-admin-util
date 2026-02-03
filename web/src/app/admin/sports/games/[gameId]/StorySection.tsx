"use client";

/**
 * Story Section (Legacy Moment-based View)
 *
 * PHASE 5 CONTRACT NOTE
 * =====================
 * This component displays the moment-based story view for debugging/admin.
 *
 * For the consumer-facing collapsed game flow, use:
 * - CollapsedGameFlow (narrative blocks only)
 * - GameFlowView (blocks + optional social sections)
 *
 * These components are in: @/components/story/
 *
 * Critical rules:
 * - Social content is SEPARATE from story content
 * - No UI elements imply tweets explain plays
 * - The "Show X plays" button is for debugging, not consumer display
 *
 * 🚫 DO NOT add tweet counts or social indicators to moment cards
 * 🚫 DO NOT imply tweets are related to specific plays
 */

import { useCallback, useEffect, useState } from "react";
import { fetchGameStory } from "@/lib/api/sportsAdmin";
import type { GameStoryResponse, StoryMoment, StoryPlay, MomentBoxScore, MomentPlayerStat } from "@/lib/api/sportsAdmin/storyTypes";
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

function formatPlayerStats(player: MomentPlayerStat): string {
  const parts: string[] = [];
  // Basketball stats
  if (player.pts != null && player.pts > 0) parts.push(`${player.pts} pts`);
  if (player.reb != null && player.reb > 0) parts.push(`${player.reb} reb`);
  if (player.ast != null && player.ast > 0) parts.push(`${player.ast} ast`);
  if (player["3pm"] != null && player["3pm"] > 0) parts.push(`${player["3pm"]} 3pm`);
  // Hockey stats
  if (player.goals != null && player.goals > 0) parts.push(`${player.goals} G`);
  if (player.assists != null && player.assists > 0) parts.push(`${player.assists} A`);
  if (player.sog != null && player.sog > 0) parts.push(`${player.sog} SOG`);
  return parts.join(", ");
}

function MiniBoxScore({ boxScore }: { boxScore: MomentBoxScore }) {
  const hasPlayers = boxScore.home.players.length > 0 || boxScore.away.players.length > 0;

  return (
    <div className={styles.miniBoxScore}>
      <div className={styles.miniBoxScoreTeams}>
        <div className={styles.miniBoxScoreTeam}>
          <div className={styles.miniBoxScoreHeader}>
            <span className={styles.miniBoxScoreTeamName}>{boxScore.away.team}</span>
            <span className={styles.miniBoxScoreScore}>{boxScore.away.score}</span>
          </div>
          {hasPlayers && boxScore.away.players.slice(0, 3).map((player, i) => (
            <div key={i} className={styles.miniBoxScorePlayer}>
              <span className={styles.miniBoxScorePlayerName}>{player.name}</span>
              <span className={styles.miniBoxScorePlayerStats}>{formatPlayerStats(player)}</span>
            </div>
          ))}
          {boxScore.away.goalie && (
            <div className={styles.miniBoxScorePlayer}>
              <span className={styles.miniBoxScorePlayerName}>{boxScore.away.goalie.name}</span>
              <span className={styles.miniBoxScorePlayerStats}>
                {boxScore.away.goalie.saves} SV, {boxScore.away.goalie.ga} GA
              </span>
            </div>
          )}
        </div>
        <div className={styles.miniBoxScoreTeam}>
          <div className={styles.miniBoxScoreHeader}>
            <span className={styles.miniBoxScoreTeamName}>{boxScore.home.team}</span>
            <span className={styles.miniBoxScoreScore}>{boxScore.home.score}</span>
          </div>
          {hasPlayers && boxScore.home.players.slice(0, 3).map((player, i) => (
            <div key={i} className={styles.miniBoxScorePlayer}>
              <span className={styles.miniBoxScorePlayerName}>{player.name}</span>
              <span className={styles.miniBoxScorePlayerStats}>{formatPlayerStats(player)}</span>
            </div>
          ))}
          {boxScore.home.goalie && (
            <div className={styles.miniBoxScorePlayer}>
              <span className={styles.miniBoxScorePlayerName}>{boxScore.home.goalie.name}</span>
              <span className={styles.miniBoxScorePlayerStats}>
                {boxScore.home.goalie.saves} SV, {boxScore.home.goalie.ga} GA
              </span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

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

      {moment.cumulativeBoxScore && (
        <MiniBoxScore boxScore={moment.cumulativeBoxScore} />
      )}

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
      setError(err instanceof Error ? err.message : "Failed to load game flow");
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
    <CollapsibleSection title="Game Flow" defaultOpen={true}>
      {loading && <div className={styles.subtle}>Loading game flow...</div>}

      {error && <div className={styles.storyError}>Error: {error}</div>}

      {!loading && !error && !story && (
        <div className={styles.subtle}>No game flow found.</div>
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
