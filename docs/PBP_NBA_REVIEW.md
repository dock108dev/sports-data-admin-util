# NBA Play-by-Play (PBP) Integration Review

## Scope
This review covers the existing NBA PBP ingestion paths, including historical scraping via Sports Reference and live polling via the NBA live feed. The goal is to document the end-to-end flow, assumptions, and handling of edge cases so NCAAB PBP can mirror the same structure without introducing cross-sport abstractions.

## Pipeline Overview

### 1) Scheduling and Orchestration
- **Entry point:** `ScrapeRunManager.run` toggles PBP ingestion when `config.pbp` is `True`. Live ingestion only runs when `config.live` is `True`. `scraper/sports_scraper/services/run_manager.py`.
- **Non-live (Sports Reference):** `_ingest_pbp_via_sportsref` selects games by league/date and calls the league scraper’s `fetch_play_by_play`, then persists plays with `upsert_plays`. `scraper/sports_scraper/services/run_manager.py`.
- **Live feed:** `LiveFeedManager.ingest_live_data` dispatches to NBA (`_sync_nba`) which resolves games via scoreboard data and ingests PBP from the NBA CDN. `scraper/sports_scraper/live/manager.py`.

### 2) Source Fetchers
- **Sports Reference (historical):** `NBASportsReferenceScraper.fetch_play_by_play` requests `https://www.basketball-reference.com/boxscores/pbp/{source_game_key}.html` and parses the `table#pbp`. `scraper/sports_scraper/scrapers/nba_sportsref.py`.
- **NBA Live Feed:** `NBALiveFeedClient.fetch_play_by_play` requests `https://cdn.nba.com/static/json/liveData/playbyplay/playbyplay_{game_id}.json`. `scraper/sports_scraper/live/nba.py`.

### 3) Parsing and Normalization
- **Sports Reference parsing:**
  - Quarter detection uses header rows with IDs like `q1`, `q2`, etc. (`current_quarter` is skipped until the first quarter is detected). `scraper/sports_scraper/scrapers/nba_sportsref.py`.
  - Each row is parsed into a `NormalizedPlay` with:
    - `play_index`: sequential counter in HTML row order.
    - `quarter`: current quarter number.
    - `game_clock`: literal clock text from the table.
    - `description`: concatenated away/home action text (`"Away action | Home action"`).
    - `home_score`/`away_score`: parsed from the score column when available.
    - `raw_data`: away action, home action, and score text for debugging.
- **Live feed parsing:**
  - Each JSON `action` becomes a `NormalizedPlay` with:
    - `play_index`: `period * 10000 + actionNumber` to guarantee deterministic ordering.
    - `quarter`: `period` from the feed.
    - `game_clock`: parsed from ISO-8601-like `clock` strings (e.g., `PT11M22.00S` → `11:22`).
    - `play_type`, `team_abbreviation`, `player_id`, `player_name`, and `description` all come from the action payload.
    - `raw_data` includes original clock/sequence/period for traceability.

### 4) Persistence
- **Storage model:** `sports_game_plays` (`SportsGamePlay`), keyed by `(game_id, play_index)` with `UniqueConstraint` and `play_index` ordering. `api/app/db_models.py`.
- **Persistence entry point:** `upsert_plays` inserts each play with `ON CONFLICT DO NOTHING` to preserve existing events and avoid overwrites. It also updates `sports_games.last_pbp_at`. `scraper/sports_scraper/persistence/plays.py`.

## Event Ordering Guarantees
- **Sports Reference path:** ordering follows HTML row order with a monotonic `play_index` counter.
- **Live feed path:** ordering is stable by using `period * 10000 + actionNumber` for `play_index`.

## Period / Quarter Handling
- **Sports Reference:** quarter numbers come from header row IDs (`q1`, `q2`, `q3`, `q4`).
- **Live feed:** `period` is provided by the NBA live payload and mapped directly to `quarter`.

## Clock Format Handling
- **Sports Reference:** raw `game_clock` string is preserved as-is from the table.
- **Live feed:** `_parse_nba_clock` converts `PT#M#S` strings to `M:SS`.

## Timestamp Notes
- **No real-world timestamps per play.** NBA PBP sources only provide `quarter` + `game_clock`, so downstream consumers must synthesize wall-clock timing from period/clock context.
- **Game clock is authoritative.** The stored `game_clock` values reflect remaining time in the period; they are not synchronized to any real-world timestamp.

## Representation of Key Event Types
- **Substitutions, fouls, timeouts, reviews, etc.:** captured in `description` (Sports Reference) or `description` + `play_type` (live feed). No structured parsing or event-type normalization is performed for NBA PBP beyond what the source provides.

## Handling Missing or Malformed Events
- **Sports Reference:**
  - Missing PBP table logs `pbp_table_not_found` and returns an empty payload.
  - Rows with unexpected column counts are skipped.
- **Live feed:**
  - If the PBP endpoint returns non-200, an empty payload is returned.
  - Actions missing `actionNumber` are skipped.
  - Ingestion skips duplicates by filtering `play_index` against the max index already stored.

## Key Assumptions
- `source_game_key` for NBA maps directly to the Basketball Reference PBP URL.
- PBP tables maintain row order suitable for sequential `play_index` assignment.
- No structured event taxonomy is required for downstream consumers; raw text is preserved.

## Replication Requirements for NCAAB

- Preserve the same storage model and `play_index` ordering behavior.
- Use half/OT-aware period mapping while keeping the `quarter` field for compatibility.
- Preserve raw text when structured fields are unavailable.
- Keep NCAAB logic isolated under its own scraper module.

---

## NBA Patterns to Mirror (for NHL Parity)

This section summarizes NBA PBP behaviors that other sport implementations must mirror.

### Must Mirror (Behavioral Guarantees)

- **Deterministic ordering:** PBP events are stored in chronological order with a stable `play_index`. Sports Reference HTML order is used to assign monotonic indices, while live feed uses `period * 10000 + sequence`.
- **Period handling:** The PBP parser relies on explicit period headers (e.g., `q1`, `q2`) and skips rows until a period is identified.
- **Clock parsing:** The PBP `game_clock` value is preserved as raw text from the source.
- **Raw text preservation:** When the event row does not fit a structured format, the full description is stored in `raw_data` and `description` without additional inference.
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
