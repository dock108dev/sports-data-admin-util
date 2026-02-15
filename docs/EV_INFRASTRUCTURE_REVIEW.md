# Sharp Book EV Baseline Framework — Codebase Review

**Date:** 2026-02-14
**Scope:** NBA, NHL, NCAAB — mainlines, game/team props, player props
**Purpose:** Understand the terrain before building. No solutions proposed.

---

## 1. Current-State Summary

### How EV Is Computed Today

EV is computed **at query time only**, inside the FairBet API endpoint (`api/app/routers/fairbet/odds.py:319-378`). Nothing is persisted.

The pipeline:

1. **Group bets** by `(game_id, market_key, abs(line_value))` — forms candidate buckets
2. **Pair opposite sides** via `_pair_opposite_sides()` — within each bucket, pairs entries with different `selection_key` values; unpaired entries get `ev_disabled_reason = "no_pair"`
3. **Eligibility gate** (`evaluate_ev_eligibility()`) — checks strategy exists, Pinnacle present on both sides, freshness, minimum book count
4. **Find Pinnacle** on each side (`ev.py`) — first match wins
5. **Devig** both Pinnacle prices via additive normalization (`ev.py:56-71`) — divide each implied prob by the sum
6. **Compute EV%** for every book using `(decimal_odds * true_prob - 1) * 100` (`ev.py:74-95`)
7. **Annotate** each book entry with `ev_percent`, `implied_prob`, `is_sharp`, `true_prob`

### Where Assumptions Live

| Assumption | Location | Detail |
|-----------|----------|--------|
| Pinnacle is the only sharp book | `api/app/services/ev_config.py` | `eligible_sharp_books = ("Pinnacle",)` on all strategies |
| Two-way markets only | `api/app/routers/fairbet/odds.py` | `_pair_opposite_sides()` pairs entries with different `selection_key`; unpaired → `no_pair` |
| Additive vig removal | `api/app/services/ev.py:56-71` | `[p / total for p in implied_probs]` |
| Both Pinnacle sides required | `api/app/services/ev.py:250` | `if sharp_a_price is not None and sharp_b_price is not None` |
| All markets treated identically | `api/app/services/ev.py:212-294` | Same devig formula for spreads, totals, ML, player props |
| No longshot adjustment | Nowhere | No thresholds, caps, or warnings on high-implied-prob-discount bets |
| No fair-odds sanity check | Nowhere | Devigged fair odds are never compared against market consensus |
| All books equally valid for EV display | `api/app/services/ev.py:257-283` | Every book gets EV annotation regardless of quality |
| EV is ephemeral | `api/app/routers/fairbet/odds.py` | Computed per request, never stored |

### Dual SHARP_BOOKS Definitions (Inconsistency)

There are **two separate definitions** that are not synchronized:

- **API** (`api/app/services/ev.py:15`): `SHARP_BOOKS = {"Pinnacle"}` — used for EV calculation
- **Scraper** (`scraper/sports_scraper/odds/client.py:46`): `SHARP_BOOKS = {"pinnacle", "betfair_ex_eu", "betfair_ex_uk", "betfair_ex_au", "matchbook", "novig"}` — not used for anything currently

The scraper definition is dead code relative to EV. Only the API definition matters today.

---

## 2. Gaps & Risks

### 2.1 EV Is Currently Misleading For:

**Longshot markets (no guardrails)**
- A +1000 moneyline (implied ~9%) gets the same EV treatment as -110 (implied ~52%)
- Pinnacle's vig as a % of the implied probability is much larger on longshots
- Additive devig systematically overstates true probability on the favorite side and understates it on the dog side for lopsided markets
- No confidence discount, no warning, no cap

**Markets with thin Pinnacle coverage**
- If Pinnacle posts a line but doesn't actively trade it (e.g., NCAAB mid-major game), the "sharp" reference may be as stale as any retail book
- No freshness check on Pinnacle's `observed_at` relative to other books
- A Pinnacle line from 6 hours ago devigged against a FanDuel line from 5 minutes ago produces a meaningless EV number

**Player props**
- Pinnacle's player prop markets are much less liquid than mainlines
- The vig on Pinnacle player props can be 5-8% (vs 2-3% on mainlines)
- Additive devig on high-vig markets produces less reliable true probabilities
- Currently no differentiation — player prop EV looks identical to mainline EV in the UI

