"use client";

import { useState } from "react";
import type { CategorizedSocialPost, SocialPostsByPhase } from "@/lib/api/sportsAdmin/storyTypes";
import styles from "./ExpandableSocialSections.module.css";

/**
 * Expandable Social Sections
 *
 * PHASE 5 CONTRACT (Task 5.2)
 * ==========================
 * Provides optional depth through EXPLICIT user action.
 *
 * Structure:
 * - Pregame card: All pregame tweets, chronological
 * - In-game sections: Per quarter/half, remaining tweets
 * - Postgame card: All postgame tweets, chronological
 *
 * Expansion rules:
 * - NEVER reorders narrative blocks
 * - NEVER inserts content into collapsed flow
 * - Visually distinct and clearly secondary
 * - No implicit expansion
 * - No auto-scrolling into expanded content
 *
 * Social content feels OPTIONAL, not required.
 */

interface ExpandableSocialSectionsProps {
  /** Social posts organized by phase */
  socialPosts: SocialPostsByPhase;
  /** League code for segment labeling */
  leagueCode: string;
}

/**
 * Get display label for a segment.
 */
function getSegmentLabel(segment: string, leagueCode: string): string {
  // NBA quarters
  if (segment === "q1") return "Q1";
  if (segment === "q2") return "Q2";
  if (segment === "q3") return "Q3";
  if (segment === "q4") return "Q4";

  // NCAAB halves
  if (segment === "first_half") return "1st Half";
  if (segment === "second_half") return "2nd Half";

  // NHL periods
  if (segment === "p1") return "1st Period";
  if (segment === "p2") return "2nd Period";
  if (segment === "p3") return "3rd Period";

  // Overtime
  if (segment === "ot" || segment === "ot1") return "Overtime";
  if (segment.startsWith("ot")) return `OT${segment.slice(2)}`;

  // Halftime/intermission
  if (segment === "halftime") return "Halftime";

  return segment;
}

/**
 * Get ordered segments based on league.
 */
function getSegmentOrder(leagueCode: string): string[] {
  if (leagueCode === "NCAAB") {
    return ["first_half", "halftime", "second_half", "ot"];
  }
  if (leagueCode === "NHL") {
    return ["p1", "p2", "p3", "ot"];
  }
  // Default: NBA
  return ["q1", "q2", "halftime", "q3", "q4", "ot1", "ot2", "ot3", "ot4"];
}

/**
 * Single social post card.
 */
function SocialPostCard({ post }: { post: CategorizedSocialPost }) {
  const timestamp = new Date(post.postedAt).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });

  return (
    <div className={styles.postCard}>
      <div className={styles.postHeader}>
        <span className={styles.postAuthor}>@{post.author}</span>
        <span className={styles.postTime}>{timestamp}</span>
        {post.hasMedia && <span className={styles.mediaBadge}>📷</span>}
      </div>
      <p className={styles.postText}>{post.text}</p>
      {post.postUrl && (
        <a
          href={post.postUrl}
          target="_blank"
          rel="noopener noreferrer"
          className={styles.postLink}
        >
          View on X →
        </a>
      )}
    </div>
  );
}

/**
 * Collapsible section wrapper.
 */
function CollapsibleCard({
  title,
  count,
  children,
  defaultOpen = false,
}: {
  title: string;
  count: number;
  children: React.ReactNode;
  defaultOpen?: boolean;
}) {
  const [isOpen, setIsOpen] = useState(defaultOpen);

  if (count === 0) {
    return null;
  }

  return (
    <div className={styles.collapsibleCard}>
      <button
        type="button"
        className={styles.collapsibleHeader}
        onClick={() => setIsOpen(!isOpen)}
        aria-expanded={isOpen}
      >
        <span className={styles.collapsibleTitle}>
          {title}
          <span className={styles.countBadge}>{count}</span>
        </span>
        <span className={styles.chevron}>{isOpen ? "▼" : "▶"}</span>
      </button>
      {isOpen && <div className={styles.collapsibleContent}>{children}</div>}
    </div>
  );
}

/**
 * Pregame tweets section.
 */
function PregameSection({ posts }: { posts: CategorizedSocialPost[] }) {
  if (posts.length === 0) {
    return null;
  }

  return (
    <CollapsibleCard title="Pregame" count={posts.length}>
      <div className={styles.postsGrid}>
        {posts.map((post) => (
          <SocialPostCard key={post.id} post={post} />
        ))}
      </div>
    </CollapsibleCard>
  );
}

/**
 * In-game tweets section, organized by segment.
 */
function InGameSections({
  postsBySegment,
  leagueCode,
}: {
  postsBySegment: Record<string, CategorizedSocialPost[]>;
  leagueCode: string;
}) {
  const segmentOrder = getSegmentOrder(leagueCode);

  // Get segments with posts, in order
  const segmentsWithPosts = segmentOrder.filter(
    (seg) => postsBySegment[seg] && postsBySegment[seg].length > 0
  );

  // Also include any segments not in the standard order
  const extraSegments = Object.keys(postsBySegment).filter(
    (seg) => !segmentOrder.includes(seg) && postsBySegment[seg].length > 0
  );

  const allSegments = [...segmentsWithPosts, ...extraSegments];

  if (allSegments.length === 0) {
    return null;
  }

  return (
    <div className={styles.inGameSections}>
      {allSegments.map((segment) => (
        <CollapsibleCard
          key={segment}
          title={getSegmentLabel(segment, leagueCode)}
          count={postsBySegment[segment].length}
        >
          <div className={styles.postsGrid}>
            {postsBySegment[segment].map((post) => (
              <SocialPostCard key={post.id} post={post} />
            ))}
          </div>
        </CollapsibleCard>
      ))}
    </div>
  );
}

/**
 * Postgame tweets section.
 */
function PostgameSection({ posts }: { posts: CategorizedSocialPost[] }) {
  if (posts.length === 0) {
    return null;
  }

  return (
    <CollapsibleCard title="Postgame" count={posts.length}>
      <div className={styles.postsGrid}>
        {posts.map((post) => (
          <SocialPostCard key={post.id} post={post} />
        ))}
      </div>
    </CollapsibleCard>
  );
}

/**
 * Main expandable social sections component.
 *
 * Displays social posts in organized, expandable sections.
 * All sections are collapsed by default - user must choose to expand.
 */
export function ExpandableSocialSections({
  socialPosts,
  leagueCode,
}: ExpandableSocialSectionsProps) {
  const totalPosts =
    socialPosts.pregame.length +
    socialPosts.postgame.length +
    Object.values(socialPosts.inGame).reduce((sum, posts) => sum + posts.length, 0);

  if (totalPosts === 0) {
    return null;
  }

  return (
    <div className={styles.container}>
      <div className={styles.sectionHeader}>
        <h3 className={styles.sectionTitle}>Social Context</h3>
        <span className={styles.sectionHint}>Optional · {totalPosts} posts</span>
      </div>

      <div className={styles.sectionsWrapper}>
        <PregameSection posts={socialPosts.pregame} />
        <InGameSections
          postsBySegment={socialPosts.inGame}
          leagueCode={leagueCode}
        />
        <PostgameSection posts={socialPosts.postgame} />
      </div>
    </div>
  );
}

export default ExpandableSocialSections;
