"use client";

import { useState } from "react";
import type { ChapterEntry } from "@/lib/api/sportsAdmin/types";
import { CollapsibleSection } from "./CollapsibleSection";
import styles from "./styles.module.css";

interface ChaptersSectionProps {
  chapters: ChapterEntry[];
  gameId: number;
}

/**
 * Displays game chapters (narrative segments).
 * 
 * ISSUE 13: Chapters-First Admin UI
 * 
 * Chapters partition the entire game timeline into coherent scenes.
 * Each chapter has reason codes explaining why the boundary exists.
 */
export function ChaptersSection({ chapters, gameId }: ChaptersSectionProps) {
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

  if (!chapters || chapters.length === 0) {
    return (
      <CollapsibleSection title="📖 Chapters" defaultOpen={true}>
        <div className={styles.emptyState}>
          <p>No chapters generated yet.</p>
        </div>
      </CollapsibleSection>
    );
  }

  return (
    <CollapsibleSection title={`📖 Chapters (${chapters.length})`} defaultOpen={true}>
      <div className={styles.chaptersContainer}>
        {/* Debug Toggle */}
        <div className={styles.debugToggle}>
          <label>
            <input
              type="checkbox"
              checked={showDebugView}
              onChange={(e) => setShowDebugView(e.target.checked)}
            />
            Show Debug Info
          </label>
        </div>

        {/* Chapters List */}
        <div className={styles.chaptersList}>
          {chapters.map((chapter, idx) => {
            const isExpanded = expandedChapters.has(chapter.chapter_id);
            
            return (
              <div key={chapter.chapter_id} className={styles.chapterCard}>
                {/* Chapter Header (Collapsed View) */}
                <div 
                  className={styles.chapterHeader}
                  onClick={() => toggleChapter(chapter.chapter_id)}
                  style={{ cursor: 'pointer' }}
                >
                  <div className={styles.chapterHeaderLeft}>
                    <span className={styles.chapterIndex}>
                      {isExpanded ? "▼" : "▶"} Chapter {idx}
                    </span>
                    {chapter.chapter_title && (
                      <span className={styles.chapterTitle}>
                        {chapter.chapter_title}
                      </span>
                    )}
                  </div>
                  
                  <div className={styles.chapterHeaderRight}>
                    <span className={styles.playCount}>
                      {chapter.play_count} plays
                    </span>
                    {chapter.period && (
                      <span className={styles.period}>
                        Q{chapter.period}
                      </span>
                    )}
                    <span className={styles.reasonCodes}>
                      {chapter.reason_codes.map(code => getReasonIcon(code)).join(" ")}
                    </span>
                  </div>
                </div>

                {/* Chapter Summary (Always Visible) */}
                {chapter.chapter_summary && (
                  <div className={styles.chapterSummary}>
                    {chapter.chapter_summary}
                  </div>
                )}

                {/* Expanded View */}
                {isExpanded && (
                  <div className={styles.chapterExpanded}>
                    {/* Metadata */}
                    <div className={styles.chapterMetadata}>
                      <div className={styles.metadataRow}>
                        <span className={styles.metadataLabel}>Play Range:</span>
                        <span>{chapter.play_start_idx} - {chapter.play_end_idx}</span>
                      </div>
                      
                      {chapter.time_range && (
                        <div className={styles.metadataRow}>
                          <span className={styles.metadataLabel}>Time Range:</span>
                          <span>{chapter.time_range.start} - {chapter.time_range.end}</span>
                        </div>
                      )}
                      
                      <div className={styles.metadataRow}>
                        <span className={styles.metadataLabel}>Reason Codes:</span>
                        <span>
                          {chapter.reason_codes.map((code, i) => (
                            <span key={i} className={styles.reasonBadge}>
                              {getReasonIcon(code)} {code}
                            </span>
                          ))}
                        </span>
                      </div>
                    </div>

                    {/* Debug Info */}
                    {showDebugView && (
                      <div className={styles.debugInfo}>
                        <h4>Debug Info</h4>
                        <pre>{JSON.stringify({
                          chapter_id: chapter.chapter_id,
                          play_start_idx: chapter.play_start_idx,
                          play_end_idx: chapter.play_end_idx,
                          reason_codes: chapter.reason_codes,
                        }, null, 2)}</pre>
                      </div>
                    )}

                    {/* Plays */}
                    <div className={styles.chapterPlays}>
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
    </CollapsibleSection>
  );
}
