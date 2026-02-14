/**
 * FairBet API client
 */

import { getApiBase } from "../apiBase";

/** Build headers including API key if configured. */
function buildHeaders(): HeadersInit {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };

  // Add API key for authentication (server-side only)
  const apiKey = process.env.SPORTS_API_KEY;
  if (apiKey) {
    headers["X-API-Key"] = apiKey;
  }

  return headers;
}

export interface BookOdds {
  book: string;
  price: number;
  observed_at: string;
  ev_percent: number | null;
  implied_prob: number | null;
  is_sharp: boolean;
}

export interface BetDefinition {
  game_id: number;
  league_code: string;
  home_team: string;
  away_team: string;
  game_date: string;
  market_key: string;
  selection_key: string;
  line_value: number;
  market_category: string | null;
  player_name: string | null;
  description: string | null;
  true_prob: number | null;
  books: BookOdds[];
}

export interface GameOption {
  game_id: number;
  matchup: string;
  game_date: string | null;
}

export interface FairbetOddsResponse {
  bets: BetDefinition[];
  total: number;
  books_available: string[];
  market_categories_available: string[];
  games_available: GameOption[];
}

export interface FairbetOddsFilters {
  league?: string;
  market_category?: string;
  game_id?: number;
  book?: string;
  player_name?: string;
  min_ev?: number;
  sort_by?: string;
  limit?: number;
  offset?: number;
}

export async function fetchFairbetOdds(
  filters: FairbetOddsFilters = {}
): Promise<FairbetOddsResponse> {
  const params = new URLSearchParams();

  if (filters.league) params.set("league", filters.league);
  if (filters.market_category) params.set("market_category", filters.market_category);
  if (filters.game_id) params.set("game_id", filters.game_id.toString());
  if (filters.book) params.set("book", filters.book);
  if (filters.player_name) params.set("player_name", filters.player_name);
  if (filters.min_ev !== undefined) params.set("min_ev", filters.min_ev.toString());
  if (filters.sort_by) params.set("sort_by", filters.sort_by);
  if (filters.limit) params.set("limit", filters.limit.toString());
  if (filters.offset) params.set("offset", filters.offset.toString());

  const url = `${getApiBase()}/api/fairbet/odds?${params.toString()}`;
  const res = await fetch(url, {
    headers: buildHeaders(),
  });

  if (!res.ok) {
    throw new Error(`Failed to fetch FairBet odds: ${res.statusText}`);
  }

  return res.json();
}

/**
 * Format American odds for display
 */
export function formatOdds(price: number): string {
  if (price >= 0) {
    return `+${price}`;
  }
  return price.toString();
}

/**
 * Get the best odds (highest for positive, lowest magnitude for negative)
 */
export function getBestOdds(books: BookOdds[]): BookOdds | null {
  if (books.length === 0) return null;

  return books.reduce((best, current) => {
    // For positive odds, higher is better
    // For negative odds, closer to 0 is better (e.g., -105 > -110)
    if (current.price > best.price) {
      return current;
    }
    return best;
  });
}

/**
 * Format selection key for display
 */
export function formatSelectionKey(key: string): string {
  // team:los_angeles_lakers -> Los Angeles Lakers
  // total:over -> Over
  // player:lebron_james:over -> LeBron James Over
  const parts = key.split(":");
  if (parts.length < 2) return key;

  const value = parts.slice(1).join(" ");
  return value
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

/**
 * Format market key for display
 */
export function formatMarketKey(key: string): string {
  const mapping: Record<string, string> = {
    h2h: "Moneyline",
    spreads: "Spread",
    totals: "Total",
    moneyline: "Moneyline",
    spread: "Spread",
    total: "Total",
    // Player prop markets
    player_points: "Points",
    player_rebounds: "Rebounds",
    player_assists: "Assists",
    player_threes: "3-Pointers",
    player_points_rebounds_assists: "PRA",
    player_blocks: "Blocks",
    player_steals: "Steals",
    player_goals: "Goals",
    player_shots_on_goal: "SOG",
    player_total_saves: "Saves",
    // Other markets
    team_totals: "Team Total",
    alternate_spreads: "Alt Spread",
    alternate_totals: "Alt Total",
  };
  return mapping[key.toLowerCase()] || key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

/**
 * Format market category for display
 */
export function formatMarketCategory(category: string): string {
  const mapping: Record<string, string> = {
    mainline: "Mainline",
    player_prop: "Player Prop",
    team_prop: "Team Prop",
    alternate: "Alternate",
    period: "Period",
    game_prop: "Game Prop",
  };
  return mapping[category] || category;
}

/**
 * Format EV percentage for display
 */
export function formatEv(ev: number | null): string {
  if (ev === null || ev === undefined) return "—";
  const sign = ev >= 0 ? "+" : "";
  return `${sign}${ev.toFixed(1)}%`;
}

/**
 * Get EV color class
 */
export function getEvColor(ev: number | null): "positive" | "negative" | "neutral" {
  if (ev === null || ev === undefined) return "neutral";
  if (ev > 0) return "positive";
  if (ev < 0) return "negative";
  return "neutral";
}
