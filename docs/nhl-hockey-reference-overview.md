# NHL Hockey-Reference Overview

## Coverage & Entry Points

Hockey-Reference exposes NHL season statistics on league pages keyed by season year. The season year is the opening year of the season (e.g., `2023-24` maps to `2023`).

**Primary pages used by the scraper:**

- Team season stats: `https://www.hockey-reference.com/leagues/NHL_{season}.html`
- Player (skater) season stats: `https://www.hockey-reference.com/leagues/NHL_{season}_skaters.html`
- Player (goalie) season stats: `https://www.hockey-reference.com/leagues/NHL_{season}_goalies.html`

The scraper expects the standard Sports Reference table IDs (`stats`, `skaters`, `goalies`) but also checks comment-wrapped tables to avoid silent misses when Hockey-Reference hides tables in HTML comments.

## Identifier Patterns

- **Season identifier:** `NHL_{season}` where `{season}` is the opening year (e.g., `2023` for the 2023-24 season).
- **Team IDs:** derived from team URLs like `/teams/NYR/2024.html` → `NYR` (uppercased).
- **Player IDs:** derived from player URLs like `/players/m/mcdavco01.html` → `mcdavco01`.
- **Team abbreviations:** Hockey-Reference abbreviations map to repo canonical team names via `normalize_team_name`.

## Available Data Types

### Team Season Stats

Captured from the `stats` table:

- Games played, wins, losses, overtime losses
- Points / points percentage (where available)
- Goals for / against, goal differential
- Shots for / against, shooting / save percentages
- Penalty minutes, power-play %, penalty-kill %
- Raw table fields retained in `raw_stats`

### Player Season Stats

Captured from `skaters` and `goalies` tables:

- Games played
- Goals, assists, points
- Positions
- Time on ice (average), when present
- Raw table fields retained in `raw_stats`

Goalie rows retain goalie-specific fields in `raw_stats` (e.g., GAA, save %, shutouts) without forcing them into skater-only fields.

## Notable Quirks vs NBA/NCAAB

- **Table IDs in comments:** Hockey-Reference frequently ships tables inside HTML comments. The scraper scans comment blocks for tables by ID and logs a warning if none are found.
- **Team abbreviations:** Hockey-Reference uses NHL-specific abbreviations (e.g., `VGK`, `CBJ`) that differ from basketball conventions.
- **Positions:** Hockey positions use abbreviations like `C`, `LW`, `RW`, `D`, `G`; they are normalized into a dedicated `position` field instead of basketball-style positional buckets.
- **Time on ice:** TOI is expressed as `MM:SS` and is converted to decimal minutes.
- **Team totals vs. individual teams:** Skater tables include `TOT` rows for players who played for multiple teams. These rows are stored with a `team_abbreviation` of `TOT` and no linked team ID.

## Integration Checklist

### Structural Alignment with NBA/NCAAB

- ✅ Season-level stats stored as JSONB with normalized helper fields.
- ✅ Per-sport normalization keeps hockey-specific fields in `raw_stats`.
- ✅ Team / player identities use Sports Reference IDs and normalized team abbreviations.

### NHL-Specific Behavior

- ✅ Team stats parsed from Hockey-Reference league pages.
- ✅ Player stats parsed from skater + goalie pages.
- ✅ TOI converted to decimal minutes; goalie-specific fields remain in `raw_stats`.
- ✅ `TOT` rows preserved without forcing them into team constraints.
