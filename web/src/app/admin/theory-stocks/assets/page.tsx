"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import styles from "./page.module.css";
import {
  listEquityAssets,
  type EquityAssetSummary,
  type EquityAssetListResponse,
} from "@/lib/api/stocksAdmin";

const EXCHANGES = ["", "NYSE", "NASDAQ"];

type AssetFilters = {
  exchange: string;
  tickerPrefix: string;
  sector: string;
  industry: string;
};

const EMPTY_FILTERS: AssetFilters = {
  exchange: "",
  tickerPrefix: "",
  sector: "",
  industry: "",
};

export default function StocksAssetsPage() {
  const [assetsResponse, setAssetsResponse] = useState<EquityAssetListResponse | null>(null);
  const [exchange, setExchange] = useState<string>("");
  const [tickerPrefix, setTickerPrefix] = useState<string>("");
  const [sector, setSector] = useState<string>("");
  const [industry, setIndustry] = useState<string>("");
  const [offset, setOffset] = useState(0);
  const [limit] = useState(50);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadAssets = useCallback(async (filters: AssetFilters, newOffset = 0) => {
    try {
      setLoading(true);
      const data = await listEquityAssets({
        exchange: filters.exchange || undefined,
        tickerPrefix: filters.tickerPrefix || undefined,
        sector: filters.sector || undefined,
        industry: filters.industry || undefined,
        limit,
        offset: newOffset,
      });
      setAssetsResponse(data);
      setOffset(newOffset);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [limit]);

  useEffect(() => {
    loadAssets(EMPTY_FILTERS, 0);
  }, [loadAssets]);

  const handleApplyFilters = () => {
    loadAssets({ exchange, tickerPrefix, sector, industry }, 0);
  };

  const handleReset = () => {
    setExchange("");
    setTickerPrefix("");
    setSector("");
    setIndustry("");
    loadAssets(EMPTY_FILTERS, 0);
  };

  const pageCount =
    assetsResponse && assetsResponse.total > 0
      ? Math.ceil(assetsResponse.total / limit)
      : 1;
  const currentPage = Math.floor(offset / limit) + 1;

  const items: EquityAssetSummary[] = assetsResponse?.assets ?? [];

  if (loading && !assetsResponse && !error) {
    return <div className={styles.loading}>Loading stocks assets...</div>;
  }

  if (error) {
    return <div className={styles.error}>Error: {error}</div>;
  }

  return (
    <div className={styles.container}>
      <header className={styles.header}>
        <h1 className={styles.title}>Stocks Assets</h1>
        <p className={styles.subtitle}>Browse tracked equities by exchange, sector, and industry</p>
      </header>

      <div className={styles.filters}>
        <select value={exchange} onChange={(e) => setExchange(e.target.value)}>
          {EXCHANGES.map((ex) => (
            <option key={ex || "all"} value={ex}>
              {ex || "All exchanges"}
            </option>
          ))}
        </select>
        <input
          type="text"
          placeholder="Ticker prefix (e.g. A)"
          value={tickerPrefix}
          onChange={(e) => setTickerPrefix(e.target.value)}
        />
        <input
          type="text"
          placeholder="Sector"
          value={sector}
          onChange={(e) => setSector(e.target.value)}
        />
        <input
          type="text"
          placeholder="Industry"
          value={industry}
          onChange={(e) => setIndustry(e.target.value)}
        />
      </div>
      <div className={styles.filtersRow}>
        <button onClick={handleApplyFilters}>Apply</button>
        <button onClick={handleReset}>Reset</button>
      </div>

      <section className={styles.tableCard}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th>Ticker</th>
              <th>Exchange</th>
              <th>Name</th>
              <th>Sector</th>
              <th>Industry</th>
            </tr>
          </thead>
          <tbody>
            {items.map((asset) => (
              <tr key={asset.id}>
                <td>
                  <Link
                    href={`/admin/theory-stocks/assets/${asset.id}`}
                    className={styles.symbolLink}
                  >
                    {asset.ticker}
                  </Link>
                </td>
                <td>{asset.exchange_code}</td>
                <td>{asset.name ?? "—"}</td>
                <td>{asset.sector ?? "—"}</td>
                <td>{asset.industry ?? "—"}</td>
              </tr>
            ))}
            {items.length === 0 && (
              <tr>
                <td colSpan={5}>No assets found.</td>
              </tr>
            )}
          </tbody>
        </table>

        <div className={styles.pagination}>
          <span>
            Page {currentPage} of {pageCount} · {assetsResponse?.total ?? 0} assets
          </span>
          <div>
            <button
              onClick={() =>
                loadAssets(
                  { exchange, tickerPrefix, sector, industry },
                  Math.max(0, offset - limit),
                )
              }
              disabled={offset === 0 || loading}
            >
              Previous
            </button>
            <button
              onClick={() => loadAssets({ exchange, tickerPrefix, sector, industry }, offset + limit)}
              disabled={
                loading || !assetsResponse || offset + limit >= assetsResponse.total
              }
            >
              Next
            </button>
          </div>
        </div>
      </section>
    </div>
  );
}
