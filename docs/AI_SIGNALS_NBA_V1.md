# AI Signals for NBA v1

**Issue 9: Define Player, Team, and Theme Signals Exposed to AI**

This document defines the authoritative, locked set of signals that the AI may reference during chapter-level and full-book story generation for NBA v1.

## Core Principles

1. **Prior Chapters Only**: All signals derived from `StoryState` (chapters 0..N-1)
2. **No Future Knowledge**: No spoilers, no final totals, no outcomes
3. **Minimal & Bounded**: Only essential signals, strictly limited
4. **Deterministic**: Same chapters → same signals
5. **Natural Language Ready**: Signals map cleanly to callbacks

---

## A. Player Signals (NBA v1)

### Allowed Player Signals

Only the following player-level signals are exposed to AI:

| Field Name | Type | Description | Bounded |
|------------|------|-------------|---------|
| `player_name` | string | Display name | N/A |
| `points_so_far` | int | Cumulative points from prior chapters | Top 6 only |
| `made_fg_so_far` | int | Made field goals from prior chapters | Top 6 only |
| `made_3pt_so_far` | int | Made 3-pointers from prior chapters | Top 6 only |
| `made_ft_so_far` | int | Made free throws from prior chapters | Top 6 only |
| `notable_actions_so_far` | list[str] | Notable actions (max 5) | Top 6 only |

### Player Bounding Rules

- **Only top 6 players by `points_so_far`** are exposed to AI
- Players outside top 6 are invisible to AI (even if they appear in current chapter)
- Tie-breaking: alphabetical by `player_name` (deterministic)

### Allowed AI Phrasing

✅ **Allowed:**
- "LeBron had 20 through three quarters"
- "Curry already had 15 by halftime"
- "Durant's 12 early points"
- "Giannis with 8 so far"

❌ **Disallowed:**
- "LeBron finished with 35" (implies future knowledge)
- "Curry would end up with 28" (predictive)
- "Durant was on pace for 40" (inference)
- "Giannis was the leading scorer" (unless deterministically true in state)

### Notable Actions

Allowed notable action tags (NBA v1):
- `dunk`
- `block`
- `steal`
- `3PT`
- `and-1`
- `technical`
- `flagrant`
- `challenge`
- `clutch_shot` (only if in crunch time)

**Rules:**
- Max 5 per player (FIFO)
- No inference or fabrication
- AI may reference as: "after his dunk earlier", "with 3 three-pointers already"

---

## B. Team Signals (NBA v1)

### Allowed Team Signals

| Field Name | Type | Description | Notes |
|------------|------|-------------|-------|
| `team_name` | string | Display name | Required |
| `score_so_far` | int \| null | Cumulative score (if derivable) | Nullable |
| `momentum_hint` | enum | Coarse momentum indicator | See enum below |
| `theme_tags` | list[str] | Deterministic theme tags (max 8) | See themes |

### Momentum Hint Enum (Locked)

```
surging    # Team on a run
steady     # Normal back-and-forth
slipping   # Team losing momentum
volatile   # Momentum swinging rapidly
unknown    # Cannot determine
```

**Rules:**
- Momentum hints are **descriptive, not predictive**
- AI must not extrapolate outcomes from momentum
- Momentum is derived from most recent chapter's reason codes

### Allowed AI Phrasing

✅ **Allowed:**
- "Utah was surging"
- "Minnesota had been steady"
- "The momentum was volatile"

❌ **Disallowed:**
- "Utah would go on to win" (predictive)
- "Minnesota couldn't recover" (outcome)
- "The game was over" (finality)

---

## C. Theme Signals (NBA v1)

### Allowed Theme Tags

Themes represent **story-level patterns**, not stats.

**NBA v1 Theme Tags (Locked):**

| Theme Tag | Description | Derivation Rule |
|-----------|-------------|-----------------|
| `timeout_heavy` | Multiple timeouts | `TIMEOUT` in reason codes |
| `crunch_time` | Late + close game | `CRUNCH_START` in reason codes |
| `overtime` | Overtime period | `OVERTIME_START` in reason codes |
| `review_heavy` | Multiple reviews | `REVIEW` in reason codes |
| `defensive_intensity` | Blocks + steals | ≥3 blocks/steals in chapter |
| `hot_shooting` | Many made shots | ≥5 made shots in chapter |
| `free_throw_battle` | Many free throws | ≥4 free throws in chapter |

**Bounding:**
- Max 8 theme tags total (most frequent, deterministic)
- Themes are cumulative across all prior chapters
- Tie-breaking: alphabetical by tag name

### Allowed AI Phrasing

✅ **Allowed:**
- "Utah kept attacking the rim"
- "Minnesota was settling for threes"
- "It was a free throw battle"
- "Defensive intensity was high"

❌ **Disallowed:**
- "Utah knew Minnesota couldn't stop them" (inference)
- "Minnesota gave up" (subjective)
- "The defense was elite" (qualitative judgment)

---

## D. Signal-to-Language Mapping Guidelines

### General Rules

1. **Use past tense for prior chapters**: "had", "was", "kept"
2. **Use "so far" language**: "through three", "by halftime", "early on"
3. **No finality**: Never "finished", "ended", "final"
4. **No prediction**: Never "would", "was going to", "on pace for"
5. **No inference**: Only state what signals explicitly show

### Examples by Signal Type

