# Adding a New Sport/League

This guide explains how to enable a new sport in the sports-data-admin system.

## Quick Start

To add a new league (e.g., MLB):

### 1. Update SSOT Configuration

Edit **both** config files (keep them in sync):

- `scraper/sports_scraper/config_sports.py` — Full config for scraper pipelines
- `api/app/config_sports.py` — Matching config for API validation

**Example entry in `scraper/sports_scraper/config_sports.py`:**
```python
LEAGUE_CONFIG: dict[str, LeagueConfig] = {
    # ... existing leagues ...
    "MLB": LeagueConfig(
        code="MLB",
        display_name="MLB Baseball",
        boxscores_enabled=True,
        player_stats_enabled=True,
        team_stats_enabled=True,
        odds_enabled=True,
        social_enabled=False,       # Enable when X handles are seeded
        pbp_enabled=False,          # MLB PBP not yet supported
        timeline_enabled=False,     # Enable when PBP works
        scheduled_ingestion=False,  # Enable when ready for prod
    ),
}
```

Add matching entry to `api/app/config_sports.py` with the same structure.

### 2. Seed Database (if needed)

Add league to `sql/000_sports_schema.sql`:
```sql
INSERT INTO sports_leagues (code, name, sport_type)
VALUES ('MLB', 'Major League Baseball', 'baseball');
```

Run migration or insert manually.

### 3. Enable Scheduled Ingestion

When ready for production daily runs:

```python
# In config_sports.py
"MLB": LeagueConfig(
    ...
    scheduled_ingestion=True,  # Now included in daily cron
)
```

## Configuration Fields

| Field | Description |
|-------|-------------|
| `code` | Unique identifier (NBA, NHL, etc.) |
| `display_name` | Human-readable name |
| `boxscores_enabled` | Scrape team/game stats |
| `player_stats_enabled` | Scrape individual player stats |
| `team_stats_enabled` | Scrape team aggregate stats |
| `odds_enabled` | Fetch odds from odds API |
| `social_enabled` | Fetch X/Twitter posts |
| `pbp_enabled` | Scrape play-by-play data |
| `timeline_enabled` | Generate timeline artifacts |
| `scheduled_ingestion` | Include in daily cron jobs |

## Running Locally

### Single League
```bash
# Scraper CLI
cd scraper && uv run python -m sports_scraper --league NBA

# API endpoints (pass league_code explicitly)
curl "http://localhost:8000/api/admin/sports/timelines/missing?league_code=NHL"
```

### All Scheduled Leagues
```bash
# This runs for all leagues where scheduled_ingestion=True
cd scraper && uv run python -c "from sports_scraper.services.scheduler import schedule_ingestion_runs; schedule_ingestion_runs()"
```

## Validation

The system validates league codes at every entry point:
- Unknown league codes raise `ValueError`
- No silent fallback to "NBA"
- Required parameters are enforced

## Files That Reference League Config

| File | Purpose |
|------|---------|
| `scraper/sports_scraper/config_sports.py` | **SSOT for scraper** |
| `api/app/config_sports.py` | **SSOT for API** |
| `scraper/sports_scraper/services/scheduler.py` | Daily job scheduling |
| `scraper/sports_scraper/jobs/tasks.py` | Post-scrape triggers |
| `web/src/lib/constants/sports.ts` | Frontend league list |

## Common Mistakes to Avoid

❌ Don't hardcode league strings:
```python
# BAD
if league == "NBA":
    do_something()

# GOOD
from config_sports import get_league_config
cfg = get_league_config(league)
if cfg.some_feature_enabled:
    do_something()
```

❌ Don't add default="NBA":
```python
# BAD
league_code: str = Field(default="NBA")

# GOOD
league_code: str = Field(..., description="Required: NBA, NHL, NCAAB")
```

---

## Implementing a New Scraper

If the new sport needs custom scraping logic:

### 1. Create Scraper Class

Extend `BaseSportsReferenceScraper` in `scraper/sports_scraper/scrapers/`:

```python
class NewLeagueScraper(BaseSportsReferenceScraper):
    def fetch_games_for_date(self, date: date) -> list[NormalizedGame]: ...
    def pbp_url(self, game: SportsGame) -> str: ...  # If PBP supported
    def fetch_play_by_play(self, game: SportsGame) -> list[NormalizedPlay]: ...
    def fetch_single_boxscore(self, game: SportsGame) -> NormalizedGame: ...
```

### 2. Normalize Output

Build `NormalizedGame` objects with:
- `GameIdentification` (team identities, season, date)
- `home_score`, `away_score`
- `team_boxscores` + `player_boxscores`

### 3. Register the Scraper

Add to `_SCRAPER_REGISTRY` in `scraper/sports_scraper/scrapers/__init__.py`.

### 4. Run Through Orchestrator

`ScrapeRunManager` automatically pulls from `get_all_scrapers()`.

---

## Stubbed/Incomplete Data

When scrapers operate with incomplete data (pre-game, partial ingestion):

**Minimum requirements for a game payload:**

| Field | Requirement |
|-------|-------------|
| Identity fields | Always present: `league_code`, `season`, `game_date`, team identities |
| Team boxscores | Always present (two entries), but `points` may be `None` |
| Scores | May be `None` for scheduled games |
| Status | Must be explicit (`scheduled`, `in_progress`, `postponed`) |

A missing or non-numeric score is treated as a parse error and logged.
