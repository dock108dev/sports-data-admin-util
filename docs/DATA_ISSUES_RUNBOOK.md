# Data Issues Runbook

Step-by-step procedures for diagnosing and resolving common data quality issues.

Each issue follows the same flow: **Description** > **Review** > **Root Cause** > **Fix** > **Test** > **Resolve**.

---

## Issue 1: Alt Spread Fair Odds Collapse — RESOLVED 2026-02-15

**Symptom:** Multiple alternate spread lines (e.g., -1.5 and -2.5) display the same fair odds when they should differ.

**Status:** Fixed. The grouping step still uses `abs(line_value)` to form candidate buckets, but a new `_pair_opposite_sides()` helper validates that paired entries have **different** `selection_key` values before computing EV. Entries that cannot find a valid opposite side are marked `ev_disabled_reason = "no_pair"`. The fix also extracted EV annotation into a `_annotate_pair_ev()` helper.

**Files changed:**
- `api/app/routers/fairbet/odds.py` — Added `_pair_opposite_sides()`, `_annotate_pair_ev()`; refactored Step 6 EV loop
- `api/tests/test_fairbet_odds.py` — Added `TestPairOppositeSides` (6 tests), `TestAltSpreadGrouping` (3 tests)

No data cleanup needed — fair odds are computed at query time.

---

## Issue 2: Fair Odds Bad Fallback — RESOLVED 2026-02-15

**Symptom:** Fair odds show an implausible value (e.g., Fair -100 moneyline when every book prices a side at +400 or longer).

### Review

**Query Pinnacle prices for both sides of a suspect market:**

```sql
SELECT market_key, selection_key, line_value, book, price
FROM fairbet_game_odds_work
WHERE game_id = <game_id>
  AND book = 'Pinnacle'
  AND market_key ILIKE '%moneyline%'
ORDER BY selection_key;
```

Verify that Pinnacle has prices for both sides. If one side is missing, the pairing will fail silently.

**Check what the devig produces:**

For Pinnacle prices of, say, -180 and +155:
- Implied prob A: `180 / (180 + 100) = 0.643`
- Implied prob B: `100 / (155 + 100) = 0.392`
- Total: `1.035` (vig)
- True prob A: `0.643 / 1.035 = 0.621` → Fair odds: -164
- True prob B: `0.392 / 1.035 = 0.379` → Fair odds: +164

If the output is Fair -100, the wrong sides were likely paired (same root cause as Issue 1).

### Root Cause

Two potential causes:

1. **~~Same grouping bug as Issue 1.~~** RESOLVED — The `_pair_opposite_sides()` fix from Issue 1 ensures only entries with different `selection_key` values are paired, eliminating mis-pairing as a source of bad fair odds.

2. **Devig math edge cases (remaining).** `api/app/services/ev.py:56-71` — `remove_vig()` uses additive normalization: `true_prob = implied_prob / sum(implied_probs)`. This is mathematically correct for a properly paired two-way market but has no sanity check on the output. Edge cases include:
   - **Longshot markets:** Additive devig systematically overstates the favorite's true probability on lopsided lines (e.g., -800/+500). The devigged fair odds can look implausible compared to the consensus.
   - **Stale-on-one-side:** If Pinnacle's price on one side is stale while the other is fresh, the devig inputs are inconsistent even though the freshness check passes (it uses the *older* of the two).
   - **No divergence check:** A devigged fair price of -100 is never flagged even when every book prices the side at +400 or longer.

### Fix

1. **~~Primary: Fix the grouping bug from Issue 1.~~** DONE (2026-02-15).
2. **Remaining:** Add a sanity check in the EV computation. After devigging, compare the resulting fair odds against the consensus of all books for that side. If the fair price diverges from the book-median price by more than a configurable threshold, flag the market with `ev_disabled_reason = "fair_odds_outlier"` rather than displaying potentially misleading fair odds. This check belongs in `api/app/services/ev.py` inside or around `compute_ev_for_market()` (line ~212).

### Test

1. Construct a test case where Pinnacle has -180 / +155 and verify the devig produces approximately -164 / +164 (not -100).
2. Test the edge case where only one side of a Pinnacle market exists — the code should skip EV rather than pairing with an unrelated side.

