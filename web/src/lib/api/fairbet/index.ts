/**
 * FairBet API client
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface BookOdds {
  book: string;
  price: number;
  observed_at: string;
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
  books: BookOdds[];
}

export interface FairbetOddsResponse {
  bets: BetDefinition[];
  total: number;
  books_available: string[];
}

export interface FairbetOddsFilters {
  league?: string;
  limit?: number;
  offset?: number;
}

export async function fetchFairbetOdds(
  filters: FairbetOddsFilters = {}
): Promise<FairbetOddsResponse> {
  const params = new URLSearchParams();

  if (filters.league) params.set("league", filters.league);
  if (filters.limit) params.set("limit", filters.limit.toString());
  if (filters.offset) params.set("offset", filters.offset.toString());

  const url = `${API_BASE}/api/fairbet/odds?${params.toString()}`;
  const res = await fetch(url);

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
  const parts = key.split(":");
  if (parts.length < 2) return key;

  const value = parts.slice(1).join(":");
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
  };
  return mapping[key.toLowerCase()] || key;
}
