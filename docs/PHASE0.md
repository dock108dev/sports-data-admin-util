# Beta Phase 0 — Game Identity Stabilization

> Completed: 2026-01-08

## Purpose

Phase 0 establishes a **canonical data model** for game identity. Every real-world game has exactly one internal ID, and downstream consumers (iOS app) can reliably route to the correct game.

## Canonical Schema

### games (`sports_games`)

| Column | Type | Description |
|--------|------|-------------|
| `id` | integer (PK) | **Internal ID — use this everywhere** |
| `league_id` | FK → sports_leagues | League reference |
| `game_date` | timestamp with tz | Scheduled start time (immutable) |
| `end_time` | timestamp with tz | Set when status = final (nullable until then) |
| `home_team_id` | FK → sports_teams | Internal team ID |
| `away_team_id` | FK → sports_teams | Internal team ID |
| `status` | varchar(20) | scheduled / live / final / completed / postponed / canceled |
| `source_game_key` | varchar(100) | External provider ID (for lookup only) |
| `external_ids` | JSONB | Additional external IDs by provider |

**Indexes:**
- `(league_id, game_date)` — time-window queries
- `(league_id, status)` — status-based queries
- `UNIQUE (league_id, season, game_date, home_team_id, away_team_id)` — deduplication
- `UNIQUE (source_game_key)` — external lookups

### teams (`sports_teams`)

| Column | Type | Description |
|--------|------|-------------|
| `id` | integer (PK) | **Internal ID — use this everywhere** |
| `league_id` | FK → sports_leagues | League reference |
| `abbreviation` | varchar(20) | Team abbreviation |
| `external_ref` | varchar(100) | DEPRECATED — use external_codes |
| `external_codes` | JSONB | External IDs by provider |

### pbp_events (`sports_game_plays`)

| Column | Type | Description |
|--------|------|-------------|
| `id` | integer (PK) | Internal ID |
| `game_id` | FK → sports_games | **Must reference internal game ID** |
| `quarter` | integer | Period number |
| `play_index` | integer | Sequence within game |
| `game_clock` | varchar(10) | Time remaining |
| `description` | text | Raw play description |

### social_posts (`game_social_posts`)

| Column | Type | Description |
|--------|------|-------------|
| `id` | integer (PK) | Internal ID |
| `game_id` | FK → sports_games | **Must reference internal game ID** |
| `external_post_id` | varchar(100) | Platform's post ID |
| `posted_at` | timestamp with tz | When posted |
| `spoiler_risk` | boolean | Contains score spoilers |

## ID Rules

### Internal IDs (games.id)

- **ALWAYS** use `games.id` for routing, queries, and relationships
- All FK references must use internal IDs
- API responses return internal IDs as the primary identifier

### External IDs (source_game_key)

- **NEVER** route by external ID
- Stored for reference/lookup only
- Used to match incoming data from providers
- Resolve to internal ID before any further processing

### Code Pattern

```python
# CORRECT: Look up by external, then use internal
game = session.query(SportsGame).filter_by(source_game_key=external_id).first()
if game:
    process_game(game.id)  # Use internal ID

# WRONG: Don't pass external IDs around
def process_game(external_id: str):  # ❌ Never do this
    ...

# CORRECT: Always use internal IDs
def process_game(game_id: int):  # ✅ Internal ID
    ...
```

## Status Model

### Lifecycle

```
scheduled ──┬──> live ──> final
            │
            ├──> postponed
            │
            └──> canceled
```

### Rules

1. `game_date` (start_time) is **immutable** — never changes after creation
2. `end_time` is set **only** when status becomes `final` (or `completed`)
3. `completed` is a legacy alias for `final` — new code should use `final`

### Status Values

| Status | Meaning |
|--------|---------|
| `scheduled` | Game not yet started |
| `live` | Game in progress |
| `final` | Game completed (preferred) |
| `completed` | Game completed (legacy alias) |
| `postponed` | Game delayed to future date |
| `canceled` | Game will not be played |

## Migration Notes

### Schema Changes (20260108_000001)

1. Added `end_time` column to `sports_games`
2. Added `idx_games_league_status` index
3. Added `external_post_id` and `spoiler_risk` to `game_social_posts`
4. Backfilled `end_time` for completed games

### Deprecated Paths

The following are marked deprecated but still functional:

- `SportsTeam.external_ref` — use `external_codes` for new providers
- `GameStatus.completed` — use `GameStatus.final` for new games

## API Contract

All game endpoints return:

```json
{
  "id": 98691,           // Internal ID (use this for routing)
  "league_code": "NBA",
  "status": "completed",
  "game_date": "2025-10-21T00:00:00Z"  // start_time alias
}
```

### Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /games` | List games with internal IDs |
| `GET /games/{game_id}` | Get game by internal ID |
| `POST /games/{game_id}/rescrape` | Rescrape by internal ID |

## Validation Queries

### No Duplicate External Keys

```sql
SELECT COUNT(*) FROM (
  SELECT league_id, source_game_key
  FROM sports_games
  WHERE source_game_key IS NOT NULL
  GROUP BY league_id, source_game_key
  HAVING COUNT(*) > 1
) x;
-- Expected: 0
```

### Time Window Query

```sql
SELECT * FROM sports_games
WHERE league_id = ?
  AND game_date BETWEEN ? AND ?
ORDER BY game_date;
```

### Status Query

```sql
SELECT * FROM sports_games
WHERE league_id = ?
  AND status = 'live';
```

## Definition of Done

✅ Game identity is deterministic (every game has one internal ID)
✅ Historical data is preserved and normalized
✅ Downstream routing can rely on `games.id` forever
✅ No API response depends on external IDs
✅ Status lifecycle is documented and enforced

---

*This is Phase 0. Future phases will add live polling, social scraping, and recap generation.*
