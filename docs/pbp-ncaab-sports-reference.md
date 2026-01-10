# NCAAB PBP via Sports Reference

## Data Shape Overview
Sports Reference NCAAB PBP lives under the `cbb` namespace and is accessed via the per-game PBP URL:

```
https://www.sports-reference.com/cbb/boxscores/pbp/{source_game_key}.html
```

The parser expects a single PBP table (`table#pbp`) and treats each row as a play event. Plays are normalized into the existing `NormalizedPlay` schema and stored in `sports_game_plays` with a monotonic `play_index`.

## Parsing Model (NCAAB-Specific)
- **Period mapping (halves + OT):**
  - 1st half → period `1`
  - 2nd half → period `2`
  - OT/OT2/OT3 → period `3+`
- **Clock format:** preserved as the raw clock text from the PBP table.
- **Event text:** away/home actions are concatenated into `description` when both are present. When the row is a neutral colspan event (e.g., jump ball, end of half), the full description is preserved in `raw_data`.
- **Score parsing:** if the score column uses `away-home` text, it is parsed into `away_score` and `home_score`.

## Key Differences vs NBA PBP
- **Periods:** NCAAB uses halves plus overtime instead of quarters.
- **URL host/path:** NCAAB uses the Sports Reference `cbb` domain; NBA uses Basketball Reference.
- **Data richness:** NCAAB PBP is text-heavy; there is no structured `play_type` or player identifier extraction at this time.

## Known Limitations and Gaps
- **Structured fields:** substitutions, fouls, timeouts, and reviews remain embedded in text and are not normalized into structured event types.
- **Player identifiers:** player IDs are not parsed from PBP rows; `player_id` and `player_name` are left unset unless a future enhancement is required.
- **Table layout variability:** the parser tolerates both 4-column (Time | Away | Score | Home) and 6-column layouts, but any other variant will be skipped.
- **Source verification:** the current implementation mirrors known Sports Reference patterns; confirm actual NCAAB PBP layout if the site changes or if parsing gaps are observed.

## Assumptions
- `source_game_key` from the existing NCAAB boxscore links is valid for the PBP URL.
- PBP table rows are ordered in chronological order and can be mapped to a sequential `play_index`.
- Header rows announce halves/OT in a consistent way (e.g., "1st Half", "2nd Half", "OT").

## Validation & Parity Checklist
- [ ] PBP ingestion for one NCAAB game produces deterministic `play_index` ordering.
- [ ] `quarter` values map to 1st half, 2nd half, and OT consistently.
- [ ] `description`, `away_score`, and `home_score` fields are populated when present in the table.
- [ ] No changes to NBA PBP jobs or live feed ingestion behavior.
