import { useState, useEffect, useCallback } from "react";
import { GameSummary, GameFilters, listGames } from "@/lib/api/sportsAdmin";

export const DEFAULT_GAME_FILTERS: GameFilters = {
  leagues: [],
  season: undefined,
  team: "",
  startDate: undefined,
  endDate: undefined,
  missingBoxscore: false,
  missingPlayerStats: false,
  missingOdds: false,
  missingSocial: false,
  missingAny: false,
  limit: 25,
  offset: 0,
};

interface UseGameFiltersOptions {
  defaultLimit?: number;
  loadMoreMode?: boolean;
}

interface UseGameFiltersReturn {
  formFilters: GameFilters;
  setFormFilters: React.Dispatch<React.SetStateAction<GameFilters>>;
  appliedFilters: GameFilters;
  games: GameSummary[];
  total: number;
  nextOffset: number | null;
  aggregates: {
    withBoxscore: number;
    withPlayerStats: number;
    withOdds: number;
    withSocial: number;
    withPbp: number;
    withStory: number;
  } | null;
  loading: boolean;
  error: string | null;
  applyFilters: (nextFilters?: GameFilters) => void;
  resetFilters: () => void;
  loadMore: () => void;
  toggleLeague: (code: string) => void;
}

/**
 * Shared hook for game filtering and data loading.
 * Handles form state, applied filters, API calls, and pagination.
 */
export function useGameFilters(options: UseGameFiltersOptions = {}): UseGameFiltersReturn {
  const { defaultLimit = 25, loadMoreMode = false } = options;
  
  const [formFilters, setFormFilters] = useState<GameFilters>({
    ...DEFAULT_GAME_FILTERS,
    limit: defaultLimit,
  });
  const [appliedFilters, setAppliedFilters] = useState<GameFilters>({
    ...DEFAULT_GAME_FILTERS,
    limit: defaultLimit,
  });
  const [games, setGames] = useState<GameSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [aggregates, setAggregates] = useState<{
    withBoxscore: number;
    withPlayerStats: number;
    withOdds: number;
    withPbp: number;
    withSocial: number;
    withStory: number;
  } | null>(null);
  const [nextOffset, setNextOffset] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const response = await listGames(appliedFilters);
        if (cancelled) return;
        
        if (loadMoreMode && appliedFilters.offset && appliedFilters.offset > 0) {
          setGames((prev) => [...prev, ...response.games]);
        } else {
          setGames(response.games);
        }
        
        setTotal(response.total);
        setAggregates({
          withBoxscore: response.with_boxscore_count ?? 0,
          withPlayerStats: response.with_player_stats_count ?? 0,
          withOdds: response.with_odds_count ?? 0,
          withSocial: response.with_social_count ?? 0,
          withPbp: response.with_pbp_count ?? 0,
          withStory: response.with_story_count ?? 0,
        });
        setNextOffset(response.next_offset);
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Failed to load games");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [appliedFilters, loadMoreMode]);

  const applyFilters = useCallback(
    (nextFilters?: GameFilters) => {
      const filtersToApply: GameFilters = nextFilters
        ? { ...nextFilters, leagues: nextFilters.leagues ?? [] }
        : { ...formFilters, leagues: formFilters.leagues ?? [], offset: 0 };
      setAppliedFilters(filtersToApply);
    if (!loadMoreMode) {
      setGames([]);
    }
      setAggregates(null);
    },
    [formFilters, loadMoreMode],
  );

  const resetFilters = useCallback(() => {
    const defaultFilters = { ...DEFAULT_GAME_FILTERS, limit: defaultLimit };
    setFormFilters(defaultFilters);
    setAppliedFilters(defaultFilters);
    setGames([]);
    setAggregates(null);
  }, [defaultLimit]);

  const loadMore = useCallback(() => {
    if (nextOffset === null) return;
    setAppliedFilters((prev) => ({ ...prev, offset: nextOffset }));
  }, [nextOffset]);

  const toggleLeague = useCallback((code: string) => {
    setFormFilters((prev) => {
      const exists = prev.leagues.includes(code);
      return {
        ...prev,
        leagues: exists ? prev.leagues.filter((lg) => lg !== code) : [...prev.leagues, code],
      };
    });
  }, []);

  return {
    formFilters,
    setFormFilters,
    appliedFilters,
    games,
    total,
    aggregates,
    nextOffset,
    loading,
    error,
    applyFilters,
    resetFilters,
    loadMore,
    toggleLeague,
  };
}

