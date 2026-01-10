# NHL PBP via Hockey-Reference

## Data Shape Overview
Hockey-Reference play-by-play pages live under the `boxscores/pbp` namespace and are accessed via:

```
https://www.hockey-reference.com/boxscores/pbp/{source_game_key}.html
```

The parser expects a single PBP table (`table#pbp`) and treats each row as a play event. Plays are normalized into the existing `NormalizedPlay` schema and stored in `sports_game_plays` with a monotonic `play_index`.

## Page Structure (Observed + Assumed)
> **Note:** Direct access to Hockey-Reference was blocked in the current environment, so the parser mirrors known Sports Reference patterns and should be validated against real NHL PBP pages when available.

- A single PBP table with `id="pbp"`.
- Header rows (`tr.thead`) announce period transitions (e.g., `1st Period`, `2nd Period`, `3rd Period`, `Overtime`, `Shootout`).
- Event rows contain time remaining, event type, team, description, and optionally score.
- Some rows may be neutral or colspan rows (e.g., period end summaries), which are preserved verbatim.

## Period Mapping
- **1st Period → 1**
- **2nd Period → 2**
- **3rd Period → 3**
- **Overtime → 4** (OT2 → 5, etc.)
- **Shootout → next period after regulation/OT** (kept separate from OT)

The `quarter` field is reused for NHL periods to preserve the existing schema shape.

## Event Types Observed / Expected
The parser stores the event type as the raw event text (when present) in `play_type` and preserves the raw description without normalization. Expected event categories include:
- Goals
- Penalties
- Shots / blocked shots
- Faceoffs
- Stoppages / TV timeouts
- Hits / giveaways / takeaways
- Shootout attempts

## Structured vs Free-Text Fields
- **Structured (best effort):** `play_type`, `team_abbreviation`, `home_score`, `away_score`, `game_clock`.
- **Free-text:** `description` remains as-is; no attempt to infer possession, player IDs, or derived metadata.
- **Raw preservation:** `raw_data` stores the raw cell text and per-cell `data-stat` values for traceability.

## Known Quirks and Gaps
- **Shootout rows:** Treated as a distinct period rather than merged into overtime.
- **Score column variability:** Some rows may omit the score; the parser only extracts scores matching `away-home` numeric patterns.
- **Team abbreviations:** Team text is normalized using `normalize_team_name` when possible; otherwise the raw cell text is stored.
- **Player identifiers:** Hockey-Reference PBP rows do not reliably expose player IDs, so `player_id`/`player_name` remain unset.

## Assumptions
- `source_game_key` derived from Hockey-Reference boxscore links works for the PBP URL.
- PBP rows are ordered chronologically and can be assigned sequential `play_index` values.
- Period headers appear as `tr.thead` rows and contain the period label in the row text.

## Validation & Parity Checklist
- [ ] PBP ingestion for one regulation NHL game produces deterministic `play_index` ordering.
- [ ] PBP ingestion for one overtime NHL game maps OT to period `4` (or higher for OT2).
- [ ] PBP ingestion for one shootout NHL game maps shootout to its own period (not merged into OT).
- [ ] `game_clock` preserves the clock display from Hockey-Reference.
- [ ] `description` and `raw_data` preserve unstructured text when structured fields are missing.
- [ ] No changes to NBA PBP jobs or live feed ingestion behavior.
- [ ] NHL PBP output aligns with NBA guarantees (ordering, period handling, append-only storage) with sport-specific differences documented here.
