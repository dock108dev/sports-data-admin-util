"use client";

import { useMemo, useState, useEffect } from "react";
import type { AdminGameDetail } from "@/lib/api/sportsAdmin";
import { CollapsibleSection } from "./CollapsibleSection";
import styles from "./styles.module.css";

type OddsSectionProps = {
  odds: AdminGameDetail["odds"];
};

export function OddsSection({ odds }: OddsSectionProps) {
  const bookOptions = useMemo(() => {
    return Array.from(new Set(odds.map((o) => o.book)));
  }, [odds]);

  const [selectedBook, setSelectedBook] = useState<string | null>(null);

  useEffect(() => {
    const preferred = bookOptions.find((b) => b === "FanDuel") ?? bookOptions[0] ?? null;
    setSelectedBook(preferred ?? null);
  }, [bookOptions]);

  const filteredOdds = useMemo(() => {
    if (!selectedBook) return [];
    return odds.filter((o) => o.book === selectedBook);
  }, [odds, selectedBook]);

  const oddsByMarket = useMemo(() => {
    const sortByType = (a: (typeof filteredOdds)[0], b: (typeof filteredOdds)[0]) => {
      // Opening lines first, then closing
      if (a.isClosingLine === b.isClosingLine) return 0;
      return a.isClosingLine ? 1 : -1;
    };
    const spread = filteredOdds.filter((o) => o.marketType === "spread").sort(sortByType);
    const total = filteredOdds.filter((o) => o.marketType === "total").sort(sortByType);
    const moneyline = filteredOdds.filter((o) => o.marketType === "moneyline").sort(sortByType);
    return { spread, total, moneyline };
  }, [filteredOdds]);

  return (
    <CollapsibleSection title="Odds" defaultOpen={false}>
      {odds.length === 0 ? (
        <div style={{ color: "#475569" }}>No odds found.</div>
      ) : (
        <>
          <div className={styles.oddsHeader}>
            <label>
              Book:
              <select
                className={styles.oddsBookSelect}
                value={selectedBook ?? ""}
                onChange={(e) => setSelectedBook(e.target.value)}
              >
                {bookOptions.map((b) => (
                  <option key={b} value={b}>
                    {b}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <div className={styles.oddsGroup}>
            <h3>Spread</h3>
            {oddsByMarket.spread.length === 0 ? (
              <div className={styles.subtle}>No spread odds for {selectedBook}</div>
            ) : (
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th>Type</th>
                    <th>Side</th>
                    <th>Line</th>
                    <th>Price</th>
                    <th>Observed</th>
                  </tr>
                </thead>
                <tbody>
                  {oddsByMarket.spread.map((o, idx) => (
                    <tr key={`${o.side}-${o.isClosingLine}-${idx}`}>
                      <td>
                        <span className={o.isClosingLine ? styles.closingBadge : styles.openingBadge}>
                          {o.isClosingLine ? "Closing" : "Opening"}
                        </span>
                      </td>
                      <td>{o.side ?? "—"}</td>
                      <td>{o.line ?? "—"}</td>
                      <td>{o.price ?? "—"}</td>
                      <td>{o.observedAt ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          <div className={styles.oddsGroup}>
            <h3>Total</h3>
            {oddsByMarket.total.length === 0 ? (
              <div className={styles.subtle}>No total odds for {selectedBook}</div>
            ) : (
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th>Type</th>
                    <th>Side</th>
                    <th>Line</th>
                    <th>Price</th>
                    <th>Observed</th>
                  </tr>
                </thead>
                <tbody>
                  {oddsByMarket.total.map((o, idx) => (
                    <tr key={`${o.side}-${o.isClosingLine}-${idx}`}>
                      <td>
                        <span className={o.isClosingLine ? styles.closingBadge : styles.openingBadge}>
                          {o.isClosingLine ? "Closing" : "Opening"}
                        </span>
                      </td>
                      <td>{o.side ?? "—"}</td>
                      <td>{o.line ?? "—"}</td>
                      <td>{o.price ?? "—"}</td>
                      <td>{o.observedAt ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          <div className={styles.oddsGroup}>
            <h3>Moneyline</h3>
            {oddsByMarket.moneyline.length === 0 ? (
              <div className={styles.subtle}>No moneyline odds for {selectedBook}</div>
            ) : (
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th>Type</th>
                    <th>Side</th>
                    <th>Price</th>
                    <th>Observed</th>
                  </tr>
                </thead>
                <tbody>
                  {oddsByMarket.moneyline.map((o, idx) => (
                    <tr key={`${o.side}-${o.isClosingLine}-${idx}`}>
                      <td>
                        <span className={o.isClosingLine ? styles.closingBadge : styles.openingBadge}>
                          {o.isClosingLine ? "Closing" : "Opening"}
                        </span>
                      </td>
                      <td>{o.side ?? "—"}</td>
                      <td>{o.price ?? "—"}</td>
                      <td>{o.observedAt ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </>
      )}
    </CollapsibleSection>
  );
}
