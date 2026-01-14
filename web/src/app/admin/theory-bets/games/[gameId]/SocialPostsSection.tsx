"use client";

import { useMemo, useState } from "react";
import type { AdminGameDetail } from "@/lib/api/sportsAdmin";
import { TwitterEmbed } from "@/components/social/TwitterEmbed";
import { CollapsibleSection } from "./CollapsibleSection";
import styles from "./styles.module.css";

const POSTS_PER_PAGE = 10;

export function SocialPostsSection({ posts }: { posts: AdminGameDetail["social_posts"] }) {
  const [page, setPage] = useState(0);

  const filteredPosts = useMemo(() => {
    // IMPORTANT: Do NOT sort by timestamp here.
    // Trust backend order. See docs/NARRATIVE_TIME_MODEL.md
    // Timestamps do not imply causality or reading order.
    return [...(posts || [])].filter(
      (post) =>
        post.tweet_text ||
        post.image_url ||
        post.video_url ||
        post.media_type === "video" ||
        post.media_type === "image"
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
                  <span className={styles.badge}>{post.team_abbreviation}</span>
                  {post.source_handle && (
                    <span className={styles.handleBadge}>@{post.source_handle}</span>
                  )}
                  {post.media_type === "video" && <span className={styles.videoBadge}>🎥 Video</span>}
                  {post.media_type === "image" && <span className={styles.imageBadge}>🖼️ Image</span>}
                </div>

                {post.media_type === "video" ? (
                  <TwitterEmbed tweetUrl={post.post_url} />
                ) : (
                  <>
                    {post.tweet_text && <div className={styles.tweetText}>{post.tweet_text}</div>}
                    {post.image_url && (
                      <img
                        src={post.image_url}
                        alt="Post media"
                        className={styles.socialPostImage}
                        loading="lazy"
                      />
                    )}
                    <a
                      href={post.post_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className={styles.socialPostLink}
                    >
                      View on X →
                    </a>
                  </>
                )}

                <div className={styles.socialPostMeta}>{new Date(post.posted_at).toLocaleString()}</div>
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