### Resolve

No data cleanup needed. Fair odds are computed at query time, so fixing the code immediately resolves all games.

---

## Issue 3: AI Player-Team Misattribution

**Symptom:** A game flow narrative attributes a player to the wrong team (e.g., describes a player as playing for Duke when they play for Clemson).

### Review

**Query the narrative text for a suspect game:**

```sql
SELECT id, game_id, content, created_at
FROM sports_game_stories
WHERE game_id = <game_id>
ORDER BY created_at DESC
LIMIT 1;
```

Search the `content` JSON for the misattributed player name and note which team context the narrative places them in.

**Confirm the player's actual team from play-by-play:**

```sql
SELECT DISTINCT p.player_name, p.team_id, t.abbreviation, t.display_name
FROM sports_game_plays p
JOIN sports_teams t ON t.id = p.team_id
WHERE p.game_id = <game_id>
  AND p.player_name ILIKE '%<player_name>%';
```

If the narrative says Team A but the query says Team B, the misattribution is confirmed.

### Root Cause

`api/app/services/pipeline/stages/render_prompts.py:297-303` — When building the prompt for OpenAI, key plays are passed as bare descriptions without team context:

```
# Lines 297-303
key_plays_desc = []
for pid in key_play_ids:
    play = play_lookup.get(pid, {})
    desc = play.get("description", "")
    if desc:
        key_plays_desc.append(f"- {desc}")
```

The play `description` field (e.g., "Ngongba makes a layup") doesn't include which team the player is on. OpenAI must infer team affiliation from surrounding context (home/away, score direction), and it sometimes guesses wrong — especially when a less well-known player scores in a block where the opposing team has momentum.

### Fix

Include the `team_abbreviation` in each key play description sent to OpenAI. The `play_lookup` dict already contains `team_id`; resolve it to an abbreviation and prepend it:

The fix lives in `api/app/services/pipeline/stages/render_prompts.py` around lines 297-303. Conceptually, change the line from:

```
key_plays_desc.append(f"- {desc}")
```

to something like:

```
key_plays_desc.append(f"- [{team_abbr}] {desc}")
```

This gives OpenAI an explicit signal and removes the guessing.

### Test

1. Find a completed game with key plays from both teams in the same block.
2. Run the pipeline with `force=true` and verify the narrative correctly attributes each player to their team.
3. Spot-check 2-3 additional games to confirm no regressions.

### Resolve

Unlike the odds issues, game flow narratives are persisted in `sports_game_stories`. After deploying the fix, re-run the pipeline for affected games:

**Single game:**

```bash
curl -X POST "http://localhost:8000/api/admin/timelines/<game_id>/generate" \
  -H "Content-Type: application/json" \
  -d '{"force": true}'
```

**Batch (date range):**

```bash
curl -X POST "http://localhost:8000/api/admin/timelines/regenerate-batch" \
  -H "Content-Type: application/json" \
  -d '{"start_date": "2026-02-15", "end_date": "2026-02-15"}'
```

**Identify affected games** (games with a specific player in key plays):

```sql
SELECT DISTINCT gs.game_id, g.game_date, g.status
FROM sports_game_stories gs
JOIN sports_games g ON g.id = gs.game_id
WHERE gs.content::text ILIKE '%<player_name>%'
ORDER BY g.game_date DESC;
```

---

## Quick Reference

| Issue | Root Cause File | Data Cleanup? | Status |
|-------|----------------|---------------|--------|
| Alt spread collapse | `api/app/routers/fairbet/odds.py` | No (query-time) | **RESOLVED** 2026-02-15 |
| Bad fallback odds | `api/app/services/ev.py` | No (query-time) | **RESOLVED** 2026-02-15 |
| Player misattribution | `api/app/services/pipeline/stages/render_prompts.py:297` | Yes (re-run pipeline) | Open |

---

## See Also

- [OPERATOR_RUNBOOK.md](OPERATOR_RUNBOOK.md) — Production operations guide
- [API.md](API.md) — API endpoint documentation
- [GAMEFLOW_CONTRACT.md](GAMEFLOW_CONTRACT.md) — Game flow pipeline contract
