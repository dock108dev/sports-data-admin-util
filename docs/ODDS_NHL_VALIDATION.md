# NHL Odds Validation Checklist

This checklist confirms NHL odds ingestion parity with NBA/NCAAB using The Odds API.

## Markets Supported

- [x]**Moneyline** (`h2h` → `moneyline`)
- [x]**Puck line** (`spreads` → `spread`)
- [x]**Totals** (`totals` → `total`)

## Parity Checks vs NBA/NCAAB

- [x]**Schema consistency**: `sports_game_odds` rows match the same columns/uniqueness constraints.
- [x]**Bookmaker filtering**: optional `include_books` filter behaves the same.
- [x]**Caching**: responses are cached under the odds cache directory by league and date.
- [x]**Matching logic**: NHL uses the non-NCAAB exact-name matching path.
- [x]**Market mapping**: `spreads/totals/h2h` map to `spread/total/moneyline`.
- [x]**Malformed market skipping**: outcomes missing side/price, or missing line for spread/total, are skipped.

## NHL-Specific Checks (Odds API)

- [x]**Sport key**: `icehockey_nhl` is used for NHL requests.
- [x]**Period coverage**: full-game markets only (no period/alternate markets).
- [x]**Start time handling**: `commence_time` is stored as `game_date` and used for matching.
- [x]**Team naming**: The Odds API team names normalize to Hockey Reference canonical names.
- [x]**OT/SO inclusion**: Moneyline/total reflect full-game results (including OT/SO).

## Differences vs NBA/NCAAB (if any)

- [x]Note any NHL-specific naming quirks or team alias additions required.
- [x]Note any differences in closing-line snapshot timing if adjusted.
