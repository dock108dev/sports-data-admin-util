"use client";

import { useMemo } from "react";
import type { NarrativeBlock, EmbeddedTweet } from "@/lib/api/sportsAdmin/storyTypes";
import { validateBlocksPreRender, type GuardrailResult } from "@/lib/guardrails";
import styles from "./CollapsedGameFlow.module.css";

/**
 * Collapsed Game Flow
 *
 * PHASE 5 CONTRACT (Task 5.1)
 * ==========================
 * The collapsed view is the PRIMARY product - complete and self-sufficient.
 *
 * May contain ONLY:
 * - Narrative blocks (from Phase 1)
 * - Embedded tweets (from Phase 4)
 *
 * Must NOT contain:
 * - Pregame tweets
 * - Postgame tweets
 * - Bulk social lists
 * - Hidden expandable sections
 *
 * Rendering rules:
 * - Narrative blocks define vertical rhythm
 * - Embedded tweets interleaved, never dominating
 * - Removing all tweets produces SAME narrative layout
 * - Total read time: 20-60 seconds
 *
 * Tweets act as reaction beats, NOT narrative drivers.
 */

interface CollapsedGameFlowProps {
  /** Narrative blocks to display */
  blocks: NarrativeBlock[];
  /** Game ID for guardrail logging */
  gameId?: number;
  /** Home team name for score display */
  homeTeam?: string;
  /** Away team name for score display */
  awayTeam?: string;
  /** Whether to show debug information */
  showDebug?: boolean;
}

/**
 * Format semantic role for display.
 */
function formatRole(role: string): string {
  const roleLabels: Record<string, string> = {
    SETUP: "Opening",
    MOMENTUM_SHIFT: "Shift",
    RESPONSE: "Response",
    DECISION_POINT: "Decisive",
    RESOLUTION: "Final",
  };
  return roleLabels[role] || role;
}

/**
 * Get role badge color class.
 */
function getRoleBadgeClass(role: string): string {
  const roleColors: Record<string, string> = {
    SETUP: styles.roleSetup,
    MOMENTUM_SHIFT: styles.roleMomentum,
    RESPONSE: styles.roleResponse,
    DECISION_POINT: styles.roleDecision,
    RESOLUTION: styles.roleResolution,
  };
  return roleColors[role] || "";
}

/**
 * Embedded Tweet Display
 *
 * Renders a single embedded tweet inline with the narrative.
 * Styled to be visually secondary to the narrative text.
 */
function EmbeddedTweetCard({ tweet }: { tweet: EmbeddedTweet }) {
  return (
    <div className={styles.embeddedTweet}>
      <div className={styles.tweetMeta}>
        <span className={styles.tweetAuthor}>@{tweet.author}</span>
        {tweet.hasMedia && <span className={styles.mediaBadge}>📷</span>}
      </div>
      <p className={styles.tweetText}>{tweet.text}</p>
    </div>
  );
}

/**
 * Narrative Block Display
 *
 * Renders a single narrative block with its semantic role.
 * Optional embedded tweet displayed after the narrative.
 */
function BlockCard({
  block,
  homeTeam,
  awayTeam,
  showDebug,
}: {
  block: NarrativeBlock;
  homeTeam?: string;
  awayTeam?: string;
  showDebug?: boolean;
}) {
  const hasScoreChange =
    block.scoreBefore[0] !== block.scoreAfter[0] ||
    block.scoreBefore[1] !== block.scoreAfter[1];

  const formatScore = (score: number[]) => {
    if (score.length >= 2) {
      return `${score[0]}-${score[1]}`;
    }
    return "—";
  };

  return (
    <div className={styles.blockCard}>
      {/* Block header with role badge */}
      <div className={styles.blockHeader}>
        <span className={`${styles.roleBadge} ${getRoleBadgeClass(block.role)}`}>
          {formatRole(block.role)}
        </span>
        {hasScoreChange && (
          <span className={styles.scoreChange}>
            {formatScore(block.scoreBefore)} → {formatScore(block.scoreAfter)}
          </span>
        )}
        {block.periodStart !== block.periodEnd ? (
          <span className={styles.periodRange}>
            Q{block.periodStart}–Q{block.periodEnd}
          </span>
        ) : (
          <span className={styles.periodBadge}>Q{block.periodStart}</span>
        )}
      </div>

      {/* Narrative text - the primary content */}
      <p className={styles.narrative}>{block.narrative || "No narrative"}</p>

      {/* Embedded tweet - optional, visually secondary */}
      {block.embeddedTweet && (
        <EmbeddedTweetCard tweet={block.embeddedTweet} />
      )}

      {/* Debug info - only when enabled */}
      {showDebug && (
        <div className={styles.debugInfo}>
          <span>Block #{block.blockIndex}</span>
          <span>Moments: {block.momentIndices.join(", ")}</span>
          <span>Plays: {block.playIds.length}</span>
          <span>Key plays: {block.keyPlayIds.join(", ")}</span>
        </div>
      )}
    </div>
  );
}

/**
 * Main collapsed game flow component.
 *
 * Renders narrative blocks with optional embedded tweets.
 * This is the primary, self-sufficient view of the game story.
 */
export function CollapsedGameFlow({
  blocks,
  gameId,
  homeTeam,
  awayTeam,
  showDebug = false,
}: CollapsedGameFlowProps) {
  // Phase 6: Run guardrail validation on every render
  // This ensures violations are immediately visible during development
  const guardrailResult = useMemo(
    () => validateBlocksPreRender(blocks, gameId ?? null),
    [blocks, gameId]
  );

  // Empty state - no blocks
  if (!blocks || blocks.length === 0) {
    return (
      <div className={styles.emptyState}>
        No story blocks available
      </div>
    );
  }

  // Count embedded tweets for summary
  const embeddedTweetCount = blocks.filter((b) => b.embeddedTweet).length;

  // Calculate total word count
  const totalWords = blocks.reduce((sum, b) => {
    const narrativeWords = b.narrative?.split(/\s+/).length || 0;
    return sum + narrativeWords;
  }, 0);

  return (
    <div className={styles.container}>
      {/* Guardrail violation warning - visible in dev */}
      {!guardrailResult.passed && (
        <div className={styles.guardrailWarning}>
          <strong>Guardrail Violations:</strong>
          <ul>
            {guardrailResult.violations
              .filter((v) => v.severity === "error")
              .map((v, i) => (
                <li key={i}>{v.message}</li>
              ))}
          </ul>
        </div>
      )}

      {/* Summary line */}
      <div className={styles.summary}>
        {blocks.length} blocks · ~{totalWords} words
        {embeddedTweetCount > 0 && ` · ${embeddedTweetCount} embedded tweets`}
        {!guardrailResult.passed && " · ⚠️ VIOLATIONS"}
      </div>

      {/* Blocks list - vertical flow */}
      <div className={styles.blocksList}>
        {blocks.map((block) => (
          <BlockCard
            key={block.blockIndex}
            block={block}
            homeTeam={homeTeam}
            awayTeam={awayTeam}
            showDebug={showDebug}
          />
        ))}
      </div>
    </div>
  );
}

export default CollapsedGameFlow;
