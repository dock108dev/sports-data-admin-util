"use client";

/**
 * Social Posts Section
 *
 * PHASE 5 CONTRACT COMPLIANCE
 * ===========================
 * This component displays social posts in a SEPARATE, OPTIONAL section.
 *
 * Critical rules:
 * - Posts are NEVER linked to specific plays or moments
 * - Posts are ordered by time only, not by game events
 * - No "related plays" or similar language
 * - No tweet count badges tied to plays/moments
 * - No styling implying tweets explain or verify plays
 *
 * Tweets are REACTION, not EVIDENCE.
 *
 * 🚫 DO NOT add affordances that imply tweets explain plays
 * 🚫 DO NOT add links between tweets and specific game events
 * 🚫 DO NOT add "X tweets about this play" indicators
 */

import { useMemo, useState } from "react";
import type { AdminGameDetail } from "@/lib/api/sportsAdmin";
import { TwitterEmbed } from "@/components/social/TwitterEmbed";
import { CollapsibleSection } from "./CollapsibleSection";
import styles from "./styles.module.css";

const POSTS_PER_PAGE = 10;

export function SocialPostsSection({ posts }: { posts: AdminGameDetail["socialPosts"] }) {
  const [page, setPage] = useState(0);

  const filteredPosts = useMemo(() => {
    // IMPORTANT: Do NOT sort by timestamp here.
    // Trust backend order. See docs/NARRATIVE_TIME_MODEL.md
    // Timestamps do not imply causality or reading order.
    return [...(posts || [])].filter(
        (post) =>
          post.tweetText ||
          post.imageUrl ||
          post.videoUrl ||
          post.mediaType === "video" ||
          post.mediaType === "image"
      );
  }, [posts]);

  const totalPages = Math.ceil(filteredPosts.length / POSTS_PER_PAGE);
  const paginatedPosts = filteredPosts.slice(page * POSTS_PER_PAGE, (page + 1) * POSTS_PER_PAGE);

  return (
    <CollapsibleSection title="Social Posts" defaultOpen={false}>
      {filteredPosts.length === 0 ? (
        <div style={{ color: "#475569" }}>No social posts found for this game.</div>
      ) : (
        <>
          <div style={{ marginBottom: "1rem", color: "#64748b", fontSize: "0.9rem" }}>
            Showing {page * POSTS_PER_PAGE + 1}–
            {Math.min((page + 1) * POSTS_PER_PAGE, filteredPosts.length)} of {filteredPosts.length} posts
          </div>

          <div className={styles.socialPostsGrid}>
            {paginatedPosts.map((post) => (
              <div key={post.id} className={styles.socialPostCard}>
                <div className={styles.socialPostHeader}>
                  <span className={styles.badge}>{post.teamAbbreviation}</span>
                  {post.sourceHandle && (
                    <span className={styles.handleBadge}>@{post.sourceHandle}</span>
                  )}
                  {post.mediaType === "video" && <span className={styles.videoBadge}>🎥 Video</span>}
                  {post.mediaType === "image" && <span className={styles.imageBadge}>🖼️ Image</span>}
                </div>

                {post.mediaType === "video" ? (
                  <TwitterEmbed tweetUrl={post.postUrl} />
                ) : (
                  <>
                    {post.tweetText && <div className={styles.tweetText}>{post.tweetText}</div>}
                    {post.imageUrl && (
                      <img
                        src={post.imageUrl}
                        alt="Post media"
                        className={styles.socialPostImage}
                        loading="lazy"
                      />
                    )}
                    <a
                      href={post.postUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className={styles.socialPostLink}
                    >
                      View on X →
                    </a>
                  </>
                )}

                <div className={styles.socialPostMeta}>{new Date(post.postedAt).toLocaleString()}</div>
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
