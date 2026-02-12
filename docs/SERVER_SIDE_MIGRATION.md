# Server-Side Migration Guide

> Moving client-side computation to the admin backend so consumer apps become thin display layers.

**Status:** All 6 phases are **implemented and production-ready**.

---

## Table of Contents

1. [Motivation](#motivation)
2. [Architecture Overview](#architecture-overview)
3. [Phase 1 — Team Colors](#phase-1--team-colors)
4. [Phase 2 — Derived Metrics (Odds)](#phase-2--derived-metrics-odds)
5. [Phase 3 — Period Labels](#phase-3--period-labels)
6. [Phase 4 — Play Tiers](#phase-4--play-tiers)
7. [Phase 5 — Admin UI](#phase-5--admin-ui)
8. [Phase 6 — Timeline Merging](#phase-6--timeline-merging)
9. [Swift App Migration Path](#swift-app-migration-path)
10. [API Reference Summary](#api-reference-summary)
11. [Testing & Verification](#testing--verification)
12. [File Index](#file-index)

---

## Motivation

The Swift app (`scroll-down-app`) performs ~2,000 lines of deterministic computation on every render that should live server-side. This causes:

| Problem | Impact |
|---------|--------|
| **Duplicated logic** | Any new consumer must reimplement odds math, tier classification, color mapping, and period labels |
| **Wasted bandwidth** | API computes `derivedMetrics` but Swift ignores them, recomputing everything from raw odds |
| **Inconsistency risk** | Period labels have 4 implementations in Swift; 2 are buggy (hardcoded "Q" for all sports) |
| **No central color source** | 430+ teams' colors hardcoded in Swift (742 lines) with no single source of truth |
| **Opaque admin data** | Admin browser doesn't show computed values that app developers need to verify |

**Goal:** The admin backend is the single source of truth for all derived data. Consumer apps become thin display layers that read pre-computed values from the API.

---

## Architecture Overview

```
                    ┌─────────────────────────────────┐
                    │       sports-data-admin          │
                    │                                  │
                    │  ┌──────────┐  ┌──────────────┐  │
  Raw Data ──────►  │  │ Scraper  │  │  PostgreSQL   │  │
  (APIs, sites)     │  │ (Celery) │──│  (source of   │  │
                    │  └──────────┘  │   truth)      │  │
                    │                └──────┬───────┘  │
                    │                       │          │
                    │  ┌────────────────────▼───────┐  │
                    │  │      FastAPI Backend        │  │
                    │  │                             │  │
                    │  │  team_colors.py             │  │
                    │  │  derived_metrics.py         │  │
                    │  │  period_labels.py           │  │
                    │  │  play_tiers.py              │  │
                    │  │  odds_events.py             │  │
                    │  │  timeline_generator.py      │  │
                    │  └─────────┬───────────────────┘  │
                    │            │                      │
                    │  ┌─────────▼───────────────────┐  │
                    │  │   Admin UI (Next.js)         │  │
                    │  │   Verification dashboard     │  │
                    │  └─────────────────────────────┘  │
                    └────────────┬──────────────────────┘
                                 │
                    ┌────────────▼──────────────────────┐
                    │     Consumer Apps                  │
                    │     (scroll-down-app, etc.)        │
                    │     Read pre-computed values only   │
                    └───────────────────────────────────┘
```

Every field that a consumer needs is computed once, server-side, and returned in the API response. Consumers never recompute.

---

## Phase 1 — Team Colors

### What It Does

Stores team colors in the database and serves them via API, replacing 742 lines of hardcoded Swift color dictionaries. Includes clash detection for matchups where both teams have visually similar colors.

### Database Schema

Two columns added to `sports_teams`:

| Column | Type | Example |
|--------|------|---------|
| `color_light_hex` | `VARCHAR(7)`, nullable | `#552583` |
| `color_dark_hex` | `VARCHAR(7)`, nullable | `#FDB927` |

Migration: `sql/versions/20260211_000002_add_team_colors.py`

### API Endpoints

#### `GET /teams`

Returns all teams with color fields.

```json
{
  "teams": [
    {
      "id": 1,
      "name": "Los Angeles Lakers",
      "shortName": "Lakers",
      "abbreviation": "LAL",
      "leagueCode": "NBA",
      "gamesCount": 45,
      "colorLightHex": "#552583",
      "colorDarkHex": "#FDB927"
    }
  ],
  "total": 430
}
```

#### `GET /teams/{teamId}`

Returns full team detail including colors.

```json
{
  "id": 1,
  "name": "Los Angeles Lakers",
  "shortName": "Lakers",
  "abbreviation": "LAL",
  "leagueCode": "NBA",
  "colorLightHex": "#552583",
  "colorDarkHex": "#FDB927",
  "recentGames": [...]
}
```

#### `PATCH /teams/{teamId}/colors`

Update team colors (admin operation).

**Request:**
```json
{
  "colorLightHex": "#552583",
  "colorDarkHex": "#FDB927"
}
```

Both fields are optional — send only the one you want to update.

### Matchup Color Clash Detection

The `team_colors.py` utility module provides color clash resolution:

```python
from app.services.team_colors import get_matchup_colors

colors = get_matchup_colors(
    home_color_light="#C8102E",   # Rockets red
    home_color_dark="#FFFFFF",
    away_color_light="#CE1141",   # Bulls red (very similar)
    away_color_dark="#FFFFFF",
)
# Returns: home yields to neutral (#000000/#FFFFFF) when distance < 0.12
```

| Function | Purpose |
|----------|---------|
| `hex_to_rgb(hex)` | Convert `#RRGGBB` to normalized `(r, g, b)` tuple |
| `color_distance(c1, c2)` | Euclidean distance in RGB space, normalized 0.0-1.0 |
| `get_matchup_colors(...)` | Resolve clashes — home team yields to neutral black/white |

**Clash threshold:** `0.12` (normalized RGB distance). This matches the Swift implementation.

### Consumer Migration

**Swift lines removed:** ~742

1. Delete `GameTheme.swift` color dictionaries
2. Fetch team colors from `GET /teams` on app launch (cache locally)
3. For matchups, either:
   - Call `get_matchup_colors()` server-side and include in a matchup endpoint, OR
   - Port the simple clash logic client-side (3 functions, ~30 lines)

### Key Files

| File | Purpose |
|------|---------|
| `api/app/db/sports.py` | `SportsTeam.color_light_hex`, `color_dark_hex` fields |
| `api/app/services/team_colors.py` | Clash detection utilities |
| `api/app/routers/sports/teams.py` | `GET /teams`, `GET /teams/{id}`, `PATCH /teams/{id}/colors` |
| `api/app/routers/sports/schemas.py` | `TeamSummary`, `TeamDetail`, `TeamColorUpdate` |

---

## Phase 2 — Derived Metrics (Odds)

### What It Does

Computes 40+ derived metrics from raw odds and game scores server-side. Covers spread analysis, totals, moneyline, line movement, cover outcomes, and display-ready labels. Consumers read pre-computed values instead of doing odds math on-device.

### How It Works

`compute_derived_metrics(game, odds)` runs on every game detail/list request. It:

1. Selects closing and opening lines for spread, total, and moneyline markets
2. Matches odds `side` values to home/away teams using name/abbreviation/short_name
3. Computes outcome metrics (cover, over/under, upset) for final games
4. Generates display labels ready for rendering

### API Response

Included in both `GET /games` (list) and `GET /games/{gameId}` (detail) responses:

```json
{
  "derivedMetrics": {
    "home_score": 112,
    "away_score": 108,
    "margin_of_victory": 4,
    "combined_score": 220,
    "winner": "home",

    "closing_spread_home": -3.5,
    "closing_spread_home_price": -110,
    "closing_spread_away": 3.5,
    "closing_spread_away_price": -110,
    "opening_spread_home": -2.5,
    "opening_spread_away": 2.5,
    "line_movement_spread": -1.0,
    "did_home_cover": true,
    "did_away_cover": false,

    "closing_total": 215.5,
    "closing_total_price": -110,
    "opening_total": 214.0,
    "line_movement_total": 1.5,
    "total_result": "over",

    "closing_ml_home": -150,
    "closing_ml_home_implied": 0.6,
    "closing_ml_away": 130,
    "closing_ml_away_implied": 0.4348,
    "opening_ml_home": -140,
    "opening_ml_away": 120,
    "moneyline_upset": false,

    "pregame_spread_label": "LAL -3.5 (-110)",
    "pregame_total_label": "O/U 215.5 (-110)",
    "pregame_ml_home_label": "LAL -150",
    "pregame_ml_away_label": "GSW +130",
    "spread_outcome_label": "LAL covered by 0.5",
    "total_outcome_label": "Over by 4.5",
    "ml_outcome_label": "LAL won (-150)"
  }
}
```

### Complete Metrics Reference

#### Score Metrics
| Key | Type | Description |
|-----|------|-------------|
| `home_score` | `int` | Home team final score |
| `away_score` | `int` | Away team final score |
| `margin_of_victory` | `int` | `home_score - away_score` (positive = home win) |
| `combined_score` | `int` | `home_score + away_score` |
| `winner` | `string` | `"home"`, `"away"`, or `"tie"` |

#### Spread Metrics
| Key | Type | Description |
|-----|------|-------------|
| `closing_spread_home` | `float` | Closing spread for home team (e.g., `-3.5`) |
| `closing_spread_away` | `float` | Closing spread for away team (e.g., `3.5`) |
| `closing_spread_home_price` | `float` | American odds price for home spread |
| `closing_spread_away_price` | `float` | American odds price for away spread |
| `opening_spread_home` | `float` | Opening spread for home team |
| `opening_spread_away` | `float` | Opening spread for away team |
| `opening_spread_home_price` | `float` | American odds price for opening home spread |
| `opening_spread_away_price` | `float` | American odds price for opening away spread |
| `line_movement_spread` | `float` | `closing - opening` (negative = moved toward home) |
| `did_home_cover` | `bool` | Home team covered the closing spread |
| `did_away_cover` | `bool` | Away team covered the closing spread |

#### Total Metrics
| Key | Type | Description |
|-----|------|-------------|
| `closing_total` | `float` | Closing over/under line |
| `closing_total_price` | `float` | American odds price for closing total |
| `opening_total` | `float` | Opening over/under line |
| `opening_total_price` | `float` | American odds price for opening total |
| `line_movement_total` | `float` | `closing - opening` |
| `total_result` | `string` | `"over"`, `"under"`, or `"push"` |

#### Moneyline Metrics
| Key | Type | Description |
|-----|------|-------------|
| `closing_ml_home` | `float` | Closing moneyline for home (American odds) |
| `closing_ml_away` | `float` | Closing moneyline for away (American odds) |
| `closing_ml_home_implied` | `float` | Implied probability 0.0-1.0 |
| `closing_ml_away_implied` | `float` | Implied probability 0.0-1.0 |
| `opening_ml_home` | `float` | Opening moneyline for home |
| `opening_ml_away` | `float` | Opening moneyline for away |
| `opening_ml_home_implied` | `float` | Implied probability 0.0-1.0 |
| `opening_ml_away_implied` | `float` | Implied probability 0.0-1.0 |
| `moneyline_upset` | `bool` | Winner was the underdog |

#### Display Labels
| Key | Type | Example |
|-----|------|---------|
| `pregame_spread_label` | `string` | `"LAL -3.5 (-110)"` |
| `pregame_total_label` | `string` | `"O/U 215.5 (-110)"` |
| `pregame_ml_home_label` | `string` | `"LAL -150"` |
| `pregame_ml_away_label` | `string` | `"GSW +130"` |
| `spread_outcome_label` | `string` | `"LAL covered by 0.5"` or `"Push"` |
| `total_outcome_label` | `string` | `"Over by 4.5"` or `"Push"` |
| `ml_outcome_label` | `string` | `"LAL won (-150)"` or `"GSW upset (+130)"` |

### Implied Probability Formula

```
If price > 0:  probability = 100 / (price + 100)
If price < 0:  probability = -price / (-price + 100)
```

### Graceful Degradation

- No odds at all: `derivedMetrics` contains only score metrics (or `{}` if no scores)
- Partial odds (e.g., only spread, no moneyline): only available metrics are populated
- Pre-game (no final score): pregame labels and opening/closing lines present, no outcome metrics

### Consumer Migration

**Swift lines removed:** ~170

1. Delete local odds computation in ViewModel
2. Read `derivedMetrics` from `GET /games/{gameId}` response
3. Use `pregame_spread_label`, `pregame_total_label`, etc. directly for display
4. Use `spread_outcome_label`, `total_outcome_label`, `ml_outcome_label` for outcome display

### Key Files

| File | Purpose |
|------|---------|
| `api/app/services/derived_metrics.py` | Core computation (280 lines) |
| `api/app/routers/sports/games.py` | Wired into `GET /games` and `GET /games/{id}` |
| `api/app/routers/sports/schemas.py` | `GameSummary.derived_metrics`, `GameDetailResponse.derived_metrics` |

---

## Phase 3 — Period Labels

### What It Does

Computes sport-aware period labels server-side so consumers don't need to know league rules. Eliminates 4 buggy Swift implementations (2 hardcoded "Q" for all sports).

### Label Formats

| League | Period | `periodLabel` | `timeLabel` |
|--------|--------|---------------|-------------|
| NBA | 1-4 | `Q1`-`Q4` | `Q4 2:35` |
| NBA | 5 | `OT` | `OT 3:12` |
| NBA | 6+ | `2OT`, `3OT`... | `2OT 1:45` |
| NCAAB | 1-2 | `H1`, `H2` | `H2 5:15` |
| NCAAB | 3 | `OT` | `OT 4:00` |
| NCAAB | 4+ | `2OT`, `3OT`... | `3OT 2:30` |
| NHL | 1-3 | `P1`-`P3` | `P3 12:00` |
| NHL | 4 | `OT` | `OT 3:45` |
| NHL | 5 | `SO` | `SO` |

### API Response

Every play in the `plays` array of `GET /games/{gameId}` now includes computed labels:

```json
{
  "plays": [
    {
      "playIndex": 42,
      "quarter": 3,
      "gameClock": "5:20",
      "periodLabel": "Q3",
      "timeLabel": "Q3 5:20",
      "playType": "made_shot",
      "teamAbbreviation": "LAL",
      "playerName": "L. James",
      "description": "L. James makes 24-foot three point shot",
      "homeScore": 68,
      "awayScore": 62,
      "tier": 1
    }
  ]
}
```

### Implementation

```python
# api/app/services/period_labels.py

def period_label(period: int, league_code: str) -> str:
    """Return display-ready period label. NBA: Q1-Q4, OT. NHL: P1-P3, OT, SO. NCAAB: H1, H2, OT."""

def time_label(period: int, game_clock: str | None, league_code: str) -> str:
    """Combine period label + game clock: 'Q4 2:35', 'P3 12:00', 'H2 5:15'."""
```

Labels are computed in `serialize_play_entry()` during API response serialization. No DB changes needed.

### Consumer Migration

**Swift lines removed:** ~120

1. Delete all 4 local period label implementations
2. Read `periodLabel` and `timeLabel` directly from each play object
3. No league-code branching needed on client side

### Key Files

| File | Purpose |
|------|---------|
| `api/app/services/period_labels.py` | `period_label()` and `time_label()` functions |
| `api/app/routers/sports/common.py` | `serialize_play_entry()` calls period_labels |
| `api/app/routers/sports/schemas.py` | `PlayEntry.period_label`, `PlayEntry.time_label` |

---

## Phase 4 — Play Tiers

### What It Does

Classifies every play-by-play event into Tier 1 (key scoring), Tier 2 (notable non-scoring), or Tier 3 (routine). Consumers can collapse routine plays and highlight key moments without duplicating classification logic.

### Tier Definitions

| Tier | Meaning | Criteria |
|------|---------|----------|
| **1** | Key scoring play | Scoring play AND any of: lead change, new tie, clutch time (<2 min final period), or final-period play |
| **2** | Notable non-scoring | Foul, turnover, steal, block, penalty, hit (league-specific types) |
| **3** | Routine | Everything else |

#### Tier 2 Play Types by League

| League | Play Types |
|--------|-----------|
| NBA | `foul`, `turnover`, `steal`, `block`, `offensive foul` |
| NCAAB | `personal_foul`, `shooting_foul`, `offensive_foul`, `technical_foul`, `flagrant_foul`, `foul`, `turnover`, `steal`, `block` |
| NHL | `penalty`, `delayed_penalty`, `takeaway`, `giveaway`, `hit` |

#### Final Period Threshold

| League | Final Period Starts At |
|--------|----------------------|
| NBA | Period 4 (Q4) |
| NCAAB | Period 2 (H2) |
| NHL | Period 3 (P3) |

**Clutch time:** < 2.0 minutes remaining in the final period.

### Grouped Plays (Tier 3 Collapsing)

Consecutive Tier-3 plays are grouped into collapsible summaries:

```json
{
  "groupedPlays": [
    {
      "startIndex": 45,
      "endIndex": 58,
      "playIndices": [45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58],
      "summaryLabel": "14 plays: foul, missed shot, turnover, rebound"
    }
  ]
}
```

### API Response

In `GET /games/{gameId}`:

```json
{
  "plays": [
    { "playIndex": 1, "tier": 1, "playType": "made_shot", ... },
    { "playIndex": 2, "tier": 3, "playType": "rebound", ... },
    { "playIndex": 3, "tier": 2, "playType": "foul", ... }
  ],
  "groupedPlays": [
    {
      "startIndex": 10,
      "endIndex": 15,
      "playIndices": [10, 11, 12, 13, 14, 15],
      "summaryLabel": "6 plays: rebound, missed shot, substitution"
    }
  ]
}
```

### Consumer Migration

**Swift lines removed:** ~337

1. Delete `PlayTier.swift` and all local tier classification
2. Read `tier` field from each play object (1, 2, or 3)
3. Use `groupedPlays` array to collapse Tier-3 sequences in the UI
4. Each `TieredPlayGroup` has `startIndex`/`endIndex` and a `summaryLabel`

### Key Files

| File | Purpose |
|------|---------|
| `api/app/services/play_tiers.py` | `classify_all_tiers()`, `group_tier3_plays()` |
| `api/app/routers/sports/games.py` | Wired into `GET /games/{id}` |
| `api/app/routers/sports/schemas.py` | `PlayEntry.tier`, `TieredPlayGroup` |

---

## Phase 5 — Admin UI

### What It Does

The web admin UI (`web/`) provides verification dashboards for all server-side computed values. This phase doesn't remove Swift lines — it gives developers confidence that the backend is correct before consumers adopt.

### Team Color Management

**Page:** `/admin/sports/teams/[id]`

- Color picker inputs for light and dark mode hex values
- Live color swatch preview with team abbreviation
- Matchup color preview (select opponent, see side-by-side light/dark comparisons)
- Save button persists via `PATCH /teams/{id}/colors`

### Derived Metrics Viewer

**Page:** `/admin/sports/games/[gameId]` (collapsible "Computed Fields" section)

- All 40+ derived metrics displayed grouped by category (Score, Spread, Total, Moneyline)
- Outcome labels highlighted with color-coded badges (green/red)
- Formatted values: booleans as "Yes"/"No", implied probabilities as percentages

### Play-by-Play with Tiers

**Page:** `/admin/sports/games/[gameId]` (PBP section)

- Tier badges (`T1`, `T2`, `T3`) with color coding on every play
- "Collapse Routine Plays" toggle groups consecutive Tier-3 plays
- Collapsed groups show: play count, play types, score range
- Click to expand and see individual plays within a group
- Quarter/period tabs with play counts per period

### Game Flow Viewer

**Page:** `/admin/sports/games/[gameId]` (Flow section)

- Narrative blocks displayed with semantic role badges (SETUP, MOMENTUM_SHIFT, etc.)
- Score progressions and period ranges per block
- Word count tracking for guardrail compliance
- Fallback to moment-based view for games without block narratives

---

## Phase 6 — Timeline Merging

### What It Does

Merges play-by-play events, social posts, and odds data into a unified chronological timeline. Consumers read the merged timeline from a single endpoint instead of fetching three data sources and assembling them client-side.

### Timeline Architecture

The timeline is a flat list of events sorted by:

1. **Phase order** (pregame < q1 < q2 < halftime < q3 < q4 < ot < postgame) — PRIMARY
2. **Intra-phase order** (clock progress for PBP, seconds offset for social/odds) — SECONDARY
3. **Event type tiebreaker** (pbp=0, odds=1, tweet=2 at same position) — TERTIARY

Three event types are merged:

| Type | Source | Phases | Required |
|------|--------|--------|----------|
| `pbp` | `SportsGamePlay` rows | All game phases | Yes (must have PBP data) |
| `tweet` | `TeamSocialPost` rows | Any phase | No (graceful degradation) |
| `odds` | `SportsGameOdds` rows | Pregame only | No (graceful degradation) |

### Odds Events

Up to 3 odds events are produced per game, all in the `pregame` phase:

#### `opening_line`

The earliest observed odds for the selected book.

```json
{
  "event_type": "odds",
  "phase": "pregame",
  "odds_type": "opening_line",
  "intra_phase_order": 120.0,
  "book": "fanduel",
  "markets": {
    "spread": { "side": "Lakers", "line": -3.5, "price": -110 },
    "total": { "side": "over", "line": 215.5, "price": -110 },
    "moneyline": { "side": "Lakers", "line": -150, "price": -150 }
  },
  "synthetic_timestamp": "2026-01-22T22:00:00+00:00"
}
```

#### `closing_line`

The last observed odds before game start.

```json
{
  "event_type": "odds",
  "phase": "pregame",
  "odds_type": "closing_line",
  "intra_phase_order": 7080.0,
  "book": "fanduel",
  "markets": {
    "spread": { "side": "Lakers", "line": -5.0, "price": -110 },
    "total": { "side": "over", "line": 216.0, "price": -110 }
  },
  "synthetic_timestamp": "2026-01-22T23:58:00+00:00"
}
```

#### `line_movement` (only if significant)

Emitted when any market moves beyond thresholds:

| Market | Threshold |
|--------|-----------|
| Spread | >= 1.0 point |
| Total | >= 1.0 point |
| Moneyline | >= 20 cents (American odds) |

```json
{
  "event_type": "odds",
  "phase": "pregame",
  "odds_type": "line_movement",
  "intra_phase_order": 3600.0,
  "book": "fanduel",
  "markets": { ... },
  "movements": [
    {
      "market_type": "spread",
      "side": "Lakers",
      "opening_line": -3.5,
      "closing_line": -5.0,
      "movement": -1.5
    }
  ],
  "synthetic_timestamp": "2026-01-22T22:59:00+00:00"
}
```

### Book Selection

A single book is selected for the timeline to avoid duplicate events. Priority:

1. FanDuel
2. DraftKings
3. BetMGM
4. Caesars
5. Fallback: book with the most rows

### API Endpoints

#### `GET /games/{gameId}/timeline`

Retrieve a persisted timeline artifact.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `timelineVersion` | `string` | `v1` | Timeline version to retrieve |

**Response (200):**
```json
{
  "gameId": 123,
  "sport": "NBA",
  "timelineVersion": "v1",
  "generatedAt": "2026-01-23T05:00:00Z",
  "timeline": [
    { "event_type": "odds", "phase": "pregame", "odds_type": "opening_line", ... },
    { "event_type": "odds", "phase": "pregame", "odds_type": "closing_line", ... },
    { "event_type": "pbp", "phase": "q1", "play_index": 0, ... },
    { "event_type": "tweet", "phase": "q1", "role": "momentum", ... },
    ...
  ],
  "summary": { ... },
  "gameAnalysis": { ... }
}
```

**Response (404):** No timeline artifact exists for this game/version.

#### `POST /games/{gameId}/timeline/generate`

Generate (or regenerate) a timeline artifact. Fetches PBP, social posts, and odds from the database, merges them, validates the result, and persists the artifact.

**Response (200):** Same shape as GET.

**Error responses:**
- `404`: Game not found
- `409`: Game is not final
- `422`: Missing PBP data or validation failed

### Timeline Validation

Timelines are validated before persistence. Critical checks block persistence; warnings are logged but don't block.

#### Critical Checks

| Check | Rule |
|-------|------|
| C1 | Timeline must have at least one PBP event |
| C2 | Phase order must be monotonically non-decreasing |
| C3 | No duplicate events (dedup keys: PBP by `play_index`, tweets by `timestamp+author`, odds by `odds_type+book`) |
| C4 | All social events must have a phase |
| C5 | No social events with null/empty content |
| C6 | PBP timestamps must be non-decreasing within each phase |

#### Warning Checks

| Check | Rule |
|-------|------|
| W1 | Social events should have a role assigned |
| W2 | Expected game phases should be present (q1-q4 for NBA) |
| W3 | Summary phases should match timeline phases |
| W4 | All odds events must have a phase assigned |

### Phase Order (All Leagues)

The canonical phase ordering supports all three leagues:

| Phase | Order | League(s) |
|-------|-------|-----------|
| `pregame` | 0 | All |
| `q1` / `first_half` / `p1` | 1 | NBA / NCAAB / NHL |
| `q2` | 2 | NBA |
| `halftime` / `p2` | 3 | NBA+NCAAB / NHL |
| `q3` / `second_half` / `p3` | 4-5 | NBA / NCAAB / NHL |
| `q4` | 5 | NBA |
| `ot` / `ot1` | 6 | All |
| `ot2` | 7 | All |
| `ot3` | 8 | All |
| `ot4` | 9 | All |
| `shootout` | 10 | NHL |
| `postgame` | 99 | All |

### Consumer Migration

**Swift lines removed:** ~400

1. Delete local timeline merging logic (PBP + social assembly)
2. Call `GET /games/{gameId}/timeline` to get the merged, validated timeline
3. Events are pre-sorted — iterate in order for display
4. Filter by `event_type` to style differently (`pbp`, `tweet`, `odds`)
5. Use `phase` field for section headers
6. Use `odds_type` field to distinguish opening/closing/movement for odds events

### Key Files

| File | Purpose |
|------|---------|
| `api/app/services/odds_events.py` | **NEW** — book selection, movement detection, odds event building |
| `api/app/services/timeline_events.py` | `merge_timeline_events()` — merges PBP + social + odds |
| `api/app/services/timeline_generator.py` | `generate_timeline_artifact()` — orchestrates fetch/build/merge/validate/persist |
| `api/app/services/timeline_validation.py` | Validation rules (C1-C6, W1-W4) |
| `api/app/services/timeline_types.py` | Constants: `PHASE_ORDER`, `DEFAULT_TIMELINE_VERSION` |
| `api/app/services/social_events.py` | Social event building (phase/role assignment) |
| `api/app/routers/sports/games.py` | `GET /games/{id}/timeline`, `POST /games/{id}/timeline/generate` |
| `api/app/routers/sports/schemas.py` | `TimelineArtifactResponse` |

---

## Swift App Migration Path

Each phase can be adopted incrementally. No phase depends on another.

| Phase | Swift Lines Removed | What Changes in Swift |
|-------|--------------------|-----------------------|
| 1 (Colors) | ~742 | Read colors from API, delete `GameTheme.swift` color dictionaries |
| 2 (Odds) | ~170 | Read `derivedMetrics`, delete local odds computation in ViewModel |
| 3 (Period Labels) | ~120 | Read `periodLabel`/`timeLabel` from plays, delete 4 local implementations |
| 4 (Play Tiers) | ~337 | Read `tier` from plays, delete `PlayTier.swift` |
| 5 (Admin UI) | 0 | Admin-only improvements (verification dashboards) |
| 6 (Timeline) | ~400 | Read merged timeline, delete local merging logic |
| **Total** | **~1,770** | **Swift app becomes a thin display layer** |

### Recommended Migration Order

1. **Phase 3 (Period Labels)** — Simplest change, fixes 2 known bugs
2. **Phase 1 (Colors)** — Largest line reduction, no logic complexity
3. **Phase 2 (Odds)** — Significant simplification, removes odds math
4. **Phase 4 (Play Tiers)** — Clean removal of classification logic
5. **Phase 6 (Timeline)** — Requires most testing (timeline assembly changes)

---

## API Reference Summary

All endpoints use base path `/api/admin/sports`. All responses use **camelCase** field names.

### Endpoints Added/Modified by This Migration

| Method | Path | Phase | Description |
|--------|------|-------|-------------|
| `GET` | `/teams` | 1 | Team list with `colorLightHex`, `colorDarkHex` |
| `GET` | `/teams/{id}` | 1 | Team detail with colors |
| `PATCH` | `/teams/{id}/colors` | 1 | Update team colors |
| `GET` | `/games` | 2 | Game list with `derivedMetrics` on each game |
| `GET` | `/games/{id}` | 2,3,4 | Game detail with `derivedMetrics`, plays with `periodLabel`, `timeLabel`, `tier`, and `groupedPlays` |
| `GET` | `/games/{id}/timeline` | 6 | Retrieve persisted timeline artifact |
| `POST` | `/games/{id}/timeline/generate` | 6 | Generate/regenerate timeline |
| `GET` | `/games/{id}/flow` | — | Game flow narratives (pre-existing, not part of migration) |

### Response Type Reference

```typescript
// Phase 1
interface TeamSummary {
  id: number;
  name: string;
  shortName: string;
  abbreviation: string;
  leagueCode: string;
  gamesCount: number;
  colorLightHex: string | null;   // NEW
  colorDarkHex: string | null;    // NEW
}

// Phase 2
interface GameSummary {
  // ... existing fields ...
  derivedMetrics: Record<string, any> | null;  // NEW
}

// Phase 3 + 4
interface PlayEntry {
  playIndex: number;
  quarter: number | null;
  gameClock: string | null;
  periodLabel: string | null;     // NEW (Phase 3)
  timeLabel: string | null;       // NEW (Phase 3)
  playType: string | null;
  teamAbbreviation: string | null;
  playerName: string | null;
  description: string | null;
  homeScore: number | null;
  awayScore: number | null;
  tier: number | null;            // NEW (Phase 4) — 1, 2, or 3
}

// Phase 4
interface TieredPlayGroup {
  startIndex: number;
  endIndex: number;
  playIndices: number[];
  summaryLabel: string;           // e.g., "14 plays: foul, missed shot, turnover"
}

// Phase 6
interface TimelineArtifactResponse {
  gameId: number;
  sport: string;
  timelineVersion: string;
  generatedAt: string;            // ISO 8601
  timeline: TimelineEvent[];      // Merged, sorted events
  summary: Record<string, any>;
  gameAnalysis: Record<string, any>;
}

// Phase 6 — event_type discriminator
interface PbpEvent {
  event_type: "pbp";
  phase: string;
  intra_phase_order: number;
  play_index: number;
  quarter: number;
  game_clock: string;
  description: string;
  play_type: string;
  home_score: number;
  away_score: number;
  synthetic_timestamp: string;
}

interface TweetEvent {
  event_type: "tweet";
  phase: string;
  role: string;
  intra_phase_order: number;
  author: string;
  text: string;
  synthetic_timestamp: string;
}

interface OddsEvent {
  event_type: "odds";
  phase: "pregame";
  odds_type: "opening_line" | "closing_line" | "line_movement";
  intra_phase_order: number;
  book: string;
  markets: Record<string, { side: string; line: number; price: number }>;
  movements?: Array<{             // Only on line_movement
    market_type: string;
    side: string;
    opening_line: number;
    closing_line: number;
    movement: number;
  }>;
  synthetic_timestamp: string;
}
```

---

## Testing & Verification

### Phase 1 — Team Colors

```bash
# Verify a team has colors
curl -H "X-API-Key: $KEY" $BASE/teams/1

# Update colors
curl -X PATCH -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"colorLightHex":"#552583","colorDarkHex":"#FDB927"}' \
  $BASE/teams/1/colors
```

### Phase 2 — Derived Metrics

```bash
# Check derived metrics for a game with odds
curl -H "X-API-Key: $KEY" $BASE/games/123 | jq '.derivedMetrics'

# Verify all expected keys are present
curl -H "X-API-Key: $KEY" $BASE/games/123 | jq '.derivedMetrics | keys'
```

### Phase 3 — Period Labels

```bash
# Check plays have period/time labels
curl -H "X-API-Key: $KEY" $BASE/games/123 | jq '.plays[0] | {periodLabel, timeLabel}'

# Verify NCAAB uses H1/H2
curl -H "X-API-Key: $KEY" "$BASE/games?league=NCAAB&hasPbp=true&limit=1" | \
  jq '.games[0].id' | xargs -I {} curl -H "X-API-Key: $KEY" $BASE/games/{} | \
  jq '[.plays[] | .periodLabel] | unique'
```

### Phase 4 — Play Tiers

```bash
# Check tiers are populated
curl -H "X-API-Key: $KEY" $BASE/games/123 | jq '[.plays[] | .tier] | group_by(.) | map({tier: .[0], count: length})'

# Check grouped plays exist
curl -H "X-API-Key: $KEY" $BASE/games/123 | jq '.groupedPlays | length'
```

### Phase 6 — Timeline

```bash
# Generate a timeline
curl -X POST -H "X-API-Key: $KEY" $BASE/games/123/timeline/generate | jq '.timeline | length'

# Retrieve persisted timeline
curl -H "X-API-Key: $KEY" $BASE/games/123/timeline | jq '.timeline | length'

# Count odds events in timeline
curl -H "X-API-Key: $KEY" $BASE/games/123/timeline | \
  jq '[.timeline[] | select(.event_type == "odds")] | length'

# Verify odds events are in pregame phase
curl -H "X-API-Key: $KEY" $BASE/games/123/timeline | \
  jq '[.timeline[] | select(.event_type == "odds") | .phase] | unique'
# Expected: ["pregame"]

# 404 for game without timeline
curl -H "X-API-Key: $KEY" $BASE/games/999999/timeline
# Expected: 404
```

---

## File Index

Complete list of files involved in the server-side migration, organized by phase.

### Phase 1 — Team Colors
| File | Action | Purpose |
|------|--------|---------|
| `api/app/db/sports.py` | Modified | `color_light_hex`, `color_dark_hex` on `SportsTeam` |
| `api/app/services/team_colors.py` | New | `hex_to_rgb`, `color_distance`, `get_matchup_colors` |
| `api/app/routers/sports/teams.py` | Modified | Color fields in list/detail, `PATCH /colors` endpoint |
| `api/app/routers/sports/schemas.py` | Modified | `TeamSummary`, `TeamDetail`, `TeamColorUpdate` |
| `sql/versions/20260211_000002_add_team_colors.py` | New | Alembic migration |

### Phase 2 — Derived Metrics
| File | Action | Purpose |
|------|--------|---------|
| `api/app/services/derived_metrics.py` | New | `compute_derived_metrics()` (280 lines) |
| `api/app/routers/sports/games.py` | Modified | Wired into list and detail endpoints |
| `api/app/routers/sports/schemas.py` | Modified | `derivedMetrics` on `GameSummary`, `GameDetailResponse` |

### Phase 3 — Period Labels
| File | Action | Purpose |
|------|--------|---------|
| `api/app/services/period_labels.py` | New | `period_label()`, `time_label()` |
| `api/app/routers/sports/common.py` | Modified | `serialize_play_entry()` computes labels |
| `api/app/routers/sports/schemas.py` | Modified | `PlayEntry.period_label`, `PlayEntry.time_label` |

### Phase 4 — Play Tiers
| File | Action | Purpose |
|------|--------|---------|
| `api/app/services/play_tiers.py` | New | `classify_all_tiers()`, `group_tier3_plays()` |
| `api/app/routers/sports/games.py` | Modified | Tier classification in game detail |
| `api/app/routers/sports/schemas.py` | Modified | `PlayEntry.tier`, `TieredPlayGroup` |

### Phase 5 — Admin UI
| File | Action | Purpose |
|------|--------|---------|
| `web/src/app/admin/sports/teams/[id]/page.tsx` | Modified | Color editor with matchup preview |
| `web/src/app/admin/sports/games/[gameId]/GameDetailClient.tsx` | Modified | Derived metrics viewer |
| `web/src/app/admin/sports/games/[gameId]/PbpSection.tsx` | Modified | Tier badges, collapse toggle |

### Phase 6 — Timeline Merging
| File | Action | Purpose |
|------|--------|---------|
| `api/app/services/odds_events.py` | New | Book selection, movement detection, odds event building |
| `api/app/services/timeline_events.py` | Modified | `odds_events` param in `merge_timeline_events()` |
| `api/app/services/timeline_generator.py` | Modified | Fetches odds, builds odds events, passes to merge |
| `api/app/services/timeline_validation.py` | Modified | Odds dedup in C3, W4 `check_odds_has_phase` |
| `api/app/services/timeline_types.py` | Pre-existing | `PHASE_ORDER` (source of truth for all leagues) |
| `api/app/services/social_events.py` | Pre-existing | Social event building |
| `api/app/routers/sports/games.py` | Modified | `GET /games/{id}/timeline`, `POST .../generate` |
| `api/app/routers/sports/schemas.py` | Pre-existing | `TimelineArtifactResponse` |
