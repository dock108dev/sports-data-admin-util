/**
 * API client for crypto data administration endpoints.
 *
 * Mirrors the sports admin client but targets /api/admin/crypto routes.
 */

import { getApiBase } from "./apiBase";

export type CryptoIngestionRunResponse = {
  id: number;
  exchange_code: string;
  status: string;
  timeframe: string;
  symbols: string[];
  start_time: string | null;
  end_time: string | null;
  summary: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  requested_by: string | null;
  config: Record<string, unknown> | null;
};

export type CryptoAssetSummary = {
  id: number;
  symbol: string;
  base: string | null;
  quote: string | null;
  exchange_code: string;
};

export type CryptoAssetDetail = {
  id: number;
  symbol: string;
  base: string | null;
  quote: string | null;
  exchange_code: string;
  metadata: Record<string, unknown>;
};

export type CryptoAssetListResponse = {
  assets: CryptoAssetSummary[];
  total: number;
};

export type CryptoCandleSummary = {
  id: number;
  asset_id: number;
  exchange_code: string;
  symbol: string;
  timeframe: string;
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
};

export type CryptoCandleListResponse = {
  candles: CryptoCandleSummary[];
  total: number;
  next_offset: number | null;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const apiBase = getApiBase({
    serverInternalBaseEnv: process.env.SPORTS_API_INTERNAL_URL,
    serverPublicBaseEnv: process.env.NEXT_PUBLIC_THEORY_ENGINE_URL,
    localhostPort: 8000,
  });
  const url = `${apiBase}${path}`;

  try {
    const res = await fetch(url, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(init?.headers ?? {}),
      },
      cache: "no-store",
    });

    if (!res.ok) {
      const body = await res.text();
      throw new Error(`Request failed (${res.status}): ${body}`);
    }

    return await res.json();
  } catch (err) {
    if (err instanceof TypeError && err.message.includes("fetch")) {
      throw new Error(`Failed to connect to backend at ${apiBase}. Is the server running?`);
    }
    throw err;
  }
}

export async function createCryptoIngestionRun(payload: {
  requestedBy?: string;
  config: {
    exchangeCode: string;
    symbols: string[];
    timeframe: string;
    start?: string;
    end?: string;
    includeCandles?: boolean;
    backfillMissingCandles?: boolean;
  };
}): Promise<CryptoIngestionRunResponse> {
  return request("/api/admin/crypto/ingestion/runs", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function listCryptoIngestionRuns(params?: {
  exchange?: string;
  status?: string;
  timeframe?: string;
  limit?: number;
}): Promise<CryptoIngestionRunResponse[]> {
  const query = new URLSearchParams();
  if (params?.exchange) query.append("exchange", params.exchange);
  if (params?.status) query.append("status", params.status);
  if (params?.timeframe) query.append("timeframe", params.timeframe);
  if (typeof params?.limit === "number") query.append("limit", String(params.limit));
  const qs = query.toString();
  return request(`/api/admin/crypto/ingestion/runs${qs ? `?${qs}` : ""}`);
}

export async function fetchCryptoIngestionRun(runId: number): Promise<CryptoIngestionRunResponse> {
  return request(`/api/admin/crypto/ingestion/runs/${runId}`);
}

export async function listCryptoAssets(params?: {
  exchange?: string;
  symbolPrefix?: string;
  base?: string;
  quote?: string;
  limit?: number;
  offset?: number;
}): Promise<CryptoAssetListResponse> {
  const query = new URLSearchParams();
  if (params?.exchange) query.append("exchange", params.exchange);
  if (params?.symbolPrefix) query.append("symbolPrefix", params.symbolPrefix);
  if (params?.base) query.append("base", params.base);
  if (params?.quote) query.append("quote", params.quote);
  if (typeof params?.limit === "number") query.append("limit", String(params.limit));
  if (typeof params?.offset === "number") query.append("offset", String(params.offset));
  const qs = query.toString();
  return request(`/api/admin/crypto/assets${qs ? `?${qs}` : ""}`);
}

export async function fetchCryptoAsset(assetId: number): Promise<CryptoAssetDetail> {
  return request(`/api/admin/crypto/assets/${assetId}`);
}

export async function listCryptoCandles(params: {
  assetId?: number;
  symbol?: string;
  exchange?: string;
  timeframe?: string;
  start?: string;
  end?: string;
  limit?: number;
  offset?: number;
}): Promise<CryptoCandleListResponse> {
  const query = new URLSearchParams();
  if (typeof params.assetId === "number") query.append("assetId", String(params.assetId));
  if (params.symbol) query.append("symbol", params.symbol);
  if (params.exchange) query.append("exchange", params.exchange);
  if (params.timeframe) query.append("timeframe", params.timeframe);
  if (params.start) query.append("start", params.start);
  if (params.end) query.append("end", params.end);
  if (typeof params.limit === "number") query.append("limit", String(params.limit));
  if (typeof params.offset === "number") query.append("offset", String(params.offset));
  const qs = query.toString();
  return request(`/api/admin/crypto/candles${qs ? `?${qs}` : ""}`);
}

export async function fetchCryptoCandle(candleId: number): Promise<CryptoCandleSummary> {
  return request(`/api/admin/crypto/candles/${candleId}`);
}


