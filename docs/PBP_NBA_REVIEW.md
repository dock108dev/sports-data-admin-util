# NBA Play-by-Play (PBP) Integration Review

## Scope
This review covers NBA PBP ingestion via the official NBA API. The NBA API is now the primary source for all NBA play-by-play data.

## Pipeline Overview

### 1) Scheduling and Orchestration
- **Entry point:** `ScrapeRunManager.run` toggles PBP ingestion when `config.pbp` is `True`.
- **PBP ingestion:** `ingest_pbp_via_nba_api` fetches PBP from the NBA CDN and persists plays with `upsert_plays`.
- **Implementation:** `scraper/sports_scraper/services/pbp_ingestion.py`

### 2) Source Fetcher
- **NBA API:** Fetches `https://cdn.nba.com/static/json/liveData/playbyplay/playbyplay_{game_id}.json`
- **Implementation:** `scraper/sports_scraper/live/nba.py` (NBALiveFeedClient)

### 3) Parsing and Normalization

Each JSON `action` from the NBA API becomes a `NormalizedPlay` with:
- `play_index`: `period * 10000 + actionNumber` to guarantee deterministic ordering
- `quarter`: `period` from the feed
- `game_clock`: parsed from ISO-8601-like `clock` strings (e.g., `PT11M22.00S` → `11:22`)
- `play_type`, `team_abbreviation`, `player_id`, `player_name`, and `description` from the action payload
- `raw_data` includes original clock/sequence/period for traceability

### 4) Persistence
- **Storage model:** `sports_game_plays` (`SportsGamePlay`), keyed by `(game_id, play_index)` with `UniqueConstraint` and `play_index` ordering. `api/app/db_models.py`.
- **Persistence entry point:** `upsert_plays` inserts each play with `ON CONFLICT DO NOTHING` to preserve existing events and avoid overwrites. It also updates `sports_games.last_pbp_at`. `scraper/sports_scraper/persistence/plays.py`.

## Event Ordering Guarantees
Ordering is stable by using `period * 10000 + actionNumber` for `play_index`. This ensures chronological order even with late updates.

## Period / Quarter Handling
`period` is provided by the NBA API and mapped directly to `quarter`. Standard games have periods 1-4; overtime periods are numbered 5+.

## Clock Format Handling
`_parse_nba_clock` converts ISO-8601-like `PT#M#S` strings to `M:SS` format (e.g., `PT11M22.00S` → `11:22`).

## Timestamp Notes
- **No real-world timestamps per play.** NBA PBP sources only provide `quarter` + `game_clock`, so downstream consumers must synthesize wall-clock timing from period/clock context.
- **Game clock is authoritative.** The stored `game_clock` values reflect remaining time in the period; they are not synchronized to any real-world timestamp.

## Representation of Key Event Types
- **Substitutions, fouls, timeouts, reviews, etc.:** captured in `description` (Sports Reference) or `description` + `play_type` (live feed). No structured parsing or event-type normalization is performed for NBA PBP beyond what the source provides.

## Handling Missing or Malformed Events
- If the PBP endpoint returns non-200, an empty payload is returned
- Actions missing `actionNumber` are skipped
- Ingestion skips duplicates by filtering `play_index` against the max index already stored

## Key Assumptions
- `source_game_key` for NBA is used to match games (format: `YYYYMMDDHOME_TEAM_ABBREV`)
- Games are matched via the NBA schedule API to obtain the NBA game ID
- No structured event taxonomy is required for downstream consumers; raw text is preserved

## Replication Requirements for NCAAB

- Preserve the same storage model and `play_index` ordering behavior.
- Use half/OT-aware period mapping while keeping the `quarter` field for compatibility.
- Preserve raw text when structured fields are unavailable.
- Keep NCAAB logic isolated under its own scraper module.

---

## NBA Patterns to Mirror (for Other Sports)

This section summarizes NBA PBP behaviors that other sport implementations must mirror.

### Must Mirror (Behavioral Guarantees)

- **Deterministic ordering:** PBP events are stored in chronological order with a stable `play_index` using `period * 10000 + actionNumber`.
- **Period handling:** The `period` from the API is used directly; standard games have periods 1-4, overtime uses 5+.
- **Clock parsing:** Clock values are parsed from ISO-8601 format to `M:SS` display format.
- **Raw text preservation:** The full description is stored in `raw_data` and `description` without additional inference.
- **Append-only storage:** Plays are written via `upsert_plays` with `ON CONFLICT DO NOTHING`, so ordering is stable and no prior events are overwritten.

### Acceptable Divergences (for NHL/NCAAB)

- **Period semantics:** NHL uses three regulation periods, overtime, and shootouts. The `quarter` field is reused for period numbering.
- **Event taxonomy:** Sport-specific event types differ. `play_type` can contain sport-specific strings without mapping to NBA enums.
- **Score availability:** Not all rows include a score column; parsing can leave `home_score`/`away_score` unset when not present.
- **Player attribution:** Some sources do not reliably expose player IDs; `player_id`/`player_name` can remain unset.

### Non-Goals

- No possession modeling or derived possessions.
- No normalization of event text into a shared cross-sport taxonomy.
- No attempt to infer missing data (teams, players, or timestamps) beyond what the source provides.
