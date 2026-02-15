# EV Lifecycle — Sharp Book EV Baseline Framework

How expected value (EV) is computed end-to-end in the FairBet pipeline.
This document should allow a human to manually compute EV for one bet and match the system.

---

## 1. Odds Ingestion

All odds are ingested via The Odds API into the `sports_game_odds` table, then upserted into the `fairbet_game_odds_work` work table for FairBet display. **All books are ingested** — no filtering at ingestion time. Each row stores:

- `game_id` — FK to `sports_games`
- `book` — Display name (e.g., "Pinnacle", "DraftKings")
- `market_key` — Market identifier (e.g., "spreads", "h2h", "player_points")
- `selection_key` — Selection identifier (e.g., "team:lakers", "total:over")
- `line_value` — Point line (0.0 for moneyline)
- `price` — American odds (e.g., -110, +150)
- `observed_at` — Timestamp when the odds were recorded
- `market_category` — One of: `mainline`, `player_prop`, `team_prop`, `alternate`, `period`, `game_prop`

## 2. Market Grouping

At query time, the FairBet endpoint groups rows into **bet definitions** keyed by:

```
(game_id, market_key, selection_key, line_value)
```

Each bet definition collects all book prices for that specific bet.

To compute EV, bet definitions are further grouped into **candidate buckets** keyed by:

```
(game_id, market_key, abs(line_value))
```

Within each bucket, the `_pair_opposite_sides()` helper pairs entries that have **different `selection_key` values** (e.g., `team:lakers` vs `team:celtics`). This ensures that only actual opposite sides of a two-way market are paired — even when `abs()` groups multiple alt lines into the same bucket.

- **Paired entries** proceed to EV computation (e.g., Lakers -3.5 / Celtics +3.5).
- **Unpaired entries** (no valid opposite side found) get `ev_disabled_reason = "no_pair"`.

## 3. Book Qualification & Exclusion

23 books are excluded from both display and EV computation via SQL-level filtering:

```sql
WHERE book NOT IN ('BetOnline.ag', 'BetRivers', 'BetUS', 'Bovada', ...)
```

The full exclusion list is defined in `api/app/services/ev_config.py` as `EXCLUDED_BOOKS`. These books are still ingested and persisted — exclusion is query-time only.

The remaining ~17 included books are the ones that appear in API responses and participate in EV calculation.

## 4. EV Eligibility Gating

Before computing EV, each two-way market passes through an eligibility gate (`evaluate_ev_eligibility()`). Four checks run in order:

### Check 1: Strategy Exists

```python
config = get_strategy(league_code, market_category)
# If None → disabled_reason = "no_strategy"
```

The strategy map (`ev_config.py`) maps `(league, market_category)` → `EVStrategyConfig | None`. `period` and `game_prop` markets return `None` (EV disabled).

### Check 2: Sharp Book Present

```python
sharp_a = _find_sharp_entry(side_a_books, config.eligible_sharp_books)
sharp_b = _find_sharp_entry(side_b_books, config.eligible_sharp_books)
# If either is None → disabled_reason = "reference_missing"
```

Currently, `eligible_sharp_books = ("Pinnacle",)` for all strategies. Pinnacle must have a price on **both sides** of the market.

### Check 3: Freshness

```python
oldest = min(sharp_a.observed_at, sharp_b.observed_at)
age_seconds = (now - oldest).total_seconds()
# If age_seconds > config.max_reference_staleness_seconds → disabled_reason = "reference_stale"
```

Staleness limits:
- Mainline NBA/NHL: 3600s (1 hour)
- Mainline NCAAB: 1800s (30 minutes)
- All props/alternates: 1800s (30 minutes)

### Check 4: Minimum Qualifying Books

```python
qualifying_a = count(b for b in side_a if b.book not in EXCLUDED_BOOKS)
qualifying_b = count(b for b in side_b if b.book not in EXCLUDED_BOOKS)
# If either < config.min_qualifying_books → disabled_reason = "insufficient_books"
```

All strategies start with `min_qualifying_books = 3`.

## 5. RAW_EV Computation

If eligibility passes, `compute_ev_for_market()` runs. The inputs are:
- `side_a_books`: All book entries for side A (already filtered to included books)
- `side_b_books`: All book entries for side B
- `strategy_config`: The `EVStrategyConfig` from the eligibility gate

### Step 5a: Find Sharp Prices

```python
sharp_a_price = Pinnacle's price on side A  # e.g., -110
sharp_b_price = Pinnacle's price on side B  # e.g., -110
```

### Step 5b: Convert to Implied Probabilities

```python
implied_a = american_to_implied(sharp_a_price)
implied_b = american_to_implied(sharp_b_price)
```

