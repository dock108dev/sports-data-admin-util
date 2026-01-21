/**
 * API client for Chapters-First Story Generation.
 * 
 * ISSUE 14: Wire GameStory Output to Admin UI
 */

import type { GameStoryResponse, StoryStateResponse } from './types';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

/**
 * Fetch game story (chapters + summaries + compact story).
 */
export async function fetchGameStory(
  gameId: number,
  includeDebug: boolean = false
): Promise<GameStoryResponse> {
  const url = new URL(`${API_BASE}/api/admin/sports/games/${gameId}/story`);
  if (includeDebug) {
    url.searchParams.set('include_debug', 'true');
  }
  
  const response = await fetch(url.toString());
  
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
  const response = await fetch(
    `${API_BASE}/api/admin/sports/games/${gameId}/story-state?chapter=${chapterIndex}`
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
  const response = await fetch(
    `${API_BASE}/api/admin/sports/games/${gameId}/story/regenerate-chapters`,
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
): Promise<{ success: boolean; message: string; story?: GameStoryResponse }> {
  const response = await fetch(
    `${API_BASE}/api/admin/sports/games/${gameId}/story/regenerate-summaries`,
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
 * Regenerate compact story for a game.
 */
export async function regenerateCompactStory(
  gameId: number,
  force: boolean = false
): Promise<{ success: boolean; message: string; story?: GameStoryResponse }> {
  const response = await fetch(
    `${API_BASE}/api/admin/sports/games/${gameId}/story/regenerate-compact`,
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
 * Regenerate everything (chapters → summaries → compact story).
 */
export async function regenerateAll(
  gameId: number,
  force: boolean = false
): Promise<{ success: boolean; message: string; story?: GameStoryResponse }> {
  const response = await fetch(
    `${API_BASE}/api/admin/sports/games/${gameId}/story/regenerate-all`,
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
