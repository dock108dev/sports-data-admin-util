/**
 * API client for Chapters-First Story Generation.
 *
 * ISSUE 14: Wire GameStory Output to Admin UI
 */

import type { GameStoryResponse, StoryStateResponse } from './types';
import { getApiBase } from '../apiBase';

function getApiBaseUrl(): string {
  return getApiBase({
    serverInternalBaseEnv: process.env.SPORTS_API_INTERNAL_URL,
    serverPublicBaseEnv: process.env.NEXT_PUBLIC_SPORTS_API_URL,
    localhostPort: 8000,
  });
}

/**
 * Fetch game story (chapters + summaries + compact story).
 */
export async function fetchGameStory(
  gameId: number,
  includeDebug: boolean = false
): Promise<GameStoryResponse> {
  const apiBase = getApiBaseUrl();
  let url = `${apiBase}/api/admin/sports/games/${gameId}/story`;
  if (includeDebug) {
    url += '?include_debug=true';
  }

  const response = await fetch(url);

  if (!response.ok) {
    throw new Error(`Failed to fetch game story: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Fetch story state before a specific chapter.
 */
export async function fetchStoryState(
  gameId: number,
  chapterIndex: number
): Promise<StoryStateResponse> {
  const apiBase = getApiBaseUrl();
  const response = await fetch(
    `${apiBase}/api/admin/sports/games/${gameId}/story-state?chapter=${chapterIndex}`
  );

  if (!response.ok) {
    throw new Error(`Failed to fetch story state: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Regenerate chapters for a game.
 */
export async function regenerateChapters(
  gameId: number,
  force: boolean = false,
  debug: boolean = false
): Promise<{ success: boolean; message: string; story?: GameStoryResponse }> {
  const apiBase = getApiBaseUrl();
  const response = await fetch(
    `${apiBase}/api/admin/sports/games/${gameId}/story/regenerate-chapters`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ force, debug }),
    }
  );

  if (!response.ok) {
    throw new Error(`Failed to regenerate chapters: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Regenerate chapter summaries for a game.
 */
export async function regenerateSummaries(
  gameId: number,
  force: boolean = false
): Promise<{ success: boolean; message: string; story?: GameStoryResponse; errors?: string[] }> {
  const apiBase = getApiBaseUrl();
  const response = await fetch(
    `${apiBase}/api/admin/sports/games/${gameId}/story/regenerate-summaries`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ force, debug: false }),
    }
  );

  if (!response.ok) {
    throw new Error(`Failed to regenerate summaries: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Regenerate chapter titles for a game (requires summaries to exist first).
 *
 * ISSUE 3.1: Titles derive from summaries only.
 */
export async function regenerateTitles(
  gameId: number,
  force: boolean = false
): Promise<{ success: boolean; message: string; story?: GameStoryResponse; errors?: string[] }> {
  const apiBase = getApiBaseUrl();
  const response = await fetch(
    `${apiBase}/api/admin/sports/games/${gameId}/story/regenerate-titles`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ force, debug: false }),
    }
  );

  if (!response.ok) {
    throw new Error(`Failed to regenerate titles: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Regenerate compact story for a game.
 */
export async function regenerateCompactStory(
  gameId: number,
  force: boolean = false
): Promise<{ success: boolean; message: string; story?: GameStoryResponse }> {
  const apiBase = getApiBaseUrl();
  const response = await fetch(
    `${apiBase}/api/admin/sports/games/${gameId}/story/regenerate-compact`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ force, debug: false }),
    }
  );

  if (!response.ok) {
    throw new Error(`Failed to regenerate compact story: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Regenerate everything (chapters -> summaries -> compact story).
 */
export async function regenerateAll(
  gameId: number,
  force: boolean = false
): Promise<{ success: boolean; message: string; story?: GameStoryResponse }> {
  const apiBase = getApiBaseUrl();
  const response = await fetch(
    `${apiBase}/api/admin/sports/games/${gameId}/story/regenerate-all`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ force, debug: false }),
    }
  );

  if (!response.ok) {
    throw new Error(`Failed to regenerate all: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Bulk generate stories for games in a date range (ASYNC - returns job ID).
 */
export async function bulkGenerateStoriesAsync(params: {
  start_date: string;
  end_date: string;
  leagues: string[];
  force: boolean;
}): Promise<{
  job_id: string;
  message: string;
  status_url: string;
}> {
  const apiBase = getApiBaseUrl();
  const response = await fetch(
    `${apiBase}/api/admin/sports/games/bulk-generate-async`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    }
  );

  if (!response.ok) {
    throw new Error(`Failed to start bulk generation: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Check status of a background bulk generation job.
 */
export async function getBulkGenerateStatus(jobId: string): Promise<{
  job_id: string;
  state: string;
  current?: number;
  total?: number;
  status?: string;
  successful?: number;
  failed?: number;
  cached?: number;
  result?: {
    success: boolean;
    message: string;
    total_games: number;
    successful: number;
    failed: number;
    cached: number;
    generated: number;
  };
}> {
  const apiBase = getApiBaseUrl();
  const response = await fetch(
    `${apiBase}/api/admin/sports/games/bulk-generate-status/${jobId}`
  );

  if (!response.ok) {
    throw new Error(`Failed to get job status: ${response.statusText}`);
  }

  return response.json();
}
