"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import type { GameStoryResponse, StoryStateResponse } from "@/lib/api/sportsAdmin/types";
import styles from "./story-generator.module.css";

/**
 * Story Generator — Game Overview Page
 * 
 * ISSUE 13: Admin UI for Chapters-First System
 * 
 * Single-game inspection for story generation pipeline.
 */
export default function StoryGeneratorPage() {
  const params = useParams();
  const gameId = parseInt(params.gameId as string);
  
  const [story, setStory] = useState<GameStoryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedChapter, setSelectedChapter] = useState<number | null>(null);
  const [storyState, setStoryState] = useState<StoryStateResponse | null>(null);
  const [expandedChapters, setExpandedChapters] = useState<Set<string>>(new Set());
  const [showDebugView, setShowDebugView] = useState(false);
  
  const toggleChapter = (chapterId: string) => {
    const newExpanded = new Set(expandedChapters);
    if (newExpanded.has(chapterId)) {
      newExpanded.delete(chapterId);
    } else {
      newExpanded.add(chapterId);
    }
    setExpandedChapters(newExpanded);
  };
  
  const getReasonIcon = (reason: string) => {
    switch (reason.toUpperCase()) {
      case "PERIOD_START":
        return "🏁";
      case "PERIOD_END":
        return "⏹️";
      case "TIMEOUT":
        return "⏸️";
      case "REVIEW":
        return "🔍";
      case "CRUNCH_START":
        return "🔥";
      case "RUN_START":
        return "📈";
      case "RUN_END_RESPONSE":
        return "↩️";
      case "OVERTIME_START":
        return "⏰";
      case "GAME_END":
        return "🏁";
      default:
        return "📍";
    }
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

  const loadStoryState = async (chapterIndex: number) => {
    try {
      const { fetchStoryState } = await import("@/lib/api/sportsAdmin");
      const data = await fetchStoryState(gameId, chapterIndex);
      setStoryState(data);
      setSelectedChapter(chapterIndex);
    } catch (err) {
      console.error("Failed to load story state:", err);
      setError(err instanceof Error ? err.message : "Failed to load story state");
    }
  };

  const handleRegenerateChapters = async () => {
    if (!confirm("Regenerate chapters? This will reset all summaries and titles.")) {
      return;
    }
    
    try {
      const { regenerateChapters } = await import("@/lib/api/sportsAdmin");
      const result = await regenerateChapters(gameId, true, false);
      
      if (result.success && result.story) {
        setStory(result.story);
        alert(result.message);
      } else {
        alert(`Failed: ${result.message}`);
      }
    } catch (err) {
      alert(`Failed to regenerate chapters: ${err instanceof Error ? err.message : "Unknown error"}`);
    }
  };

  const handleRegenerateSummaries = async () => {
    if (!confirm("Regenerate all chapter summaries?")) {
      return;
    }
    
    try {
      const { regenerateSummaries } = await import("@/lib/api/sportsAdmin");
      const result = await regenerateSummaries(gameId, true);
      
      if (result.success && result.story) {
        setStory(result.story);
        alert(result.message);
      } else {
        alert(`Failed: ${result.message}`);
      }
    } catch (err) {
      alert(`Failed to regenerate summaries: ${err instanceof Error ? err.message : "Unknown error"}`);
    }
  };

  const handleRegenerateCompactStory = async () => {
    if (!confirm("Regenerate compact story?")) {
      return;
    }
    
    try {
      const { regenerateCompactStory } = await import("@/lib/api/sportsAdmin");
      const result = await regenerateCompactStory(gameId, true);
      
      if (result.success && result.story) {
        setStory(result.story);
        alert(result.message);
      } else {
        alert(`Failed: ${result.message}`);
      }
    } catch (err) {
      alert(`Failed to regenerate compact story: ${err instanceof Error ? err.message : "Unknown error"}`);
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

  return (
    <div className={styles.container}>
      {/* Header */}
      <div className={styles.header}>
        <h1>Story Generator — Game {gameId}</h1>
        <div className={styles.headerMeta}>
          <span className={styles.sport}>{story.sport}</span>
          <span className={styles.chapterCount}>{story.chapter_count} chapters</span>
          {story.reading_time_estimate_minutes && (
            <span className={styles.readingTime}>
              ~{story.reading_time_estimate_minutes.toFixed(1)} min read
            </span>
          )}
        </div>
      </div>

      {/* Actions */}
      <div className={styles.actions}>
        <button onClick={handleRegenerateChapters} className={styles.btnSecondary}>
          Regenerate Chapters
        </button>
        <button onClick={handleRegenerateSummaries} className={styles.btnSecondary}>
          Regenerate Summaries
        </button>
        <button onClick={handleRegenerateCompactStory} className={styles.btnSecondary}>
          Regenerate Compact Story
        </button>
      </div>

      {/* Status */}
      <div className={styles.statusPanel}>
        <h2>Generation Status</h2>
        <div className={styles.statusGrid}>
          <div className={styles.statusItem}>
            <span className={styles.statusLabel}>Chapters:</span>
            <span className={story.chapter_count > 0 ? styles.statusOk : styles.statusMissing}>
              {story.chapter_count > 0 ? `✓ ${story.chapter_count}` : "✗ Not generated"}
            </span>
          </div>
          
          <div className={styles.statusItem}>
            <span className={styles.statusLabel}>Summaries:</span>
            <span className={story.has_summaries ? styles.statusOk : styles.statusMissing}>
              {story.has_summaries ? "✓ Generated" : "✗ Not generated"}
            </span>
          </div>
          
          <div className={styles.statusItem}>
            <span className={styles.statusLabel}>Compact Story:</span>
            <span className={story.has_compact_story ? styles.statusOk : styles.statusMissing}>
              {story.has_compact_story ? "✓ Generated" : "✗ Not generated"}
            </span>
          </div>
        </div>
      </div>

      {/* Compact Story */}
      {story.compact_story && (
        <div className={styles.compactStoryPanel}>
          <h2>Compact Game Story</h2>
          <div className={styles.compactStory}>
            {story.compact_story.split('\n\n').map((paragraph, i) => (
              <p key={i}>{paragraph}</p>
            ))}
          </div>
        </div>
      )}

      {/* Chapters */}
      <div className={styles.chaptersPanel}>
        <h2>Chapters ({story.chapter_count})</h2>
        <div className={styles.chaptersList}>
          {story.chapters.map((chapter, idx) => {
            const isExpanded = expandedChapters.has(chapter.chapter_id);
            
            return (
              <div key={chapter.chapter_id} className={styles.chapterCard}>
                {/* Collapsed View */}
                <div 
                  className={styles.chapterHeader}
                  onClick={() => toggleChapter(chapter.chapter_id)}
                >
                  <div className={styles.chapterHeaderLeft}>
                    <span className={styles.chapterToggle}>
                      {isExpanded ? "▼" : "▶"}
                    </span>
                    <span className={styles.chapterIndex}>Chapter {idx}</span>
                    {chapter.chapter_title && (
                      <span className={styles.chapterTitle}>{chapter.chapter_title}</span>
                    )}
                  </div>
                  
                  <div className={styles.chapterHeaderRight}>
                    <span className={styles.playCount}>{chapter.play_count} plays</span>
                    {chapter.period && <span className={styles.period}>Q{chapter.period}</span>}
                    <span className={styles.reasonCodes}>
                      {chapter.reason_codes.map(code => getReasonIcon(code)).join(" ")}
                    </span>
                  </div>
                </div>

                {/* Summary (Always Visible) */}
                {chapter.chapter_summary && (
                  <div className={styles.chapterSummary}>
                    {chapter.chapter_summary}
                  </div>
                )}

                {/* Expanded View */}
                {isExpanded && (
                  <div className={styles.chapterExpanded}>
                    {/* Metadata */}
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
                        <div className={styles.reasonCodesList}>
                          {chapter.reason_codes.map((code, i) => (
                            <span key={i} className={styles.reasonBadge}>
                              {getReasonIcon(code)} {code}
                            </span>
                          ))}
                        </div>
                      </div>
                    </div>

                    {/* Debug Info */}
                    {showDebugView && (
                      <div className={styles.debugPanel}>
                        <h4>Debug Info</h4>
                        <button 
                          onClick={() => loadStoryState(idx)}
                          className={styles.btnSmall}
                        >
                          Load Story State Before This Chapter
                        </button>
                        <pre className={styles.debugJson}>
                          {JSON.stringify({
                            chapter_id: chapter.chapter_id,
                            play_start_idx: chapter.play_start_idx,
                            play_end_idx: chapter.play_end_idx,
                            play_count: chapter.play_count,
                            reason_codes: chapter.reason_codes,
                          }, null, 2)}
                        </pre>
                      </div>
                    )}

                    {/* Plays */}
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

      {/* Story State Inspector (if loaded) */}
      {storyState && selectedChapter !== null && (
        <div className={styles.storyStatePanel}>
          <h2>Story State Before Chapter {selectedChapter}</h2>
          <div className={styles.storyStateContent}>
            <div className={styles.storyStateSection}>
              <h3>Players (Top {Object.keys(storyState.players).length})</h3>
              {Object.entries(storyState.players).map(([name, player]) => (
                <div key={name} className={styles.playerState}>
                  <span className={styles.playerName}>{name}</span>
                  <span className={styles.playerStats}>
                    {player.points_so_far} pts ({player.made_fg_so_far} FG, {player.made_3pt_so_far} 3PT)
                  </span>
                  {player.notable_actions_so_far.length > 0 && (
                    <span className={styles.notableActions}>
                      Notable: {player.notable_actions_so_far.join(", ")}
                    </span>
                  )}
                </div>
              ))}
            </div>

            <div className={styles.storyStateSection}>
              <h3>Momentum</h3>
              <span className={styles.momentum}>{storyState.momentum_hint}</span>
            </div>

            {storyState.theme_tags.length > 0 && (
              <div className={styles.storyStateSection}>
                <h3>Themes</h3>
                <div className={styles.themeTags}>
                  {storyState.theme_tags.map((tag, i) => (
                    <span key={i} className={styles.themeTag}>{tag}</span>
                  ))}
                </div>
              </div>
            )}

            <div className={styles.storyStateSection}>
              <h3>Constraints</h3>
              <div className={styles.constraints}>
                <div>✓ no_future_knowledge: {storyState.constraints.no_future_knowledge.toString()}</div>
                <div>✓ source: {storyState.constraints.source}</div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
