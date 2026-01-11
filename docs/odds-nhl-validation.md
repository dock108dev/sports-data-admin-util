# NHL Odds Validation Checklist

This checklist confirms NHL odds ingestion parity with NBA/NCAAB using The Odds API.

## Markets Supported

- [ ] **Moneyline** (`h2h` → `moneyline`)
- [ ] **Puck line** (`spreads` → `spread`)
- [ ] **Totals** (`totals` → `total`)

## Parity Checks vs NBA/NCAAB

- [ ] **Schema consistency**: `sports_game_odds` rows match the same columns/uniqueness constraints.
- [ ] **Bookmaker filtering**: optional `include_books` filter behaves the same.
- [ ] **Caching**: responses are cached under the odds cache directory by league and date.
- [ ] **Matching logic**: NHL uses the non-NCAAB exact-name matching path.
- [ ] **Market mapping**: `spreads/totals/h2h` map to `spread/total/moneyline`.
- [ ] **Malformed market skipping**: outcomes missing side/price, or missing line for spread/total, are skipped.

## NHL-Specific Checks (Odds API)

- [ ] **Sport key**: `icehockey_nhl` is used for NHL requests.
- [ ] **Period coverage**: full-game markets only (no period/alternate markets).
- [ ] **Start time handling**: `commence_time` is stored as `game_date` and used for matching.
- [ ] **Team naming**: The Odds API team names normalize to Hockey Reference canonical names.
- [ ] **OT/SO inclusion**: Moneyline/total reflect full-game results (including OT/SO).

## Differences vs NBA/NCAAB (if any)

- [ ] Note any NHL-specific naming quirks or team alias additions required.
- [ ] Note any differences in closing-line snapshot timing if adjusted.
