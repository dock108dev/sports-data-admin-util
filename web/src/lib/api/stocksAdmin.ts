/**
 * API client for stocks (equities) data administration endpoints.
 *
 * Mirrors the crypto admin client but targets /api/admin/stocks routes.
 */

import { getApiBase } from "./apiBase";

export type StocksIngestionRunResponse = {
  id: number;
  exchange_code: string;
  status: string;
  timeframe: string;
  tickers: string[];
  start_time: string | null;
  end_time: string | null;
  summary: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  requested_by: string | null;
  config: Record<string, unknown> | null;
};

export type EquityAssetSummary = {
  id: number;
  ticker: string;
  name: string | null;
  exchange_code: string;
  sector: string | null;
  industry: string | null;
};

export type EquityAssetDetail = {
  id: number;
  ticker: string;
  name: string | null;
  exchange_code: string;
  sector: string | null;
  industry: string | null;
  metadata: Record<string, unknown>;
};

export type EquityAssetListResponse = {
  assets: EquityAssetSummary[];
  total: number;
};

export type EquityCandleSummary = {
  id: number;
  asset_id: number;
  exchange_code: string;
  ticker: string;
  timeframe: string;
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
};

export type EquityCandleListResponse = {
  candles: EquityCandleSummary[];
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

export async function createStocksIngestionRun(payload: {
  requestedBy?: string;
  config: {
    exchangeCode: string;
    tickers: string[];
    timeframe: string;
    start?: string;
    end?: string;
    includeCandles?: boolean;
    backfillMissingCandles?: boolean;
  };
}): Promise<StocksIngestionRunResponse> {
  return request("/api/admin/stocks/ingestion/runs", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function listStocksIngestionRuns(params?: {
  exchange?: string;
  status?: string;
  timeframe?: string;
  limit?: number;
}): Promise<StocksIngestionRunResponse[]> {
  const query = new URLSearchParams();
  if (params?.exchange) query.append("exchange", params.exchange);
  if (params?.status) query.append("status", params.status);
  if (params?.timeframe) query.append("timeframe", params.timeframe);
  if (typeof params?.limit === "number") query.append("limit", String(params.limit));
  const qs = query.toString();
  return request(`/api/admin/stocks/ingestion/runs${qs ? `?${qs}` : ""}`);
}

export async function fetchStocksIngestionRun(runId: number): Promise<StocksIngestionRunResponse> {
  return request(`/api/admin/stocks/ingestion/runs/${runId}`);
}

export async function listEquityAssets(params?: {
  exchange?: string;
  tickerPrefix?: string;
  sector?: string;
  industry?: string;
  limit?: number;
  offset?: number;
}): Promise<EquityAssetListResponse> {
  const query = new URLSearchParams();
  if (params?.exchange) query.append("exchange", params.exchange);
  if (params?.tickerPrefix) query.append("tickerPrefix", params.tickerPrefix);
  if (params?.sector) query.append("sector", params.sector);
  if (params?.industry) query.append("industry", params.industry);
  if (typeof params?.limit === "number") query.append("limit", String(params.limit));
  if (typeof params?.offset === "number") query.append("offset", String(params.offset));
  const qs = query.toString();
  return request(`/api/admin/stocks/assets${qs ? `?${qs}` : ""}`);
}

export async function fetchEquityAsset(assetId: number): Promise<EquityAssetDetail> {
  return request(`/api/admin/stocks/assets/${assetId}`);
}

export async function listEquityCandles(params: {
  assetId?: number;
  ticker?: string;
  exchange?: string;
  timeframe?: string;
  start?: string;
  end?: string;
  limit?: number;
  offset?: number;
}): Promise<EquityCandleListResponse> {
  const query = new URLSearchParams();
  if (typeof params.assetId === "number") query.append("assetId", String(params.assetId));
  if (params.ticker) query.append("ticker", params.ticker);
  if (params.exchange) query.append("exchange", params.exchange);
  if (params.timeframe) query.append("timeframe", params.timeframe);
  if (params.start) query.append("start", params.start);
  if (params.end) query.append("end", params.end);
  if (typeof params.limit === "number") query.append("limit", String(params.limit));
  if (typeof params.offset === "number") query.append("offset", String(params.offset));
  const qs = query.toString();
  return request(`/api/admin/stocks/candles${qs ? `?${qs}` : ""}`);
}

export async function fetchEquityCandle(candleId: number): Promise<EquityCandleSummary> {
  return request(`/api/admin/stocks/candles/${candleId}`);
}


