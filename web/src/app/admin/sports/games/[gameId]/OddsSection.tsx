"use client";

import { useMemo, useState } from "react";
import type { OddsEntry, AdminGameDetail } from "@/lib/api/sportsAdmin";
import { CollapsibleSection } from "./CollapsibleSection";
import styles from "./styles.module.css";

type OddsSectionProps = {
  odds: AdminGameDetail["odds"];
};

const CATEGORY_LABELS: Record<string, string> = {
  mainline: "Mainline",
  player_prop: "Player Props",
  team_prop: "Team Props",
  alternate: "Alternates",
};

function categoryLabel(cat: string): string {
  return CATEGORY_LABELS[cat] ?? cat.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

/** Group odds by market category. */
function groupOddsByCategory(odds: OddsEntry[]): Map<string, OddsEntry[]> {
  const map = new Map<string, OddsEntry[]>();
  for (const o of odds) {
    const cat = o.marketCategory ?? "mainline";
    const arr = map.get(cat);
    if (arr) {
      arr.push(o);
    } else {
      map.set(cat, [o]);
    }
  }
  return map;
}

type CrossBookRow = {
  label: string;
  line: number | null;
  prices: Record<string, number | null>; // book -> price
};

/** Build cross-book comparison rows for a set of odds sharing a market type + optional grouping key. */
function buildCrossBookRows(
  odds: OddsEntry[],
  books: string[],
): CrossBookRow[] {
  // Group by side
  const bySide = new Map<string, OddsEntry[]>();
  for (const o of odds) {
    const key = o.side ?? "—";
    const arr = bySide.get(key);
    if (arr) {
      arr.push(o);
    } else {
      bySide.set(key, [o]);
    }
  }

  const rows: CrossBookRow[] = [];
  for (const [side, sideOdds] of bySide) {
    // Prefer closing lines; fall back to any line
    const prices: Record<string, number | null> = {};
    let bestLine: number | null = null;
    for (const book of books) {
      const match =
        sideOdds.find((o) => o.book === book && o.isClosingLine) ??
        sideOdds.find((o) => o.book === book);
      prices[book] = match?.price ?? null;
      if (match?.line != null && bestLine == null) {
        bestLine = match.line;
      }
    }
    rows.push({ label: side, line: bestLine, prices });
  }
  return rows;
}

function formatPrice(price: number | null): string {
  if (price == null) return "—";
  return price > 0 ? `+${price}` : String(price);
}

/** Cross-book table for a set of odds rows. */
function CrossBookTable({
  rows,
  books,
  showLine,
}: {
  rows: CrossBookRow[];
  books: string[];
  showLine: boolean;
}) {
  if (rows.length === 0) return null;
  return (
    <table className={styles.crossBookTable}>
      <thead>
        <tr>
          <th>Side</th>
          {showLine && <th>Line</th>}
          {books.map((b) => (
            <th key={b}>{b}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.label}>
            <td>{r.label}</td>
            {showLine && <td>{r.line ?? "—"}</td>}
            {books.map((b) => (
              <td key={b} className={styles.crossBookCell}>
                {formatPrice(r.prices[b])}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** Mainline tab: spread, total, moneyline sub-tables. */
function MainlineTab({ odds, books }: { odds: OddsEntry[]; books: string[] }) {
  const byMarket = useMemo(() => {
    const map = new Map<string, OddsEntry[]>();
    for (const o of odds) {
      const arr = map.get(o.marketType);
      if (arr) {
        arr.push(o);
      } else {
        map.set(o.marketType, [o]);
      }
    }
    return map;
  }, [odds]);

  const sortedKeys = useMemo(() => {
    const order = ["spread", "total", "moneyline"];
    const keys = Array.from(byMarket.keys());
    return keys.sort((a, b) => {
      const ai = order.indexOf(a);
      const bi = order.indexOf(b);
      return (ai === -1 ? 999 : ai) - (bi === -1 ? 999 : bi);
    });
  }, [byMarket]);

  if (sortedKeys.length === 0) {
    return <div className={styles.subtle}>No mainline odds.</div>;
  }

  return (
    <>
      {sortedKeys.map((mt) => {
        const marketOdds = byMarket.get(mt) ?? [];
        const rows = buildCrossBookRows(marketOdds, books);
        const showLine = mt !== "moneyline";
        return (
          <div key={mt} className={styles.oddsGroup}>
            <h3>{mt.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())}</h3>
            <CrossBookTable rows={rows} books={books} showLine={showLine} />
          </div>
        );
      })}
    </>
  );
}

/** Player Props tab: search + grouped by player, then market type. */
function PlayerPropsTab({ odds, books }: { odds: OddsEntry[]; books: string[] }) {
  const [search, setSearch] = useState("");

  const filtered = useMemo(() => {
    if (!search.trim()) return odds;
    const q = search.toLowerCase();
    return odds.filter((o) => o.playerName?.toLowerCase().includes(q));
  }, [odds, search]);

  // Group by player name, then market type
  const grouped = useMemo(() => {
    const map = new Map<string, Map<string, OddsEntry[]>>();
    for (const o of filtered) {
      const player = o.playerName ?? "Unknown";
      let playerMap = map.get(player);
      if (!playerMap) {
        playerMap = new Map();
        map.set(player, playerMap);
      }
      const arr = playerMap.get(o.marketType);
      if (arr) {
        arr.push(o);
      } else {
        playerMap.set(o.marketType, [o]);
      }
    }
    return map;
  }, [filtered]);

  return (
    <>
      <input
        type="text"
        className={styles.oddsSearchInput}
        placeholder="Search by player name..."
        value={search}
        onChange={(e) => setSearch(e.target.value)}
      />
      {grouped.size === 0 ? (
        <div className={styles.subtle}>
          {search ? "No matching player props." : "No player prop odds."}
        </div>
      ) : (
        Array.from(grouped.entries()).map(([player, marketMap]) => (
          <div key={player}>
            <div className={styles.propGroupHeader}>{player}</div>
            {Array.from(marketMap.entries()).map(([mt, marketOdds]) => {
              const rows = buildCrossBookRows(marketOdds, books);
              return (
                <div key={mt} className={styles.oddsGroup}>
                  <h3>{mt.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())}</h3>
                  <CrossBookTable rows={rows} books={books} showLine={true} />
                </div>
              );
            })}
          </div>
        ))
      )}
    </>
  );
}

/** Generic props tab: search + grouped by market_type + description. */
function GenericPropsTab({ odds, books }: { odds: OddsEntry[]; books: string[] }) {
  const [search, setSearch] = useState("");

  const filtered = useMemo(() => {
    if (!search.trim()) return odds;
    const q = search.toLowerCase();
    return odds.filter(
      (o) =>
        o.description?.toLowerCase().includes(q) ||
        o.marketType.toLowerCase().includes(q),
    );
  }, [odds, search]);

  // Group by market_type + description
  const grouped = useMemo(() => {
    const map = new Map<string, OddsEntry[]>();
    for (const o of filtered) {
      const key = o.description ? `${o.marketType}||${o.description}` : o.marketType;
      const arr = map.get(key);
      if (arr) {
        arr.push(o);
      } else {
        map.set(key, [o]);
      }
    }
    return map;
  }, [filtered]);

  return (
    <>
      <input
        type="text"
        className={styles.oddsSearchInput}
        placeholder="Search by description..."
        value={search}
        onChange={(e) => setSearch(e.target.value)}
      />
      {grouped.size === 0 ? (
        <div className={styles.subtle}>
          {search ? "No matching odds." : "No odds in this category."}
        </div>
      ) : (
        Array.from(grouped.entries()).map(([key, groupOdds]) => {
          const [mt, desc] = key.includes("||") ? key.split("||") : [key, null];
          const rows = buildCrossBookRows(groupOdds, books);
          const title = desc
            ? `${mt.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())} — ${desc}`
            : mt.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
          return (
            <div key={key} className={styles.oddsGroup}>
              <h3>{title}</h3>
              <CrossBookTable rows={rows} books={books} showLine={true} />
            </div>
          );
        })
      )}
    </>
  );
}

export function OddsSection({ odds }: OddsSectionProps) {
  const categoryMap = useMemo(() => groupOddsByCategory(odds), [odds]);

  // Stable ordering: mainline first, then alphabetically
  const categories = useMemo(() => {
    const keys = Array.from(categoryMap.keys());
    return keys.sort((a, b) => {
      if (a === "mainline") return -1;
      if (b === "mainline") return 1;
      return a.localeCompare(b);
    });
  }, [categoryMap]);

  const [activeTab, setActiveTab] = useState<string>("mainline");

  // All unique books across all odds
  const allBooks = useMemo(() => {
    const set = new Set(odds.map((o) => o.book));
    return Array.from(set).sort();
  }, [odds]);

  // Books present in the active tab
  const activeBooks = useMemo(() => {
    const activeOdds = categoryMap.get(activeTab) ?? [];
    const set = new Set(activeOdds.map((o) => o.book));
    // Keep the same order as allBooks for consistency
    return allBooks.filter((b) => set.has(b));
  }, [categoryMap, activeTab, allBooks]);

  // If activeTab isn't in categories (e.g. initial state with no mainline), pick first
  const effectiveTab = categories.includes(activeTab) ? activeTab : categories[0] ?? "mainline";

  return (
    <CollapsibleSection title="Odds" defaultOpen={false}>
      {odds.length === 0 ? (
        <div style={{ color: "#475569" }}>No odds found.</div>
      ) : (
        <>
          {/* Category tabs */}
          <div className={styles.oddsCategoryTabs}>
            {categories.map((cat) => {
              const count = categoryMap.get(cat)?.length ?? 0;
              const isActive = cat === effectiveTab;
              return (
                <button
                  key={cat}
                  className={`${styles.oddsCategoryTab} ${isActive ? styles.oddsCategoryTabActive : ""}`}
                  onClick={() => setActiveTab(cat)}
                >
                  {categoryLabel(cat)}
                  <span className={styles.oddsCategoryTabCount}>{count}</span>
                </button>
              );
            })}
          </div>

          {/* Tab content */}
          {effectiveTab === "mainline" && (
            <MainlineTab odds={categoryMap.get("mainline") ?? []} books={activeBooks} />
          )}
          {effectiveTab === "player_prop" && (
            <PlayerPropsTab odds={categoryMap.get("player_prop") ?? []} books={activeBooks} />
          )}
          {effectiveTab !== "mainline" && effectiveTab !== "player_prop" && (
            <GenericPropsTab odds={categoryMap.get(effectiveTab) ?? []} books={activeBooks} />
          )}
        </>
      )}
    </CollapsibleSection>
  );
}
