"use client";

import { useState } from "react";
import type {
  StoryV2Output,
  PlayData,
} from "@/lib/api/sportsAdmin/storyV2Types";
import { StoryV2Viewer } from "./StoryV2Viewer";
import styles from "./storyV2.module.css";

/**
 * Story V2 Section
 *
 * Wrapper for displaying Story V2 on game detail pages.
 *
 * This component:
 * - Manages loading/error states
 * - Delegates all display to StoryV2Viewer
 * - Does NOT modify story data
 */

interface StoryV2SectionProps {
  /** Game ID for fetching story */
  gameId: number;
  /** Story V2 data (if already loaded) */
  story?: StoryV2Output | null;
  /** Plays data (if already loaded) */
  plays?: PlayData[] | null;
  /** Loading state */
  loading?: boolean;
  /** Error message */
  error?: string | null;
  /** Validation status */
  validationPassed?: boolean;
  /** Validation errors */
  validationErrors?: string[];
}

export function StoryV2Section({
  gameId,
  story,
  plays,
  loading = false,
  error = null,
  validationPassed = true,
  validationErrors = [],
}: StoryV2SectionProps) {
  // Loading state
  if (loading) {
    return (
      <div className={styles.emptyState}>
        Loading Story V2...
      </div>
    );
  }

  // Error state - show error, do not recover
  if (error) {
    return (
      <div className={styles.errorState}>
        <p>Failed to load Story V2</p>
        <ul>
          <li>{error}</li>
        </ul>
      </div>
    );
  }

  // No story - empty state (no filler prose)
  if (!story || !story.moments || story.moments.length === 0) {
    return (
      <div className={styles.emptyState}>
        No Story V2 generated
      </div>
    );
  }

  // Display story
  return (
    <StoryV2Viewer
      story={story}
      plays={plays || []}
      validationPassed={validationPassed}
      validationErrors={validationErrors}
    />
  );
}

export default StoryV2Section;
