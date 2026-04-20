"use client";

import { useCallback, useEffect, useState } from "react";
import {
  getCircuitBreakers,
  type BreakerState,
  type CircuitBreakersResponse,
  type TripEvent,
} from "@/lib/api/sportsAdmin/circuitBreakers";
import styles from "./CircuitBreakerPanel.module.css";

function BreakerRow({ breaker }: { breaker: BreakerState }) {
  return (
    <div className={styles.breakerRow}>
      <span className={styles.breakerName}>{breaker.name}</span>
      <span className={breaker.isOpen ? styles.stateBadgeOpen : styles.stateBadgeClosed}>
        {breaker.isOpen ? "OPEN" : "closed"}
      </span>
      <span className={styles.tripCount}>
        {breaker.tripCount} trip{breaker.tripCount !== 1 ? "s" : ""}
      </span>
      {breaker.lastTripReason && (
        <span className={styles.lastReason} title={breaker.lastTripReason}>
          {breaker.lastTripReason.length > 60
            ? breaker.lastTripReason.slice(0, 60) + "…"
            : breaker.lastTripReason}
        </span>
      )}
    </div>
  );
}

function TripEventRow({ event }: { event: TripEvent }) {
  const ts = new Date(event.trippedAt).toLocaleString();
  return (
    <div className={styles.tripRow}>
      <span className={styles.tripTs}>{ts}</span>
      <span className={styles.tripName}>{event.breakerName}</span>
      <span className={styles.tripReason} title={event.reason}>
        {event.reason.length > 80 ? event.reason.slice(0, 80) + "…" : event.reason}
      </span>
    </div>
  );
}

export function CircuitBreakerPanel() {
  const [data, setData] = useState<CircuitBreakersResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [showHistory, setShowHistory] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await getCircuitBreakers();
      setData(res);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, 15_000);
    return () => clearInterval(id);
  }, [load]);

  const openCount = data?.breakers.filter((b) => b.isOpen).length ?? 0;

  return (
    <div className={styles.panel}>
      <div className={styles.panelHeader}>
        <div>
          <span className={styles.panelTitle}>Circuit Breakers</span>
          {data && (
            <span className={openCount > 0 ? styles.summaryBadgeOpen : styles.summaryBadgeOk}>
              {openCount > 0 ? `${openCount} open` : "all closed"}
            </span>
          )}
        </div>
        <div className={styles.headerActions}>
          <button className={styles.refreshBtn} disabled={loading} onClick={load}>
            {loading ? "…" : "Refresh"}
          </button>
          <button
            className={styles.historyToggle}
            onClick={() => setShowHistory((v) => !v)}
          >
            {showHistory ? "Hide history" : "Show history"}
          </button>
        </div>
      </div>

      {error && <div className={styles.errorMsg}>{error}</div>}

      {data && (
        <>
          <div className={styles.breakerList}>
            {data.breakers.length === 0 ? (
              <div className={styles.emptyMsg}>No breakers registered yet.</div>
            ) : (
              data.breakers.map((b) => <BreakerRow key={b.name} breaker={b} />)
            )}
          </div>

          {showHistory && (
            <div className={styles.historySection}>
              <div className={styles.historyTitle}>Recent trips (DB, last 50)</div>
              {data.recentTrips.length === 0 ? (
                <div className={styles.emptyMsg}>No trip events recorded.</div>
              ) : (
                data.recentTrips.map((ev) => <TripEventRow key={ev.id} event={ev} />)
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
