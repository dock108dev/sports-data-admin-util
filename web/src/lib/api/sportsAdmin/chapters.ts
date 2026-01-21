/**
 * API client for Chapters-First Story Generation.
 * 
 * ISSUE 13: Admin UI for Chapters-First System
 */

import type { GameStoryResponse, StoryStateResponse } from './types';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

/**
 * Fetch game story (chapters + summaries + compact story).
 */
export async function fetchGameStory(gameId: number): Promise<GameStoryResponse> {
  const response = await fetch(`${API_BASE}/api/sports-admin/games/${gameId}/story`);
  
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
    `${API_BASE}/api/sports-admin/games/${gameId}/story-state?chapter=${chapterIndex}`
  );
  
  if (!response.ok) {
    throw new Error(`Failed to fetch story state: ${response.statusText}`);
  }
  
  return response.json();
}

/**
 * Regenerate chapters for a game.
 */
export async function regenerateChapters(gameId: number): Promise<GameStoryResponse> {
  const response = await fetch(
    `${API_BASE}/api/sports-admin/games/${gameId}/story/regenerate-chapters`,
    { method: 'POST' }
  );
  
  if (!response.ok) {
    throw new Error(`Failed to regenerate chapters: ${response.statusText}`);
  }
  
  return response.json();
}

/**
 * Regenerate chapter summaries for a game.
 */
export async function regenerateSummaries(gameId: number): Promise<GameStoryResponse> {
  const response = await fetch(
    `${API_BASE}/api/sports-admin/games/${gameId}/story/regenerate-summaries`,
    { method: 'POST' }
  );
  
  if (!response.ok) {
    throw new Error(`Failed to regenerate summaries: ${response.statusText}`);
  }
  
  return response.json();
}

/**
 * Regenerate compact story for a game.
 */
export async function regenerateCompactStory(gameId: number): Promise<GameStoryResponse> {
  const response = await fetch(
    `${API_BASE}/api/sports-admin/games/${gameId}/story/regenerate-compact`,
    { method: 'POST' }
  );
  
  if (!response.ok) {
    throw new Error(`Failed to regenerate compact story: ${response.statusText}`);
  }
  
  return response.json();
}

/**
 * Regenerate everything (chapters → summaries → compact story).
 */
export async function regenerateAll(gameId: number): Promise<GameStoryResponse> {
  const response = await fetch(
    `${API_BASE}/api/sports-admin/games/${gameId}/story/regenerate-all`,
    { method: 'POST' }
  );
  
  if (!response.ok) {
    throw new Error(`Failed to regenerate all: ${response.statusText}`);
  }
  
  return response.json();
}
