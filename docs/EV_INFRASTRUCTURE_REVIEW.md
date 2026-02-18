# Sharp Book EV Baseline Framework — Codebase Review

**Date:** 2026-02-14
**Scope:** NBA, NHL, NCAAB — mainlines, game/team props, player props
**Purpose:** Understand the terrain before building. No solutions proposed.

> **Note:** This is a historical review snapshot. For the current system behavior including recent fixes (DB team names for selection keys, NCAAB matching tightening, validation guards), see [Odds & FairBet Pipeline](ODDS_AND_FAIRBET.md).

---

## 1. Current-State Summary

### How EV Is Computed Today

EV is computed **at query time only**, inside the FairBet API endpoint (`api/app/routers/fairbet/odds.py:319-378`). Nothing is persisted.

The pipeline:

1. **Group bets** by `(game_id, market_key, abs(line_value))` — forms candidate buckets
2. **Pair opposite sides** via `_pair_opposite_sides()` — within each bucket, pairs entries with different `selection_key` values; unpaired entries get `ev_disabled_reason = "no_pair"`
3. **Eligibility gate** (`evaluate_ev_eligibility()`) — checks strategy exists, Pinnacle present on both sides, freshness, minimum book count
4. **Find Pinnacle** on each side (`ev.py`) — first match wins
5. **Devig** both Pinnacle prices via additive normalization (`ev.py:74-89`) — divide each implied prob by the sum
6. **Compute EV%** for every book using `(decimal_odds * true_prob - 1) * 100` (`ev.py:92-116`)
7. **Annotate** each book entry with `ev_percent`, `implied_prob`, `is_sharp`, `true_prob`

### Where Assumptions Live

| Assumption | Location | Detail |
|-----------|----------|--------|
| Pinnacle is the only sharp book | `api/app/services/ev_config.py` | `eligible_sharp_books = ("Pinnacle",)` on all strategies |
| Two-way markets only | `api/app/routers/fairbet/odds.py` | `_pair_opposite_sides()` pairs entries with different `selection_key`; unpaired → `no_pair` |
| Additive vig removal | `api/app/services/ev.py:74-89` | `[p / total for p in implied_probs]` |
| Both Pinnacle sides required | `api/app/services/ev.py:282` | `if sharp_a_price is not None and sharp_b_price is not None` |
| All markets treated identically | `api/app/services/ev.py:244-348` | Same devig formula for spreads, totals, ML, player props |
| No longshot adjustment | Nowhere | No thresholds, caps, or warnings on high-implied-prob-discount bets |
| Fair-odds sanity check | `api/app/services/ev.py:317-336` | Devigged fair odds compared against median book price; flags `fair_odds_suspect` if divergence exceeds threshold |
| All books equally valid for EV display | `api/app/services/ev.py:290-315` | Every book gets EV annotation regardless of quality |
| EV is ephemeral | `api/app/routers/fairbet/odds.py` | Computed per request, never stored |

### Sharp Book Configuration — RESOLVED

Sharp book selection is now centralized in `api/app/services/ev_config.py`. Each `EVStrategyConfig` declares its own `eligible_sharp_books` tuple (currently `("Pinnacle",)` for all strategies). The old `SHARP_BOOKS` constant in `ev.py` has been removed. The scraper-side `SHARP_BOOKS` in `scraper/sports_scraper/odds/client.py` is an API-key-tier label list unrelated to EV computation.

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

### 3.1 EV Reference Selector — IMPLEMENTED

The eligibility gate sits between market grouping and EV computation in the FairBet API endpoint:

```
Current flow:
  Query rows → Group by bet definition → Pair opposite sides → evaluate_ev_eligibility() → compute_ev_for_market() → Sort → Return
```

`evaluate_ev_eligibility()` performs four checks in order: strategy exists, sharp book present on both sides, freshness within staleness window, minimum qualifying books. On failure it returns an `EligibilityResult` with a `disabled_reason`.

`compute_ev_for_market()` accepts an `EVStrategyConfig`, returns confidence metadata, and includes a fair-odds sanity check.

### 3.2 Completed Refactoring

| Component | Status |
|-----------|--------|
| Sharp book selection | Config-driven via `EVStrategyConfig.eligible_sharp_books` per strategy |
| `compute_ev_for_market()` | Accepts `EVStrategyConfig`, returns `EVComputeResult` with confidence tier and `fair_odds_suspect` flag |
| Book exclusion | `EXCLUDED_BOOKS` frozenset filtered at SQL query time via `_build_base_filters()` |
| Response models | `BookOdds` and `BetDefinition` include `confidence_tier`, `ev_method`, `ev_disabled_reason` |