**Alternate lines**
- Alternate spreads/totals have wider vig than standard lines
- Pinnacle may not offer the same alternate line values as retail books
- Grouping by `(game_id, market_key, line_value)` means if Pinnacle has spread -3.5 but retail has alt spread -3.5, they may or may not land in the same group depending on `market_key` differences

### 2.2 Markets Where We Should Not Compute EV At All (Today)

| Market Type | Reason |
|------------|--------|
| Player props (NCAAB) | Pinnacle rarely posts NCAAB player props; no reference available |
| Period markets (halves/quarters) | Not currently ingested; if added, Pinnacle coverage is sparse |
| Game props (miscellaneous) | Catch-all category; no reliable sharp reference |
| Any market with <3 qualifying books | Statistical noise, not signal |
| Any market where Pinnacle line is >2 hours stale | Stale reference invalidates the calculation |

### 2.3 Books That Contaminate Baselines — RESOLVED

20 books are excluded from both display and EV computation via `EXCLUDED_BOOKS` in `api/app/services/ev_config.py`. Exclusion is enforced at SQL query time (`WHERE book NOT IN (...)`) in `_build_base_filters()` and in the eligibility gate's `min_qualifying_books` check. Books are still ingested and persisted — exclusion is query-time only.

### 2.4 Minimum Book Threshold — RESOLVED

`min_qualifying_books = 3` is enforced per-side in the eligibility gate (`evaluate_ev_eligibility()`). Markets with fewer than 3 non-excluded books on either side get `ev_disabled_reason = "insufficient_books"`.

---

## 3. Integration Points

### 3.1 Where the EV Reference Selector Should Plug In

The natural integration point is **between Step 5 (grouping) and Step 6 (annotation)** in the FairBet API endpoint:

```
Current flow:
  Query rows → Group by bet definition → Group by market (both sides) → [HERE] → Compute EV → Sort → Return

What should happen at [HERE]:
  1. Filter out excluded books
  2. Check minimum qualifying book count
  3. Look up (league, market_type) → reference strategy
  4. Determine confidence tier
  5. Decide: compute EV, mark informational, or disable entirely
  6. Pass strategy + confidence to compute_ev_for_market()
```

Currently `compute_ev_for_market()` is a pure function that takes two book lists. It would need to accept:
- Which books are eligible as sharp references (not just hardcoded `SHARP_BOOKS`)
- A confidence tier to attach to results
- Whether to compute at all (vs returning `None` with a reason)

### 3.2 What Needs Refactoring vs Extension

**Refactoring required:**

| Component | Why |
|-----------|-----|
| `SHARP_BOOKS` in `ev.py` | Must become config-driven, not a constant. Must support (league, market_type) → book set mapping |
| `compute_ev_for_market()` | Must accept strategy config, return confidence metadata, handle "disabled" case |
| FairBet API query layer | Must filter excluded books before grouping, enforce min book threshold |
| `_build_base_filters()` in odds.py | Must support book exclusion at the SQL level for efficiency |

**Extension only (no breaking changes):**

| Component | What to add |
|-----------|-------------|
| Response models (`BookOdds`, `BetDefinition`) | Add `confidence_tier`, `ev_method`, `ev_disabled_reason` fields |
| `NormalizedOddsSnapshot` | No changes needed — classification already flows through |
| `classify_market()` | Already works correctly; no changes |
| Persistence layer | No changes in Phase 0 (EV is query-time only) |
| `FairbetGameOddsWork` schema | No changes needed — it stores all book data already |

### 3.3 Config Location

The EV reference config should live as a **static Python mapping** (like `PROP_MARKETS` in `client.py` or `PREFERRED_BOOKS` in `odds_events.py`), not in the database or env vars. Reasons:
- It changes infrequently (quarterly at most)
- It must be deterministic and version-controlled
- It's referenced in hot-path API queries
- It's shared between scraper (for filtering) and API (for calculation)

Natural home: a new module like `api/app/services/ev_config.py` or `shared/ev_config.py`.

---

## 4. Open Questions

### Data Quality

1. **How stale is "too stale" for a Pinnacle reference?** If Pinnacle's `observed_at` is 4 hours old but FanDuel's is 5 minutes old, the EV number is noise. What's the acceptable staleness window? Per market type?

