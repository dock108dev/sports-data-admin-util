# NHL Implementation Guide

> **Purpose:** Comprehensive reference for implementing NHL parity with NBA. This document inventories all NBA-specific logic and outlines what changes for NHL.

---

## Quick Reference: NBA vs NHL

| Aspect | NBA | NHL |
|--------|-----|-----|
| **Periods** | 4 quarters (12 min each) | 3 periods (20 min each) |
| **Overtime** | 5 min periods, sudden death | 5 min 3-on-3, then shootout |
| **Ties** | No ties (play until winner) | Ties possible in regulation |
| **Scoring unit** | Points (1-3 per score) | Goals (1 per score) |
| **Lead Ladder** | [3, 6, 10, 16] points | [1, 2, 3] goals |
| **Moment budget** | 30 moments max | 28 moments max |
| **Clock format** | 12:00 countdown | 20:00 countdown |
| **Play types** | basket, foul, turnover, etc. | goal, penalty, shot, faceoff, etc. |
| **Moneyline** | Includes OT (no ties) | Regulation only OR includes OT/SO |

---

## 1. Lead Ladder Thresholds

### Current Implementation
**File:** `api/app/services/lead_ladder.py` (sport-agnostic)

The Lead Ladder is sport-agnostic. Thresholds are configured per league and passed to all functions.

### NBA Configuration
```python
# Thresholds: [3, 6, 10, 16] points
# Tier 0: 1-2 point lead (small)
# Tier 1: 3-5 point lead (1 possession)
# Tier 2: 6-9 point lead (2 possessions)
# Tier 3: 10-15 point lead (comfortable)
# Tier 4: 16+ point lead (blowout)
```

### NHL Configuration
```python
# Thresholds: [1, 2, 3] goals
# Tier 0: Tied (no lead)
# Tier 1: 1 goal lead (small)
# Tier 2: 2 goal lead (comfortable)
# Tier 3: 3+ goal lead (commanding)
```

### Action Required
- [ ] Verify `get_thresholds_for_league("NHL")` returns correct values

---

## 2. Period/Quarter Structure

### NBA Structure
```python
# File: api/app/services/timeline_generator.py

NBA_QUARTER_GAME_SECONDS = 12 * 60  # 720 seconds
NBA_REGULATION_REAL_SECONDS = 75 * 60  # ~75 min including stoppages
NBA_HALFTIME_REAL_SECONDS = 15 * 60

# Phases: pregame, q1, q2, halftime, q3, q4, ot1, ot2, ..., postgame
# Quarter detection: play.quarter == 1 → "q1", etc.
```

### NHL Structure (IMPLEMENTED)
```python
# NHL constants (in normalize_pbp.py)
NHL_PERIOD_GAME_SECONDS = 20 * 60        # 1200 seconds
NHL_REGULATION_REAL_SECONDS = 90 * 60    # ~90 min including stoppages
NHL_INTERMISSION_REAL_SECONDS = 18 * 60  # 18-minute intermissions
NHL_OT_GAME_SECONDS = 5 * 60             # 5-minute OT (regular season)
NHL_PLAYOFF_OT_GAME_SECONDS = 20 * 60    # 20-minute playoff OT

# Phases: pregame, p1, p2, int1, p3, ot, shootout, postgame
# Period detection: play.quarter == 1 → "p1", etc.
```

### Key Differences
| NBA | NHL |
|-----|-----|
| 4 quarters | 3 periods |
| 1 halftime | 2 intermissions |
| OT is 5 min | OT is 5 min 3-on-3 |
| No shootout | Shootout after OT |
| play.quarter = 1-4 + OT | play.quarter = 1-3, 4=OT, 5=SO |

### Action Required
- [x] Add `_nhl_phase_for_period()` function ✅ (in `normalize_pbp.py`)
- [x] Add `_nhl_block_for_period()` function ✅ (in `normalize_pbp.py`)
- [x] Add `_nhl_period_start()` function ✅ (in `normalize_pbp.py`)
- [x] Timeline generation is league-agnostic ✅
- [x] Handle shootout as distinct phase ✅ (period 5 = shootout)

---

## 3. Timeline Generation

### Current State (IMPLEMENTED)
**File:** `api/app/services/timeline_generator.py`

Timeline generation is **league-agnostic** — the same code path handles NBA, NHL, and NCAAB. The previous NBA-only guard has been removed.

### Functions

| Function | Purpose | Status |
|----------|---------|--------|
| `_nba_phase_for_quarter()` | Map quarter → phase | ✅ |
| `_nba_block_for_quarter()` | Map quarter → block | ✅ |
| `_nba_quarter_start()` | Compute quarter start time | ✅ |
| `_nhl_phase_for_period()` | Map period → phase | ✅ |
| `_nhl_block_for_period()` | Map period → block | ✅ |
| `_nhl_period_start()` | Compute period start time | ✅ |

