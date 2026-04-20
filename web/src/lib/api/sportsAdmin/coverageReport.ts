const BASE = "/api/admin";

export interface SportBreakdownEntry {
  sport: string;
  finalsCount: number;
  flowsCount: number;
  missingCount: number;
  fallbackCount: number;
  avgQualityScore: number | null;
}

export interface CoverageReportResponse {
  id: number;
  reportDate: string;
  generatedAt: string;
  sportBreakdown: SportBreakdownEntry[];
  totalFinals: number;
  totalFlows: number;
  totalMissing: number;
  totalFallbacks: number;
  avgQualityScore: number | null;
  createdAt: string;
  updatedAt: string;
}

export async function getCoverageReport(): Promise<CoverageReportResponse> {
  const res = await fetch(`${BASE}/pipeline/coverage-report`, {
    headers: { "Content-Type": "application/json" },
  });
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`coverage-report ${res.status}: ${text}`);
  }
  return res.json() as Promise<CoverageReportResponse>;
}