2. **Do we have Pinnacle coverage data?** What % of our (league, market_type) combinations actually have Pinnacle on both sides? This determines how much EV we can even show. Specifically:
   - NBA mainlines: likely high coverage
   - NHL mainlines: likely high coverage
   - NCAAB mainlines: varies by game prominence
   - Player props (any league): unknown, likely spotty for NCAAB

3. **Are Pinnacle's prop lines actually sharp?** Pinnacle is unquestionably sharp on mainlines. On player props, their markets are thinner and higher-vig. Should we still treat Pinnacle as the reference for props, or should props get a different confidence tier entirely?

### Architecture

4. **Should excluded books be filtered at ingestion or query time?** Filtering at ingestion saves storage and compute but loses data flexibility. Filtering at query time is more flexible but means we're persisting and processing data we'll never show.

5. **Should EV ever be persisted?** Currently it's computed per-request. If we want historical EV tracking (e.g., "this bet was +3% EV when we first saw it"), we'd need to store it. Is that a future requirement?

6. **Where does the 3-book minimum apply?** At the API response level (hide bets with <3 qualifying books)? Or at the EV calculation level (compute EV but flag it as low-confidence if <3 books)?

### Scope

7. **What does "confidence tier" mean concretely?** Is it:
   - A label? (`high`, `medium`, `low`, `disabled`)
   - A number? (0.0-1.0 scale)
   - A display decision? (show EV, show EV with warning, hide EV)

8. **Does confidence affect only display or also computation?** If a market is "low confidence," do we still compute EV the same way but tag it? Or do we use a different formula (e.g., wider vig assumption)?

9. **Game flow narrative odds (`odds_events.py`) — in scope?** Currently uses `PREFERRED_BOOKS = ["fanduel", "draftkings", "betmgm", "caesars"]` for selecting which book's odds appear in game flow text. This is a separate system from FairBet EV. Should the reference model also govern narrative book selection, or is that out of scope?

---

## Appendix: File Reference

| Area | File | Key Lines |
|------|------|-----------|
| EV formulas | `api/app/services/ev.py` | 37-95 (formulas), 212-294 (market annotation) |
| EV config & strategies | `api/app/services/ev_config.py` | Full file (book lists, strategy map, eligibility result) |
| EV annotation in API | `api/app/routers/fairbet/odds.py` | Step 6 (grouping + `_pair_opposite_sides` + `_annotate_pair_ev`) |
| Sharp books (API) | `api/app/services/ev_config.py` | `eligible_sharp_books` on each strategy |
| Sharp books (scraper, unused) | `scraper/sports_scraper/odds/client.py` | 46 (`SHARP_BOOKS`) |
| Market classification | `scraper/sports_scraper/models/schemas.py` | 123-142 (`classify_market`) |
| Snapshot model | `scraper/sports_scraper/models/schemas.py` | 102-121 (`NormalizedOddsSnapshot`) |
| Persistence (sports_game_odds) | `scraper/sports_scraper/persistence/odds.py` | 42-99 (two-row upsert) |
| Persistence (fairbet work) | `scraper/sports_scraper/odds/fairbet.py` | 118-203 (upsert), 57-116 (selection key) |
| FairBet work table schema | `api/app/db/odds.py` | 84-132 |
| SportsGameOdds schema | `api/app/db/odds.py` | 27-82 (includes `raw_payload` JSONB) |
| Game flow book selection | `api/app/services/odds_events.py` | 35-67 (`PREFERRED_BOOKS`, `select_preferred_book`) |
| Prop markets per sport | `scraper/sports_scraper/odds/client.py` | 52-68 (`PROP_MARKETS`) |
| Props fetching | `scraper/sports_scraper/odds/client.py` | 484-559 (`fetch_event_props`) |
| Props parsing | `scraper/sports_scraper/odds/client.py` | 561-639 (`_parse_prop_event`) |
| Odds config | `scraper/sports_scraper/config.py` | 20-32 (`OddsProviderConfig`) |
| Celery beat schedule | `scraper/sports_scraper/celery_app.py` | 78-135 (schedule definitions) |
| Migration (prop expansion) | `api/alembic/versions/20260215_000001_expand_odds_for_props.py` | Full file |
