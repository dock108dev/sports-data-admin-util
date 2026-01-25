"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import type { GameStoryResponse, PipelineDebugResponse } from "@/lib/api/sportsAdmin/types";
import styles from "./story-generator.module.css";

type ViewMode = "story" | "pipeline";

/**
 * Story Generator — Game Story Page
 *
 * Two views:
 * 1. STORY VIEW: The final rendered story
 * 2. PIPELINE VIEW: Shows data transformation from PBP → OpenAI Prompt → Story
 */
export default function StoryGeneratorPage() {
  const params = useParams();
  const router = useRouter();
  const gameId = parseInt(params.gameId as string);

  const [story, setStory] = useState<GameStoryResponse | null>(null);
  const [pipeline, setPipeline] = useState<PipelineDebugResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingPipeline, setLoadingPipeline] = useState(false);
  const [regenerating, setRegenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<ViewMode>("story");
  const [expandedSections, setExpandedSections] = useState<Set<string>>(new Set());

  const toggleSection = (sectionId: string) => {
    const newExpanded = new Set(expandedSections);
    if (newExpanded.has(sectionId)) {
      newExpanded.delete(sectionId);
    } else {
      newExpanded.add(sectionId);
    }
    setExpandedSections(newExpanded);
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

  const loadPipeline = async () => {
    if (pipeline) return; // Already loaded

    setLoadingPipeline(true);
    try {
      const { fetchPipelineDebug } = await import("@/lib/api/sportsAdmin/chapters");
      const data = await fetchPipelineDebug(gameId);
      setPipeline(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load pipeline");
    } finally {
      setLoadingPipeline(false);
    }
  };

  const handleViewModeChange = async (mode: ViewMode) => {
    setViewMode(mode);
    if (mode === "pipeline") {
      await loadPipeline();
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
            Back
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

      {/* View Mode Tabs */}
      <div className={styles.viewTabs}>
        <button
          className={`${styles.viewTab} ${viewMode === "story" ? styles.viewTabActive : ""}`}
          onClick={() => handleViewModeChange("story")}
        >
          Story
        </button>
        <button
          className={`${styles.viewTab} ${viewMode === "pipeline" ? styles.viewTabActive : ""}`}
          onClick={() => handleViewModeChange("pipeline")}
        >
          Pipeline (PBP → Prompt → Story)
        </button>
      </div>

      {/* STORY VIEW */}
      {viewMode === "story" && (
        <>
          <div className={styles.actions}>
            <button
              onClick={handleRegenerateStory}
              className={styles.btnPrimary}
              disabled={regenerating}
            >
              {regenerating ? "Regenerating..." : "Regenerate Story"}
            </button>
          </div>

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
                  Click &ldquo;Regenerate Story&rdquo; to generate the full game narrative.
                </p>
              </div>
            )}
          </div>
        </>
      )}

      {/* PIPELINE VIEW */}
      {viewMode === "pipeline" && (
        <div className={styles.pipelineView}>
          {loadingPipeline ? (
            <div className={styles.loading}>Loading pipeline data...</div>
          ) : pipeline ? (
            <>
              {/* Pipeline Stages Overview */}
              <div className={styles.pipelineStages}>
                {pipeline.pipeline_stages.map((stage, idx) => (
                  <div key={idx} className={styles.pipelineStage}>
                    <div className={styles.stageName}>{stage.stage_name}</div>
                    <div className={styles.stageDescription}>{stage.description}</div>
                    {stage.input_count !== null && (
                      <div className={styles.stageCounts}>
                        {stage.input_count} → {stage.output_count}
                      </div>
                    )}
                  </div>
                ))}
              </div>

              {/* Stage 1: Raw PBP Sample */}
              <div
                className={styles.pipelineSection}
                onClick={() => toggleSection("pbp")}
              >
                <h3 className={styles.pipelineSectionTitle}>
                  <span>{expandedSections.has("pbp") ? "▼" : "▶"}</span>
                  1. Raw PBP Data ({pipeline.total_plays} plays, showing first 15)
                </h3>
                {expandedSections.has("pbp") && (
                  <div className={styles.pipelineSectionContent}>
                    <pre className={styles.codeBlock}>
                      {JSON.stringify(pipeline.raw_pbp_sample, null, 2)}
                    </pre>
                  </div>
                )}
              </div>

              {/* Stage 2: Chapters */}
              <div
                className={styles.pipelineSection}
                onClick={() => toggleSection("chapters")}
              >
                <h3 className={styles.pipelineSectionTitle}>
                  <span>{expandedSections.has("chapters") ? "▼" : "▶"}</span>
                  2. Chapters ({pipeline.chapter_count} chapters)
                </h3>
                {expandedSections.has("chapters") && (
                  <div className={styles.pipelineSectionContent}>
                    {pipeline.chapters_summary.map((ch) => (
                      <div key={ch.chapter_id} className={styles.chapterSummaryCard}>
                        <div className={styles.chapterSummaryHeader}>
                          <strong>Ch {ch.index}</strong> (Q{ch.period}) - Plays {ch.play_range}
                        </div>
                        <div className={styles.chapterSummaryReasons}>
                          Reasons: {ch.reason_codes.join(", ")}
                        </div>
                        <div className={styles.chapterSamplePlays}>
                          {ch.sample_plays.map((play, i) => (
                            <div key={i} className={styles.samplePlay}>
                              [{play.score}] {play.description}
                            </div>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Stage 3: Sections */}
              <div
                className={styles.pipelineSection}
                onClick={() => toggleSection("sections")}
              >
                <h3 className={styles.pipelineSectionTitle}>
                  <span>{expandedSections.has("sections") ? "▼" : "▶"}</span>
                  3. Sections ({pipeline.section_count} sections)
                </h3>
                {expandedSections.has("sections") && (
                  <div className={styles.pipelineSectionContent}>
                    {pipeline.sections_summary.map((sec) => (
                      <div key={sec.index} className={styles.sectionSummaryCard}>
                        <div className={styles.sectionBeatType}>{sec.beat_type}</div>
                        <div className={styles.sectionHeader}>{sec.header}</div>
                        <div className={styles.sectionScore}>
                          Score: {sec.start_score.home}-{sec.start_score.away} →{" "}
                          {sec.end_score.home}-{sec.end_score.away}
                        </div>
                        <div className={styles.sectionChapters}>
                          Chapters: {sec.chapters_included.join(", ")}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Stage 4: OpenAI Prompt */}
              <div
                className={styles.pipelineSection}
                onClick={() => toggleSection("prompt")}
              >
                <h3 className={styles.pipelineSectionTitle}>
                  <span>{expandedSections.has("prompt") ? "▼" : "▶"}</span>
                  4. OpenAI Prompt (Target: {pipeline.target_word_count} words)
                </h3>
                {expandedSections.has("prompt") && (
                  <div className={styles.pipelineSectionContent}>
                    {pipeline.openai_prompt ? (
                      <pre className={styles.promptBlock}>
                        {pipeline.openai_prompt}
                      </pre>
                    ) : (
                      <p className={styles.noData}>No prompt data available</p>
                    )}
                  </div>
                )}
              </div>

              {/* Stage 5: AI Response */}
              <div
                className={styles.pipelineSection}
                onClick={() => toggleSection("response")}
              >
                <h3 className={styles.pipelineSectionTitle}>
                  <span>{expandedSections.has("response") ? "▼" : "▶"}</span>
                  5. AI Response (Raw JSON)
                </h3>
                {expandedSections.has("response") && (
                  <div className={styles.pipelineSectionContent}>
                    {pipeline.ai_raw_response ? (
                      <pre className={styles.codeBlock}>
                        {pipeline.ai_raw_response}
                      </pre>
                    ) : (
                      <p className={styles.noData}>No response data available</p>
                    )}
                  </div>
                )}
              </div>

              {/* Stage 6: Final Story */}
              <div
                className={styles.pipelineSection}
                onClick={() => toggleSection("story")}
              >
                <h3 className={styles.pipelineSectionTitle}>
                  <span>{expandedSections.has("story") ? "▼" : "▶"}</span>
                  6. Final Story ({pipeline.word_count} words)
                </h3>
                {expandedSections.has("story") && (
                  <div className={styles.pipelineSectionContent}>
                    {pipeline.compact_story ? (
                      <div className={styles.storyContent}>
                        {pipeline.compact_story.split('\n\n').map((p, i) => (
                          <p key={i}>{p}</p>
                        ))}
                      </div>
                    ) : (
                      <p className={styles.noData}>No story generated</p>
                    )}
                  </div>
                )}
              </div>
            </>
          ) : (
            <div className={styles.error}>Failed to load pipeline data</div>
          )}
        </div>
      )}
    </div>
  );
}