**Player Stats:**
```
✅ "Collier had already piled up 20 by the time the fourth opened"
✅ "George with 14 through three quarters"
✅ "Edwards' 13 early points"
❌ "Collier was on his way to a monster night"
❌ "George would finish with 28"
```

**Notable Actions:**
```
✅ "After his dunk in the second"
✅ "With three 3-pointers already"
✅ "Following his block earlier"
❌ "He was dominating" (qualitative)
❌ "His best performance of the season" (external knowledge)
```

**Momentum:**
```
✅ "Utah was surging"
✅ "The momentum had shifted"
✅ "It was volatile"
❌ "Utah was going to win"
❌ "Minnesota had no chance"
```

**Themes:**
```
✅ "They kept attacking the rim"
✅ "It was a defensive battle"
✅ "Free throws were key"
❌ "They had the perfect strategy"
❌ "The defense was unstoppable"
```

---

## E. Disallowed Signals (Explicit Blacklist)

The following signals **must never** be exposed to AI in NBA v1:

### Stats & Totals
- ❌ `final_points` (or any "final" stat)
- ❌ `shooting_percentage` (FG%, 3PT%, FT%)
- ❌ `plus_minus`
- ❌ `efficiency_rating`
- ❌ Box score totals (rebounds, assists, etc.)

### Predictive Metrics
- ❌ `win_probability`
- ❌ `expected_points`
- ❌ `clutch_rating`
- ❌ `importance_score`

### Legacy Moments Engine
- ❌ `ladder_tier`
- ❌ `moment_type`
- ❌ `lead_change_count`
- ❌ `tier_crossing_count`

### External Context
- ❌ Season stats
- ❌ Career stats
- ❌ Team records
- ❌ Playoff context
- ❌ Historical comparisons

### Subjective Inference
- ❌ "Best player"
- ❌ "Clutch performer"
- ❌ "Momentum shifter"
- ❌ Any ranking not deterministically derived from `points_so_far`

---

## F. Schema Definition

### AI Input Payload Schema (Chapter-Level)

```json
{
  "chapter": {
    "chapter_id": "string",
    "plays": [...],
    "reason_codes": ["string"]
  },
  "story_state": {
    "chapter_index_last_processed": "int",
    "players": {
      "<player_name>": {
        "player_name": "string",
        "points_so_far": "int",
        "made_fg_so_far": "int",
        "made_3pt_so_far": "int",
        "made_ft_so_far": "int",
        "notable_actions_so_far": ["string"]
      }
    },
    "teams": {
      "<team_name>": {
        "team_name": "string",
        "score_so_far": "int | null"
      }
    },
    "momentum_hint": "surging | steady | slipping | volatile | unknown",
    "theme_tags": ["string"],
    "constraints": {
      "no_future_knowledge": true,
      "source": "derived_from_prior_chapters_only"
    }
  },
  "prior_summaries": [...]
}
```

### Validation Rules

1. **Players**: Max 6, sorted by `points_so_far` descending
2. **Notable Actions**: Max 5 per player
3. **Theme Tags**: Max 8 total
4. **Momentum Hint**: Must be valid enum value
5. **Constraints**: Must be present and valid

---

## G. Testing Requirements

### Signal Whitelist Test
- Assert AI payload contains only defined signals
- No extra fields allowed

### Bounding Test
- Create 10 players → only top 6 in payload
- Verify deterministic truncation

### No Disallowed Fields Test
- Assert no blacklisted signals in payload
- Check against explicit disallow list

### Schema Validation Test
- Payload conforms to schema
- Enums validated
- Bounds enforced

---

## H. CLI Support

### Print AI Signals Command

```bash
python -m app.services.chapters.cli <input.json> --print-ai-signals --chapter-index N
```

**Output:**
```
=== AI SIGNALS FOR CHAPTER N ===

Players (Top 6):
  1. LeBron James: 20 pts (7 FG, 2 3PT, 0 FT) | Notable: dunk, 3PT
  2. Stephen Curry: 15 pts (5 FG, 3 3PT, 0 FT) | Notable: 3PT, 3PT, 3PT
  ...

Teams:
  Lakers: 58 pts | Momentum: surging
  Warriors: 52 pts | Momentum: steady

Themes (8):
  - hot_shooting
  - defensive_intensity
  - crunch_time

Constraints:
  ✓ no_future_knowledge: true
  ✓ source: derived_from_prior_chapters_only
```

---

## I. Evolution & Extensibility

### Adding New Signals (Future)

To add a new signal:
1. Update this document with signal definition
2. Add to `StoryState` schema
3. Add derivation logic to `story_state.py`
4. Add to whitelist tests
5. Update AI prompt templates

### Removing Signals

To remove a signal:
1. Mark as deprecated in this document
2. Add to disallowed list
3. Update tests to reject it
4. Remove from schema (breaking change)

---

## J. Summary

**Allowed Signals:**
- Player: name, points/FG/3PT/FT so far, notable actions (top 6 only)
- Team: name, score so far, momentum hint, theme tags
- Themes: 8 deterministic tags

**Disallowed Signals:**
- Final stats, percentages, box scores
- Predictive metrics, win probability
- Legacy moments engine fields
- External context, subjective rankings

**Guarantees:**
- Prior chapters only
- Deterministic & bounded
- Natural language ready
- No spoilers, no inference