For American odds:
- If price >= 100: `implied = 100 / (price + 100)`
- If price <= -100: `implied = |price| / (|price| + 100)`

Example: -110 → `110 / (110 + 100)` = 0.5238

## 6. Devig & Final Math

### Additive Normalization (Remove Vig)

```python
total = implied_a + implied_b  # e.g., 0.5238 + 0.5238 = 1.0476
true_prob_a = implied_a / total  # e.g., 0.5238 / 1.0476 = 0.5000
true_prob_b = implied_b / total  # e.g., 0.5238 / 1.0476 = 0.5000
```

The sum of implied probabilities exceeds 1.0 by the vig (4.76% in this case). Normalization distributes the vig equally across outcomes.

### EV Calculation

For each book's price on each side:

```python
# Convert book price to decimal odds
if book_price >= 100:
    decimal_odds = (book_price / 100) + 1.0
elif book_price <= -100:
    decimal_odds = (100 / |book_price|) + 1.0

ev_percent = (decimal_odds * true_prob - 1.0) * 100.0
```

Example: DraftKings has -105 on side A, true_prob_a = 0.5000
- decimal_odds = (100 / 105) + 1.0 = 1.9524
- ev_percent = (1.9524 * 0.5000 - 1.0) * 100 = -2.38%

Example: FanDuel has +105 on side A, true_prob_a = 0.5000
- decimal_odds = (105 / 100) + 1.0 = 2.0500
- ev_percent = (2.0500 * 0.5000 - 1.0) * 100 = +2.50%

### Annotation

Each book entry gets annotated with:
- `ev_percent` — The EV percentage (positive = value, negative = bad)
- `implied_prob` — The book's raw implied probability (before devig)
- `true_prob` — The devigged true probability
- `is_sharp` — Whether this book is a sharp reference

Each bet definition gets:
- `ev_method` — e.g., "pinnacle_devig"
- `ev_confidence_tier` — "high", "medium", or "low"

## 7. EV Disabled Scenarios

When EV cannot be computed, the bet definition carries:

| `ev_disabled_reason` | Meaning | Common Cause |
|---|---|---|
| `no_strategy` | No strategy configured for this (league, market_category) | `period` or `game_prop` market |
| `no_pair` | No valid opposite side found for pairing | Single-sided market, or all entries in the `abs(line_value)` bucket share the same `selection_key` |
| `reference_missing` | Sharp book (Pinnacle) not present on one or both sides | Low-liquidity market, Pinnacle doesn't offer this line |
| `reference_stale` | Sharp book data is too old | Odds haven't been refreshed recently |
| `insufficient_books` | Too few qualifying books on a side | Niche market with limited book coverage |
| `fair_odds_outlier` | Devigged fair odds diverge too far from book median | Longshot markets, stale one-sided Pinnacle data, high-vig props |

When disabled, `ev_percent` is `null` on all BookOdds entries, but `ev_disabled_reason` and `ev_confidence_tier` may be present on the BetDefinition.

## 8. Confidence Tiers & Meaning

| Tier | Meaning | Typical Markets |
|---|---|---|
| `high` | Pinnacle vig is ~2-3%, line is heavily bet, devig is reliable | NBA/NHL mainlines (spread, moneyline, total) |
| `medium` | Pinnacle line exists but with higher vig or less liquidity | NCAAB mainlines, team props |
| `low` | Pinnacle vig is 5-8%, line may be thin, use EV directionally | Player props, alternates |

Key rule: **Player props can never be HIGH confidence.** Pinnacle's prop vig (5-8%) makes devigged probabilities unreliable for high-confidence decisions.

Confidence tier is set at the strategy level, not computed dynamically.

## 9. Known Limitations

1. **Two-way markets only.** Three-way markets (e.g., soccer draw) are not supported. Markets with 1 or 3+ sides get no EV.

2. **Single sharp book.** Only Pinnacle is used as the reference. Future: consensus strategy averaging multiple sharp books.

3. **Additive normalization only.** Other devig methods (multiplicative, power, Shin) are not implemented. Additive is simplest and works well for two-way markets.

4. **EV not persisted.** EV is computed at query time on every request. No historical EV tracking.

5. **No CLV (Closing Line Value) tracking.** We don't yet compare opening vs closing EV.

6. **Static staleness thresholds.** Staleness limits are hardcoded per strategy, not dynamically adjusted based on market conditions or time-to-game.

7. **No line movement detection.** A sharp line that moved significantly since `observed_at` may still be within the staleness window.

8. **Book list maintenance is manual.** `EXCLUDED_BOOKS` and `INCLUDED_BOOKS` are version-controlled constants, not database-driven.
