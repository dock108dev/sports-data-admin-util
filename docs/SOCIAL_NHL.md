# NHL X (Twitter) Social Integration

## Scope

This integration mirrors NBA social ingestion 1:1, using the same scraper architecture, filtering, and storage model. NHL social data is **team-only** (no player or media accounts) and is attached to games by team ID.

### Included Account Types
- **Official NHL team X accounts** (from `sports_teams.x_handle` and `team_social_accounts`).
- **No league account** is included (NBA social does not include a league handle, so NHL follows the same constraint).

### Explicit Exclusions
- Player accounts (not part of NBA scope).
- Media, beat writers, and influencer accounts.
- Hashtag-based discovery or keyword search beyond the official team handles.
- Retweets (filtered by the Playwright collector); replies are not explicitly filtered and may appear if returned by search.

## NHL Team Account Map

The authoritative handles are stored in `sql/006_seed_nhl_x_handles.sql` and can be mirrored into the `team_social_accounts` registry via `sql/008_seed_team_social_accounts.sql`.

| Team | Abbrev | X Handle |
|------|--------|----------|
| Anaheim Ducks | ANA | AnaheimDucks |
| Arizona Coyotes | ARI | ArizonaCoyotes |
| Boston Bruins | BOS | NHLBruins |
| Buffalo Sabres | BUF | BuffaloSabres |
| Calgary Flames | CGY | NHLFlames |
| Carolina Hurricanes | CAR | Canes |
| Chicago Blackhawks | CHI | NHLBlackhawks |
| Colorado Avalanche | COL | Avalanche |
| Columbus Blue Jackets | CBJ | BlueJacketsNHL |
| Dallas Stars | DAL | DallasStars |
| Detroit Red Wings | DET | DetroitRedWings |
| Edmonton Oilers | EDM | EdmontonOilers |
| Florida Panthers | FLA | FlaPanthers |
| Los Angeles Kings | LAK | LAKings |
| Minnesota Wild | MIN | mnwild |
| Montréal Canadiens | MTL | CanadiensMTL |
| Nashville Predators | NSH | PredsNHL |
| New Jersey Devils | NJD | NJDevils |
| New York Islanders | NYI | NYIslanders |
| New York Rangers | NYR | NYRangers |
| Ottawa Senators | OTT | Senators |
| Philadelphia Flyers | PHI | NHLFlyers |
| Pittsburgh Penguins | PIT | penguins |
| San Jose Sharks | SJS | SanJoseSharks |
| Seattle Kraken | SEA | SeattleKraken |
| St. Louis Blues | STL | StLouisBlues |
| Tampa Bay Lightning | TBL | TampaBayLightning |
| Toronto Maple Leafs | TOR | MapleLeafs |
| Vancouver Canucks | VAN | Canucks |
| Vegas Golden Knights | VGK | GoldenKnights |
| Washington Capitals | WSH | Capitals |
| Winnipeg Jets | WPG | NHLJets |

## Parity Notes (NBA ↔ NHL)

NHL social ingestion reuses NBA assumptions without modification:
- Playwright search (`from:<handle> since:... until:...`) for historical posts.
- Retweet exclusion, conservative reveal filtering, and timestamp window checks.
- Deduplication by `platform + external_post_id`, with a `post_url` fallback.
- The same rate limiting + polling cache protections.

## Validation Checklist

Use this checklist when validating NHL social runs against NBA parity:

- [ ] **Run eligibility:** NHL social run starts when `social: true` and `league_code: NHL` are selected.
- [ ] **Account resolution:** NHL teams resolve to `team_social_accounts` or `sports_teams.x_handle` without fallback errors.
- [ ] **Schema parity:** Posts saved to `game_social_posts` with identical fields (`post_url`, `posted_at`, `tweet_text`, `media_type`, `external_post_id`, `reveal_risk`).
- [ ] **Filtering parity:** Retweets excluded; reveal-risk posts flagged instead of removed.
- [ ] **No cross-sport contamination:** Only NHL game IDs receive NHL team posts.
- [ ] **Rate limit stability:** No new rate-limit regressions vs NBA runs.
- [ ] **Deduping behavior:** Re-running ingestion does not create duplicates (external ID or URL uniqueness).

## NHL-Only Differences

None required at this time. NHL uses the same team-only account model and ingestion rules as NBA. Any future NHL-specific changes must preserve the shared social schema and the isolation of NHL data by game/team IDs.