### 3.3 Config Location — IMPLEMENTED

EV strategy config lives in `api/app/services/ev_config.py` as a static Python mapping. The module defines:
- `EXCLUDED_BOOKS` and `INCLUDED_BOOKS` frozensets
- `EVStrategyConfig` frozen dataclass
- `get_strategy(league, market_category)` lookup function
- `evaluate_ev_eligibility()` (in `ev.py`, using config from `ev_config.py`)

---

## 4. Open Questions

### Resolved Questions

1. **Staleness window** — Implemented per-strategy: NBA/NHL mainlines 3600s, NCAAB mainlines 1800s, all props/alternates 1800s.

2. **Book exclusion** — Query-time filtering via `EXCLUDED_BOOKS` frozenset. Books are still ingested and persisted for flexibility.

3. **3-book minimum** — Enforced at the EV calculation level per-side in `evaluate_ev_eligibility()`. Markets with <3 non-excluded books get `ev_disabled_reason = "insufficient_books"`.

4. **Confidence tier** — A string label (`high`, `medium`, `low`) set per-strategy. Same devig formula is used regardless; the tier is metadata for consumer display decisions.

### Open Questions

1. **Do we have Pinnacle coverage data?** What % of our (league, market_type) combinations actually have Pinnacle on both sides? This determines how much EV we can even show.

2. **Are Pinnacle's prop lines actually sharp?** Pinnacle is unquestionably sharp on mainlines. On player props, their markets are thinner and higher-vig. Currently treated as `low` confidence tier.

3. **Should EV ever be persisted?** Currently computed per-request. Historical EV tracking would require storage.

4. ~~**Game flow narrative odds (`odds_events.py`) — in scope?**~~ Resolved: Timeline odds integration implemented (2026-02-11). Uses `PREFERRED_BOOKS` for selecting which book's odds appear in game flow text. Separate system from FairBet EV.

---

## Appendix: File Reference

| Area | File | Key Lines |
|------|------|-----------|
| EV formulas | `api/app/services/ev.py` | 38-116 (formulas), 244-348 (market annotation) |
| EV config & strategies | `api/app/services/ev_config.py` | Full file (book lists, strategy map, eligibility result) |
| EV annotation in API | `api/app/routers/fairbet/odds.py` | Step 6 (grouping + `_pair_opposite_sides` + `_annotate_pair_ev`) |
| Sharp books (API) | `api/app/services/ev_config.py` | `eligible_sharp_books` on each strategy, `EXCLUDED_BOOKS`, `INCLUDED_BOOKS` |
| Sharp books (scraper) | `scraper/sports_scraper/odds/client.py` | `SHARP_BOOKS` (API-tier label, not used for EV) |
| Market classification | `scraper/sports_scraper/models/schemas.py` | 123-142 (`classify_market`) |
| Snapshot model | `scraper/sports_scraper/models/schemas.py` | 102-121 (`NormalizedOddsSnapshot`) |
| Persistence (sports_game_odds) | `scraper/sports_scraper/persistence/odds.py` | 42-99 (two-row upsert) |
| Persistence (fairbet work) | `scraper/sports_scraper/odds/fairbet.py` | upsert_fairbet_odds (uses DB team names + validation guard), build_selection_key |
| FairBet work table schema | `api/app/db/odds.py` | 84-132 |
| SportsGameOdds schema | `api/app/db/odds.py` | 27-82 (includes `raw_payload` JSONB) |
| Game flow book selection | `api/app/services/odds_events.py` | 35-67 (`PREFERRED_BOOKS`, `select_preferred_book`) |
| Prop markets per sport | `scraper/sports_scraper/odds/client.py` | 52-68 (`PROP_MARKETS`) |
| Props fetching | `scraper/sports_scraper/odds/client.py` | 484-559 (`fetch_event_props`) |
| Props parsing | `scraper/sports_scraper/odds/client.py` | 561-639 (`_parse_prop_event`) |
| Odds config | `scraper/sports_scraper/config.py` | 20-32 (`OddsProviderConfig`) |
| Celery beat schedule | `scraper/sports_scraper/celery_app.py` | 78-135 (schedule definitions) |
| Schema (odds + props) | `api/alembic/versions/20260218_000001_baseline_squash.py` | `sports_game_odds` and `fairbet_game_odds_work` tables |