### Status
- [x] NHL phase/period mapping functions ✅ (in `normalize_pbp.py`)
- [x] OT + shootout phases handled ✅ (shootout = period 5)
- [x] Timeline generation is league-agnostic (same code path for NBA/NHL/NCAAB)

---

## 4. Moment Detection

### Current State
**File:** `api/app/services/moments/`

Moment detection is largely sport-agnostic because it uses Lead Ladder thresholds from config.

### Sport-Specific Configuration

```python
# Moment budgets (hard limits)
MOMENT_BUDGET = {
    "NBA": 30,
    "NCAAB": 32,
    "NFL": 22,
    "NHL": 28,  # Already configured
    "MLB": 26,
}

# Per-period limits
QUARTER_MOMENT_LIMIT = 7  # Same for all sports
```

### High-Impact Play Types

**NBA:**
```python
HIGH_IMPACT_PLAY_TYPES = frozenset({
    "ejection", "flagrant", "technical",  # Discipline
    "injury",  # Context-critical
})
```

**NHL (TO ADD):**
```python
NHL_HIGH_IMPACT_PLAY_TYPES = frozenset({
    "major_penalty", "game_misconduct", "match_penalty",  # Discipline
    "injury",  # Context-critical
    "fighting_majors",  # Fights
    "penalty_shot",  # Rare, dramatic
})
```

### Action Required
- [ ] Add NHL-specific high-impact play types
- [ ] Verify moment budget (28) is appropriate
- [ ] Test Lead Ladder thresholds produce reasonable moment counts

---

## 5. Play-by-Play Parsing

### Current State

**NBA PBP:** Official NBA API (`cdn.nba.com`)
**NHL PBP:** Official NHL API (`api-web.nhle.com`)

Both NBA and NHL use their official league APIs for play-by-play data. Sports Reference is used only for boxscores (NBA) and NCAAB data.

### Event Type Mapping

**NBA Event Types:**
```python
# Derived from description parsing
- made_shot, missed_shot
- made_three, missed_three
- made_free_throw, missed_free_throw
- rebound (offensive/defensive)
- turnover
- steal
- block
- foul (personal, technical, flagrant)
- timeout
- substitution
- jump_ball
```

**NHL Event Types:**
```python
# From NHL API play-by-play
- goal
- shot (on goal)
- blocked_shot
- missed_shot
- faceoff
- penalty (minor, major, misconduct)
- stoppage
- hit
- giveaway
- takeaway
- shootout_attempt
```

### Key Differences

| Aspect | NBA | NHL |
|--------|-----|-----|
| **Scoring events** | Multiple point values | All goals = 1 point |
| **Penalties** | Fouls (personal, tech) | Penalties (power play time) |
| **Possession changes** | Turnovers, rebounds | Faceoffs, stoppages |
| **Period transitions** | Quarter markers | Period + intermission |
| **Extra time** | OT periods | OT + shootout |

### Score Extraction

**NBA:**
```python
# Score available on every play row
home_score = parse_score(row, "home")
away_score = parse_score(row, "away")
```

**NHL:**
```python
# Score may not be on every row
# Goals are the scoring events
# Score is reconstructed from goal events
```

### Action Required
- [ ] Verify NHL PBP produces usable `play_type` values
- [ ] Map NHL event types to narrative weights
- [ ] Handle shootout plays (distinct from regular play)

---

## 6. Odds Handling

### Current State
**File:** `scraper/sports_scraper/odds/client.py`
**File:** `scraper/sports_scraper/odds/synchronizer.py`

### Sport Key Mapping
```python
SPORT_KEYS = {
    "NBA": "basketball_nba",
    "NHL": "icehockey_nhl",  # Already configured
    ...
}
```

### Market Differences

| Market | NBA | NHL |
|--------|-----|-----|
| **Spread** | Point spread | Puck line (usually ±1.5) |
| **Total** | Over/under points | Over/under goals |
| **Moneyline** | Win probability | 3-way (reg) or 2-way (full game) |

### NHL-Specific Considerations

1. **Puck Line vs Spread**
   - NBA spreads vary: -5.5, +3.5, etc.
   - NHL puck line is typically ±1.5 (fixed)
   - Some books offer alternate puck lines

2. **Moneyline Types**
   - **Regulation Only (3-way):** Home, Away, Draw
   - **Full Game (2-way):** Home, Away (includes OT/SO)
   - The Odds API may return both or one

3. **Tie Handling**
   - NBA: Never a tie (play until winner)
   - NHL: Regulation can end in tie → OT → Shootout

### Action Required
- [ ] Determine which moneyline type The Odds API returns for NHL
- [ ] Handle 3-way moneyline if present (Home/Away/Draw)
- [ ] Verify puck line parsing works with ±1.5 standard
- [ ] Document NHL odds behavior

