import { request } from "./client";

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
  return request<CoverageReportResponse>("/api/admin/pipeline/coverage-report");
}
