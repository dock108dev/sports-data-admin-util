/**
 * Theory evaluation API methods with type-safe endpoints for all domains.
 */

import { APIClient } from "./client";
import type {
  TheoryRequest,
  TheoryResponse,
  CryptoResponse,
  StocksResponse,
  ConspiraciesResponse,
} from "../types";

export class TheoryAPI {
  constructor(private client: APIClient) {}

  /**
   * Evaluate a theory using the generic endpoint (auto-routes domain).
   */
  async evaluateTheory(request: TheoryRequest): Promise<TheoryResponse> {
    return this.client.post<TheoryResponse>("/api/theory/evaluate", request);
  }

  /**
   * Evaluate a crypto theory.
   */
  async evaluateCrypto(request: TheoryRequest): Promise<CryptoResponse> {
    return this.client.post<CryptoResponse>("/api/theory/crypto", request);
  }

  /**
   * Evaluate a stocks theory.
   */
  async evaluateStocks(request: TheoryRequest): Promise<StocksResponse> {
    return this.client.post<StocksResponse>("/api/theory/stocks", request);
  }

  /**
   * Evaluate a conspiracy theory.
   */
  async evaluateConspiracies(
    request: TheoryRequest
  ): Promise<ConspiraciesResponse> {
    return this.client.post<ConspiraciesResponse>(
      "/api/theory/conspiracies",
      request
    );
  }
}
