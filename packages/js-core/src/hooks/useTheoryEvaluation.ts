/**
 * React hooks for theory evaluation.
 */

import { useState, useCallback } from "react";
import { TheoryAPI, createClient } from "../api";
import type {
  TheoryRequest,
  TheoryResponse,
  CryptoResponse,
  StocksResponse,
  ConspiraciesResponse,
} from "../types";

interface UseTheoryEvaluationState<T extends TheoryResponse> {
  data: T | null;
  loading: boolean;
  error: Error | null;
}

interface UseTheoryEvaluationReturn<T extends TheoryResponse> {
  data: T | null;
  loading: boolean;
  error: Error | null;
  evaluate: (request: TheoryRequest) => Promise<T | null>;
  reset: () => void;
}

/**
 * Hook for evaluating theories with loading and error states.
 */
export function useTheoryEvaluation<T extends TheoryResponse = TheoryResponse>(
  domain: "crypto" | "stocks" | "conspiracies" | "playlist",
  baseURL?: string
): UseTheoryEvaluationReturn<T> {
  const [state, setState] = useState<UseTheoryEvaluationState<T>>({
    data: null,
    loading: false,
    error: null,
  });

  const client = createClient(baseURL);
  const api = new TheoryAPI(client);

  const evaluate = useCallback(
    async (request: TheoryRequest): Promise<T | null> => {
      setState({ data: null, loading: true, error: null });

      try {
        let response: TheoryResponse;

        switch (domain) {
          case "crypto":
            response = await api.evaluateCrypto(request);
            break;
          case "stocks":
            response = await api.evaluateStocks(request);
            break;
          case "conspiracies":
            response = await api.evaluateConspiracies(request);
            break;
          default:
            response = await api.evaluateTheory(request);
        }

        setState({ data: response as T, loading: false, error: null });
        return response as T;
      } catch (err) {
        const error =
          err instanceof Error
            ? err
            : new Error(err instanceof Error ? err.message : String(err));

        setState({ data: null, loading: false, error });
        return null;
      }
    },
    [domain, api]
  );

  const reset = useCallback(() => {
    setState({ data: null, loading: false, error: null });
  }, []);

  return {
    data: state.data,
    loading: state.loading,
    error: state.error,
    evaluate,
    reset,
  };
}

/**
 * Hook specifically for crypto domain.
 */
export function useCryptoEvaluation(
  baseURL?: string
): UseTheoryEvaluationReturn<CryptoResponse> {
  return useTheoryEvaluation<CryptoResponse>("crypto", baseURL);
}

/**
 * Hook specifically for stocks domain.
 */
export function useStocksEvaluation(
  baseURL?: string
): UseTheoryEvaluationReturn<StocksResponse> {
  return useTheoryEvaluation<StocksResponse>("stocks", baseURL);
}

/**
 * Hook specifically for conspiracies domain.
 */
export function useConspiraciesEvaluation(
  baseURL?: string
): UseTheoryEvaluationReturn<ConspiraciesResponse> {
  return useTheoryEvaluation<ConspiraciesResponse>("conspiracies", baseURL);
}