---

## 7. Social Integration

### Current State
**Files:** `scraper/sports_scraper/social/team_collector.py`, `scraper/sports_scraper/social/tweet_mapper.py`
**Docs:** [SOCIAL_NHL.md](SOCIAL_NHL.md)

NHL social integration uses the **team-centric two-scrape model**:
1. **Scrape #1 (final-whistle):** Triggered on game FINAL → tweets collected to `team_social_posts`
2. **Scrape #2 (daily sweep):** Catches late tweets → mapped via `mapping_status='mapped'` in `team_social_posts`

**Parity with NBA:**
- Same scraping mechanism (Playwright)
- Same rate limiting
- Same reveal filtering
- Team handles seeded via Alembic migration

### Schedule
NHL social collection runs as part of the daily 5:00 AM EST ingestion sweep (NBA → NHL → NCAAB sequential).
See `scraper/sports_scraper/celery_app.py` for schedule configuration.

### Status
- [x] NHL team X handles seeded ✅
- [x] Social scraping works for NHL ✅
- [x] Separate scheduled tasks for NBA/NHL ✅

---

## 8. Closing Detection (Dagger Moments)

### NBA Logic
```python
# Late-game = Q4 with < 5 minutes remaining
# "Closing control" detected when:
# - Time remaining < 5 min
# - Lead tier >= 2 (comfortable)
# - Lead has been stable for N plays

DEFAULT_CLOSING_SECONDS = 300  # 5 minutes
DEFAULT_CLOSING_TIER = 1  # Max tier for "close" game
```

### NHL Considerations

**Differences:**
- NHL periods are 20 minutes (vs 12 for NBA quarters)
- A 3-goal lead in P3 is more decisive than a 10-point lead in Q4
- Empty net situations in final 2 minutes

**Proposed NHL Logic:**
```python
# Late-game = P3 with < 5 minutes remaining
# OR OT (entire period is "late-game")
# "Closing control" detected when:
# - Time remaining < 5 min in P3, or any OT
# - Lead tier >= 2 (2+ goals)
# - Empty net scenarios
```

### Action Required
- [ ] Define NHL closing detection rules
- [ ] Handle empty net as high-impact context
- [ ] Consider OT as inherently "closing" phase

---

## 9. Summary Generation

### Current State
**File:** `api/app/services/summary_builder.py`

### NBA-Specific Function
```python
def build_nba_summary(game: db_models.SportsGame) -> dict[str, Any]:
    """Build summary for NBA game."""
```

### NHL Considerations

Flow classification needs adjustment:

| Flow | NBA Margin | NHL Margin |
|------|------------|------------|
| close | ≤5 points | ≤1 goal |
| competitive | 6-12 points | 2 goals |
| comfortable | 13-20 points | 3 goals |
| blowout | >20 points | 4+ goals |

### Action Required
- [ ] Create `build_nhl_summary()` function
- [ ] Adjust flow thresholds for goals vs points
- [ ] Handle OT/SO outcomes in summary language

---

## 10. Phase Boundaries

### NBA Phase Boundaries
```python
PHASE_ORDER = {
    "pregame": 0,
    "q1": 1,
    "q2": 2,
    "halftime": 3,
    "q3": 4,
    "q4": 5,
    "ot1": 6,
    "ot2": 7,
    # ...
    "postgame": 99,
}
```

### NHL Phase Boundaries (IMPLEMENTED)
```python
# In _compute_nhl_phase_boundaries() in normalize_pbp.py
# Phases computed: p1, int1, p2, int2, p3, ot, shootout
# Phase mapping via _nhl_phase_for_period():
#   period 1 → "p1", period 2 → "p2", period 3 → "p3"
#   period 4 → "ot", period 5 → "shootout"
#   period 6+ → "ot2", "ot3", etc. (playoff extended OT)
```

### Action Required
- [x] Add NHL phase boundary computation ✅ (`_compute_nhl_phase_boundaries()`)
- [x] Map period numbers to phase codes ✅ (`_nhl_phase_for_period()`)
- [x] Handle intermissions as phases ✅ (int1, int2 computed)

---

## 11. Clock Parsing

### NBA Clock Format
```python
# Sports Reference: "8:45" (mm:ss)
# Live feed: "PT08M45.00S" (ISO-8601 duration)

def parse_clock_to_seconds(clock: str) -> int:
    # "8:45" → 525 seconds
```

### NHL Clock Format
```python
# NHL API: Clock extracted from play data as "mm:ss" or seconds
# Format varies by play type; normalized during parsing
```

