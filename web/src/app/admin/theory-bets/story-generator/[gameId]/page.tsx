"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import type { GameStoryResponse } from "@/lib/api/sportsAdmin/types";
import styles from "./story-generator.module.css";

/**
 * Story Generator — Game Story Page
 *
 * STORY-CENTRIC UI (Breaking Change)
 *
 * PRIMARY VIEW: Compact Game Story
 * - The full story text is the default view
 * - This is what users see first
 *
 * DEBUG VIEW: Chapters & Technical Details
 * - Hidden by default behind a toggle
 * - Shows chapters, plays, reason codes, etc.
 */
export default function StoryGeneratorPage() {
  const params = useParams();
  const router = useRouter();
  const gameId = parseInt(params.gameId as string);

  const [story, setStory] = useState<GameStoryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [regenerating, setRegenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showDebugView, setShowDebugView] = useState(false);
  const [expandedChapters, setExpandedChapters] = useState<Set<string>>(new Set());

  const toggleChapter = (chapterId: string) => {
    const newExpanded = new Set(expandedChapters);
    if (newExpanded.has(chapterId)) {
      newExpanded.delete(chapterId);
    } else {
      newExpanded.add(chapterId);
    }
    setExpandedChapters(newExpanded);
  };

  useEffect(() => {
    loadStory();
  }, [gameId]);

  const loadStory = async () => {
    setLoading(true);
    setError(null);

    try {
      const { fetchGameStory } = await import("@/lib/api/sportsAdmin");
      const data = await fetchGameStory(gameId, false);
      setStory(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load story");
    } finally {
      setLoading(false);
    }
  };

  const handleRegenerateStory = async () => {
    if (!confirm("Regenerate the entire story? This will rebuild chapters, summaries, and the compact story.")) {
      return;
    }

    setRegenerating(true);

    try {
      // Full regeneration pipeline: chapters -> summaries -> titles -> compact story
      const { regenerateChapters, regenerateSummaries, regenerateTitles, regenerateCompactStory } = await import("@/lib/api/sportsAdmin");

      // Step 1: Regenerate chapters
      let result = await regenerateChapters(gameId, true, false);
      if (!result.success) {
        throw new Error(`Chapter generation failed: ${result.message}`);
      }

      // Step 2: Regenerate summaries
      result = await regenerateSummaries(gameId, true);
      if (!result.success) {
        throw new Error(`Summary generation failed: ${result.message}`);
      }

      // Step 3: Regenerate titles
      result = await regenerateTitles(gameId, true);
      if (!result.success) {
        throw new Error(`Title generation failed: ${result.message}`);
      }

      // Step 4: Regenerate compact story
      result = await regenerateCompactStory(gameId, true);
      if (!result.success) {
        throw new Error(`Compact story generation failed: ${result.message}`);
      }

      // Update UI with final result
      if (result.story) {
        setStory(result.story);
      }

    } catch (err) {
      alert(`Failed to regenerate story: ${err instanceof Error ? err.message : "Unknown error"}`);
    } finally {
      setRegenerating(false);
    }
  };

  if (loading) {
    return (
      <div className={styles.container}>
        <div className={styles.loading}>Loading story...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className={styles.container}>
        <div className={styles.error}>Error: {error}</div>
      </div>
    );
  }

  if (!story) {
    return (
      <div className={styles.container}>
        <div className={styles.error}>No story found</div>
      </div>
    );
  }

  const hasStory = story.has_compact_story && story.compact_story;

  return (
    <div className={styles.container}>
      {/* Header */}
      <div className={styles.header}>
        <div className={styles.headerTop}>
          <button
            onClick={() => router.push("/admin/theory-bets/story-generator")}
            className={styles.backButton}
          >
            Back to Games
          </button>
        </div>
        <h1>Game {gameId}</h1>
        <div className={styles.headerMeta}>
          <span className={styles.sport}>{story.sport}</span>
          {story.reading_time_estimate_minutes && (
            <span className={styles.readingTime}>
              {story.reading_time_estimate_minutes.toFixed(1)} min read
            </span>
          )}
        </div>
      </div>

      {/* Primary Action */}
      <div className={styles.actions}>
        <button
          onClick={handleRegenerateStory}
          className={styles.btnPrimary}
          disabled={regenerating}
        >
          {regenerating ? "Regenerating..." : "Regenerate Story"}
        </button>
        <label className={styles.debugToggle}>
          <input
            type="checkbox"
            checked={showDebugView}
            onChange={(e) => setShowDebugView(e.target.checked)}
          />
          Show Debug Details
        </label>
      </div>

      {/* PRIMARY VIEW: Compact Story */}
      <div className={styles.storyPanel}>
        {hasStory ? (
          <div className={styles.storyContent}>
            {story.compact_story!.split('\n\n').map((paragraph, i) => (
              <p key={i}>{paragraph}</p>
            ))}
          </div>
        ) : (
          <div className={styles.noStory}>
            <p>No story generated yet.</p>
            <p className={styles.noStoryHint}>
              Click "Regenerate Story" to generate the full game narrative.
            </p>
          </div>
        )}
      </div>

      {/* DEBUG VIEW: Chapters (hidden by default) */}
      {showDebugView && (
        <div className={styles.debugSection}>
          <h2 className={styles.debugSectionTitle}>Debug: Chapters ({story.chapter_count})</h2>

          {/* Status indicators */}
          <div className={styles.statusRow}>
            <span className={story.chapter_count > 0 ? styles.statusOk : styles.statusMissing}>
              Chapters: {story.chapter_count > 0 ? story.chapter_count : "None"}
            </span>
            <span className={story.has_summaries ? styles.statusOk : styles.statusMissing}>
              Summaries: {story.has_summaries ? "Yes" : "No"}
            </span>
            <span className={story.has_compact_story ? styles.statusOk : styles.statusMissing}>
              Compact Story: {story.has_compact_story ? "Yes" : "No"}
            </span>
          </div>

          {/* Chapters list */}
          <div className={styles.chaptersList}>
            {story.chapters.map((chapter, idx) => {
              const isExpanded = expandedChapters.has(chapter.chapter_id);

              return (
                <div key={chapter.chapter_id} className={styles.chapterCard}>
                  <div
                    className={styles.chapterHeader}
                    onClick={() => toggleChapter(chapter.chapter_id)}
                  >
                    <div className={styles.chapterHeaderLeft}>
                      <span className={styles.chapterToggle}>
                        {isExpanded ? "v" : ">"}
                      </span>
                      <span className={styles.chapterIndex}>Ch {idx}</span>
                      {chapter.chapter_title && (
                        <span className={styles.chapterTitle}>{chapter.chapter_title}</span>
                      )}
                    </div>

                    <div className={styles.chapterHeaderRight}>
                      <span className={styles.playCount}>{chapter.play_count} plays</span>
                      {chapter.period && <span className={styles.period}>Q{chapter.period}</span>}
                      <span className={styles.reasonCodes}>
                        {chapter.reason_codes.join(", ")}
                      </span>
                    </div>
                  </div>

                  {chapter.chapter_summary && (
                    <div className={styles.chapterSummary}>
                      {chapter.chapter_summary}
                    </div>
                  )}

                  {isExpanded && (
                    <div className={styles.chapterExpanded}>
                      <div className={styles.metadata}>
                        <div className={styles.metadataRow}>
                          <span className={styles.label}>Play Range:</span>
                          <span>{chapter.play_start_idx} - {chapter.play_end_idx}</span>
                        </div>

                        {chapter.time_range && (
                          <div className={styles.metadataRow}>
                            <span className={styles.label}>Time Range:</span>
                            <span>{chapter.time_range.start} - {chapter.time_range.end}</span>
                          </div>
                        )}

                        <div className={styles.metadataRow}>
                          <span className={styles.label}>Reason Codes:</span>
                          <span>{chapter.reason_codes.join(", ")}</span>
                        </div>
                      </div>

                      <div className={styles.playsSection}>
                        <h4>Plays ({chapter.plays.length})</h4>
                        <div className={styles.playsList}>
                          {chapter.plays.map((play, playIdx) => (
                            <div key={playIdx} className={styles.playEntry}>
                              <span className={styles.playIndex}>{play.play_index}</span>
                              <span className={styles.playDescription}>{play.description}</span>
                              {play.game_clock && (
                                <span className={styles.playClock}>{play.game_clock}</span>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
