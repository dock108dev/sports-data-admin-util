import { request } from "./client";

export interface BreakerState {
  name: string;
  isOpen: boolean;
  tripCount: number;
  lastTripReason: string | null;
  lastTripAt: string | null;
  lastResetAt: string | null;
}

export interface TripEvent {
  id: number;
  breakerName: string;
  reason: string;
  trippedAt: string;
}

export interface CircuitBreakersResponse {
  breakers: BreakerState[];
  recentTrips: TripEvent[];
}

export async function getCircuitBreakers(): Promise<CircuitBreakersResponse> {
  return request("/api/admin/circuit-breakers");
}
