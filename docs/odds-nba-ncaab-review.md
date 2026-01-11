# NBA & NCAAB Odds Integration Review

This document summarizes the existing odds ingestion patterns for NBA and NCAAB so that NHL odds can mirror the same behavior.

## Components & Flow

1. **Odds API client**
   - The Odds API (v4) client lives in `scraper/bets_scraper/odds/client.py`.
   - Live odds are pulled via `/sports/{sport}/odds` for upcoming games.
   - Historical odds are pulled via `/historical/sports/{sport}/odds` for past dates.
   - Caching is enabled under the scraper HTML cache directory (per-league, per-date JSON).

2. **Polling / ingestion jobs**
   - Odds are fetched by `OddsSynchronizer` (`scraper/bets_scraper/odds/synchronizer.py`).
   - Runs occur either as part of scheduled ingestion or ad-hoc backfills (`run_manager.py`).
   - Live endpoints are used for today/future; historical endpoints are used for past dates.

3. **Normalization & mapping**
   - Team normalization uses `normalize_team_name` in `scraper/bets_scraper/normalization/__init__.py`.
   - Odds market keys map to canonical markets:
     - `spreads` → `spread`
     - `totals` → `total`
     - `h2h` → `moneyline`

4. **Persistence**
   - `upsert_odds` (`scraper/bets_scraper/persistence/odds.py`) matches odds to games by:
     1. Team IDs (exact and swapped).
     2. Team names (NCAAB uses normalized matching; other leagues use exact).
   - Odds are stored in `sports_game_odds` with uniqueness on `(game_id, book, market_type, side, is_closing_line)`.

## Supported Markets

- **Spread** (NBA and NCAAB): canonical `spread` market derived from The Odds API `spreads`.
- **Total**: canonical `total` market derived from The Odds API `totals`.
- **Moneyline**: canonical `moneyline` market derived from The Odds API `h2h`.

## Bookmaker Filtering

- Optional bookmaker filtering is passed in via `IngestionConfig.include_books`.
- If `include_books` is unset, all bookmakers returned by The Odds API are accepted.

## Update Cadence

- Live odds: fetched for today/future games on scheduled or manual runs.
- Historical odds: fetched day-by-day for past dates (rate-limited with a short delay every 5 days).

## Game Matching & Team Resolution

- Team names are normalized to canonical values (NBA mappings are exhaustive; NCAAB is partial by design).
- NCAAB includes special normalized matching and limited canonical overrides to handle frequent naming variations.

## Required vs Optional Fields

**Required** (for ingestion to persist):
- `league_code`
- `book`
- `market_type` (spread/total/moneyline)
- `side` (team name or outcome label)
- `price`
- `observed_at`
- `home_team` / `away_team` (normalized identities)
- `game_date`

**Optional**:
- `line` (required for spreads/totals, optional for moneylines)
- `source_key`
- `raw_payload`

## Key Assumptions

- One outcome per team per market per book (stored as one row per side).
- The Odds API event payloads include `home_team`, `away_team`, and `commence_time`.
- NBA and NCAAB markets are full-game only; no period-level markets are ingested.

## What NHL Must Replicate Exactly

- Use the same The Odds API client and endpoints.
- Preserve the canonical market mapping (`spread`, `total`, `moneyline`).
- Persist odds via `upsert_odds` with the same matching logic.
- Respect the same bookmaker filter behavior and caching strategy.
- Skip malformed outcomes (missing side/price or missing line for spread/total).

## Where Sport-Specific Differences Are Allowed

- Team name normalization mappings (NHL-specific abbreviations, aliases).
- Close-line snapshot timing values (if NHL needs a different closing hour).
- Team naming quirks from The Odds API (only if required for correct matching).