### Intra-Phase Ordering
```python
# NBA: 12:00 → 0 progress, 0:00 → 720 progress
NBA_QUARTER_GAME_SECONDS = 720
progress = NBA_QUARTER_GAME_SECONDS - clock_seconds

# NHL: 20:00 → 0 progress, 0:00 → 1200 progress
NHL_PERIOD_GAME_SECONDS = 1200
progress = NHL_PERIOD_GAME_SECONDS - clock_seconds
```

### Action Required
- [x] Add `NHL_PERIOD_GAME_SECONDS = 1200` constant ✅ (in `normalize_pbp.py`)
- [x] Use in intra-phase ordering calculations ✅ (in `_build_pbp_events()`)

---

## 12. Implementation Checklist

### Phase 1: Foundation
- [ ] Verify NHL PBP scraping produces usable data
- [ ] Verify NHL odds ingestion works
- [ ] Verify NHL social scraping works

### Phase 2: Timeline Generation
- [x] Add NHL phase/period mapping functions ✅
- [x] Add NHL timing constants ✅
- [ ] Create `build_nhl_timeline()` function
- [x] Handle shootout as distinct phase ✅
- [ ] Update `generate_timeline_artifact()` to support NHL

### Phase 3: Moment Detection
- [ ] Add NHL high-impact play types
- [ ] Verify Lead Ladder produces reasonable tier crossings
- [ ] Test moment budget (28) with real games
- [ ] Define NHL closing detection rules

### Phase 4: Summary & Display
- [ ] Create `build_nhl_summary()` function
- [ ] Adjust flow thresholds for goals
- [ ] Handle OT/SO in summary language

### Phase 5: Validation
- [ ] Generate timelines for sample NHL games
- [ ] Validate moment counts are reasonable
- [ ] Validate phase ordering is correct
- [ ] Test compact mode with NHL data

---

## 13. Files to Modify

| File | Changes | Status |
|------|---------|--------|
| `api/app/services/pipeline/stages/normalize_pbp.py` | NHL phase/timing/constants | ✅ Done |
| `api/app/services/pipeline/stages/prompt_builders.py` | NHL period formatting | ✅ Done |
| `api/app/services/timeline_generator.py` | Add NHL functions, update dispatch | ✅ Done |
| `api/app/services/moments/` | Add NHL high-impact types to config | Pending |
| `api/app/services/summary_builder.py` | Add `build_nhl_summary()` | Pending |
| `api/app/services/game_analysis.py` | Add NHL thresholds reference | Pending |
| `api/app/config_sports.py` | Already has NHL config | ✅ Done |
| `scraper/sports_scraper/config_sports.py` | Already has NHL config | ✅ Done |

---

## 14. Testing Strategy

### Unit Tests
- [ ] `test_nhl_phase_mapping.py` - Period → phase mapping
- [ ] `test_nhl_lead_ladder.py` - Goal-based tier crossings
- [ ] `test_nhl_moment_detection.py` - Moment boundaries

### Integration Tests
- [ ] Generate timeline for real NHL game
- [ ] Validate moment counts (expect 15-28)
- [ ] Validate phase ordering (p1 < p2 < p3 < ot)

### Sample Games to Test
- Regulation game (3-2 final)
- Overtime game (3-3 → 4-3 OT)
- Shootout game (2-2 → 2-2 → SO winner)
- Blowout game (6-1 final)
- Close game (1-0 final)

---

## 15. NHL Official API

NHL data ingestion uses the official NHL API (`api-web.nhle.com`) exclusively. This provides all data through a single, reliable source.

### API Endpoints

| Data Type | URL Pattern |
|-----------|-------------|
| Schedule | `api-web.nhle.com/v1/schedule/{date}` |
| Play-by-Play | `api-web.nhle.com/v1/gamecenter/{game_id}/play-by-play` |
| Boxscore | `api-web.nhle.com/v1/gamecenter/{game_id}/boxscore` |

### Benefits Over Web Scraping

- **Single source:** All NHL data from one API
- **Reliability:** Official API less likely to break than HTML scraping
- **Speed:** REST API faster than web scraping
- **Player names:** Roster data included with player names resolved

### Implementation

**File:** `scraper/sports_scraper/live/nhl.py`

The `NHLLiveFeedClient` class handles:
- Schedule fetching for date ranges
- PBP fetching with player name resolution
- Boxscore fetching (team and player stats)

### Boxscore Data

Team stats: shots on goal, penalty minutes
Skater stats: goals, assists, points, +/-, PIM, hits, SOG, TOI, blocks
Goalie stats: saves, goals against, shots against, save %, TOI

---

## See Also

- [DATA_SOURCES.md](DATA_SOURCES.md) - NHL API data source details
- [ODDS_NHL_VALIDATION.md](ODDS_NHL_VALIDATION.md) - NHL odds validation
- [SOCIAL_NHL.md](SOCIAL_NHL.md) - NHL social integration
- [TIMELINE_ASSEMBLY.md](TIMELINE_ASSEMBLY.md) - Timeline generation
