"use client";

import { useState } from "react";
import type { NarrativeBlock, SocialPostsByPhase } from "@/lib/api/sportsAdmin/gameFlowTypes";
import { CollapsedGameFlow } from "./CollapsedGameFlow";
import { ExpandableSocialSections } from "./ExpandableSocialSections";
import styles from "./GameFlowView.module.css";

/**
 * Game Flow View
 *
 * Combines collapsed game flow with expandable social sections.
 *
 * Architecture:
 * 1. COLLAPSED VIEW (primary): Narrative blocks + embedded tweets
 *    - Self-sufficient, complete story
 *    - 20-60 second read time
 *    - Works identically with or without social data
 *
 * 2. EXPANDABLE SECTIONS (secondary): Optional social context
 *    - Clearly separated from collapsed view
 *    - All sections collapsed by default
 *    - Expansion is explicit user choice
 *
 * Visual hierarchy:
 * - Collapsed flow is visually primary
 * - Social sections are visually secondary
 * - No UI elements imply tweets explain plays
 *
 * Removing all social data must NOT change layout structure.
 */

interface GameFlowViewProps {
  /** Narrative blocks for collapsed view */
  blocks: NarrativeBlock[];
  /** Social posts for expandable sections */
  socialPosts?: SocialPostsByPhase;
  /** League code for segment labeling */
  leagueCode: string;
  /** Home team name */
  homeTeam?: string;
  /** Away team name */
  awayTeam?: string;
}

export function GameFlowView({
  blocks,
  socialPosts,
  leagueCode,
  homeTeam,
  awayTeam,
}: GameFlowViewProps) {
  const [showDebug, setShowDebug] = useState(false);

  // Calculate social stats for summary
  const hasSocialPosts = socialPosts && (
    socialPosts.pregame.length > 0 ||
    socialPosts.postgame.length > 0 ||
    Object.values(socialPosts.inGame).some((posts) => posts.length > 0)
  );

  return (
    <div className={styles.container}>
      {/* Debug toggle */}
      <div className={styles.header}>
        <label className={styles.debugToggle}>
          <input
            type="checkbox"
            checked={showDebug}
            onChange={(e) => setShowDebug(e.target.checked)}
          />
          Debug
        </label>
      </div>

      {/* PRIMARY: Collapsed game flow */}
      <div className={styles.primarySection}>
        <CollapsedGameFlow
          blocks={blocks}
          homeTeam={homeTeam}
          awayTeam={awayTeam}
          showDebug={showDebug}
        />
      </div>

      {/* SECONDARY: Expandable social sections */}
      {hasSocialPosts && socialPosts && (
        <div className={styles.secondarySection}>
          <ExpandableSocialSections
            socialPosts={socialPosts}
            leagueCode={leagueCode}
          />
        </div>
      )}
    </div>
  );
}

export default GameFlowView;
