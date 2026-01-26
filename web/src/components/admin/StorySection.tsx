"use client";

import { useState } from "react";
import type {
  StoryOutput,
  PlayData,
} from "@/lib/api/sportsAdmin/storyTypes";
import { StoryViewer } from "./StoryViewer";
import styles from "./story.module.css";

/**
 * Story Section
 *
 * Wrapper for displaying Story on game detail pages.
 *
 * This component:
 * - Manages loading/error states
 * - Delegates all display to StoryViewer
 * - Does NOT modify story data
 */

interface StorySectionProps {
  /** Game ID for fetching story */
  gameId: number;
  /** Story data (if already loaded) */
  story?: StoryOutput | null;
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

export function StorySection({
  gameId,
  story,
  plays,
  loading = false,
  error = null,
  validationPassed = true,
  validationErrors = [],
}: StorySectionProps) {
  // Loading state
  if (loading) {
    return (
      <div className={styles.emptyState}>
        Loading Story...
      </div>
    );
  }

  // Error state - show error, do not recover
  if (error) {
    return (
      <div className={styles.errorState}>
        <p>Failed to load Story</p>
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
        No Story generated
      </div>
    );
  }

  // Display story
  return (
    <StoryViewer
      story={story}
      plays={plays || []}
      validationPassed={validationPassed}
      validationErrors={validationErrors}
    />
  );
}

export default StorySection;
