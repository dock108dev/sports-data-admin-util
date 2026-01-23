# AI Context Policy: Prior Chapters Only

**Status:** Authoritative  
**Date:** 2026-01-21  
**Scope:** NBA v1

---

## Overview

This document defines the **authoritative AI context rules** for the Book + Chapters story generation system.

**Core Principle:** AI may only know what has happened **so far** in the game, never what happens **next**.

This prevents:
- Spoilers in chapter summaries
- Hallucinated "final line" statements
- Hindsight language in sequential chapters
- Context leakage from future chapters

---

## What AI Does (and Does Not Do)

### AI Responsibilities ✅

**AI is a narrative renderer:**
- Generate chapter summaries (1-3 sentences per chapter)
- Generate chapter titles (3-8 words per chapter)
- Generate compact story (full game recap, 4-12 min read)
- Use callbacks to prior chapters ("he already had 20 through three")
- Interpret plays with sportscaster voice
- Synthesize themes and momentum

### AI Does NOT ❌

**AI is not a decision engine:**
- ❌ Define chapter boundaries
- ❌ Decide which plays belong to which chapter
- ❌ Compute importance scores
- ❌ Infer stats beyond provided signals
- ❌ See future chapters during sequential generation
- ❌ Make strategic or structural decisions
- ❌ Determine what is "notable" or "key"

**Principle:** Structure is deterministic. AI adds meaning to existing structure.

---

## AI Context Rules (Locked Policy)

### 1. Allowed Inputs When Generating Chapter N Summary

When generating a summary for Chapter N, the AI **may receive only**:

#### ✅ Current Chapter N
- **Raw plays** from Chapter N (all plays in the chapter)
- **Chapter metadata**:
  - `chapter_id`
  - `play_start_idx`, `play_end_idx`
  - `reason_codes` (why this chapter exists)
  - `period` (quarter/period number)
  - `time_range` (game clock range)

#### ✅ Prior Chapter Summaries (Chapters 0..N-1)
- **Chapter titles** (if generated)
- **Chapter summaries** (narrative text)
- **Chapter metadata** (IDs, reason codes, periods)

**Purpose:** Enables callbacks and thematic continuity.

#### ✅ Running Story State (Derived from Chapters 0..N-1)
- **Deterministic state** computed only from prior chapters
- **Player stats "so far"** (points, shots, notable actions)
- **Team state** (score differential, momentum hints)
- **Themes** (established narrative threads)

**Purpose:** Enables "so far" language and callbacks.

---

### 2. Forbidden Inputs When Generating Chapter N Summary

The AI **must NOT receive**:

#### ❌ Future Chapters (N+1..end)
- No plays from future chapters
- No future chapter summaries
- No future chapter metadata

**Rationale:** Prevents spoilers and hindsight language.

#### ❌ Full Game PBP
- No access to complete play-by-play timeline
- Only current chapter plays + prior summaries

**Rationale:** Enforces sequential processing.

#### ❌ Full Game Stats / Box Score
- No final player totals
- No final team stats
- No computed "final" outcomes

**Rationale:** Prevents "finished with 28 points" language in early chapters.

#### ❌ Any Computed "Final" Outcomes
- No game result (unless last chapter)
- No player final lines
- No end-of-game statistics

**Exception:** Last chapter or full book generation may include finals.

---

### 3. Allowed Behaviors

When generating Chapter N summary, the AI **may**:

#### ✅ Reference Earlier Chapters as Callbacks
```
Example: "After his hot start in Q1, LeBron cooled off in Q2..."
```

**Source:** Prior chapter summaries + story state.

#### ✅ Reference "So Far" Stats
```
Example: "LeBron has 18 points through three quarters..."
```

**Source:** `story_state.players["LeBron James"].points_so_far`

#### ✅ Highlight Themes Established Earlier
```
Example: "The Lakers continued their defensive intensity from the first half..."
```

**Source:** `story_state.theme_tags` or prior summaries.

#### ✅ Use Present/Past Tense for Current Chapter
```
Example: "The Lakers went on a 10-2 run to close the quarter."
```

**Rationale:** Describes what happened in this chapter.

---

### 4. Forbidden Behaviors

When generating Chapter N summary, the AI **must NOT**:

#### ❌ Use Language Implying Foreknowledge

**Forbidden:**
```
"This would be the dagger."
"They never recovered after this run."
"His final total of 28 points..."
```

**Allowed (if last chapter):**
```
"This proved to be the dagger."
"His 28 points led the Lakers to victory."
```

**Exception:** Hindsight language is allowed **only** in:
- Last chapter summary (if game is complete)
- Full book generation (Mode B)

#### ❌ State Final Totals Unless Known

**Forbidden (in Chapter 2 of 4):**
```
"LeBron finished with 28 points."
```

**Allowed (in Chapter 2 of 4):**
```
"LeBron has 18 points so far."
```

**Allowed (in last chapter):**
```
"LeBron finished with 28 points."
```

**Rule:** Only state totals that are known from chapters processed so far.

#### ❌ Introduce Facts Not in Plays or Running State

**Forbidden:**
```
"The Lakers improved to 15-3 on the season."
```

**Rationale:** Season record is not in chapter plays or story state.

**Allowed (if in metadata):**
```
"The Lakers, riding a 5-game win streak, continued their hot play..."
```

**Rationale:** Metadata can include context like win streaks.

---

## Generation Modes

### Mode A: Chapter Summary Generation (Sequential)

**Purpose:** Generate narrative for a single chapter in sequence.

**Input Contract:**
```python
{
  "chapter": {
    "chapter_id": "ch_003",
    "plays": [...],  # Current chapter plays only
    "reason_codes": ["TIMEOUT"],
    "period": 2,
    "time_range": {"start": "8:30", "end": "5:00"}
  },
  "prior_chapters": [
    {
      "chapter_id": "ch_001",
      "title": "Opening Tip",  # Optional
      "summary": "The Lakers started strong...",
      "reason_codes": ["PERIOD_START"],
      "period": 1
    },
    {
      "chapter_id": "ch_002",
      "title": "First Quarter Surge",
      "summary": "LeBron scored 8 quick points...",
      "reason_codes": ["PERIOD_START"],
      "period": 2
    }
  ],
  "story_state": {
    "chapter_index_last_processed": 2,
    "players": {
      "LeBron James": {
        "points_so_far": 18,
        "made_fg_so_far": 7,
        "notable_actions_so_far": ["dunk", "3PT", "and-1"]
      },
      ...
    },
    "teams": {
      "Lakers": {"score_so_far": 54},
      "Celtics": {"score_so_far": 48}
    },
    "momentum_hint": "surging",
    "theme_tags": ["defensive_intensity", "hot_shooting"],
    "constraints": {
      "no_future_knowledge": true,
      "source": "derived_from_prior_chapters_only"
    }
  }
}
```

**Output Contract:**
```python
{
  "chapter_id": "ch_003",
  "title": "Timeout Adjustment",  # Optional
  "summary": "After the Lakers timeout, they tightened their defense..."
}
```

**Rules:**
- ✅ May reference prior chapters
- ✅ May use "so far" stats
- ❌ No future knowledge
- ❌ No final totals

---

### Mode B: Compact Book Generation (Full Arc)

**Purpose:** Generate a complete game narrative with hindsight.

**Input Contract:**
```python
{
  "game_id": 12345,
  "sport": "NBA",
  "chapters": [
    {
      "chapter_id": "ch_001",
      "title": "Opening Tip",
      "summary": "The Lakers started strong..."
    },
    {
      "chapter_id": "ch_002",
      "title": "First Quarter Surge",
      "summary": "LeBron scored 8 quick points..."
    },
    ...
  ],
  "metadata": {
    "home_team": "Lakers",
    "away_team": "Celtics",
    "final_score": "Lakers 112, Celtics 108"  # Allowed here
  }
}
```

**Output Contract:**
```python
{
  "compact_story": "The Lakers overcame an early deficit to defeat the Celtics 112-108. LeBron James led the way with 28 points, including a crucial 3-pointer in the final minutes. The Lakers' defense held strong in crunch time, forcing three straight turnovers to seal the victory."
}
```

**Rules:**
- ✅ Hindsight language allowed ("proved to be", "sealed the victory")
- ✅ Final totals allowed
- ✅ Game result allowed
- ✅ Narrative arc with beginning/middle/end

**This is the ONLY mode where hindsight language is permitted.**

---

## Running Story State Schema (Deterministic)

### Purpose

The **Story State** is a deterministic, incrementally-updated context object that:
- Tracks cumulative stats from chapters processed so far
- Enables "so far" language in AI prompts
- Prevents future knowledge leakage
- Remains minimal to avoid prompt bloat

### Schema Definition

```python
@dataclass
class PlayerStoryState:
    """Player state derived from prior chapters only."""
    
    player_name: str                    # Display name
    points_so_far: int                  # Cumulative points
    made_fg_so_far: int                 # Made field goals
    made_3pt_so_far: int                # Made 3-pointers
    made_ft_so_far: int                 # Made free throws
    notable_actions_so_far: list[str]   # Bounded list (max 5)


@dataclass
class TeamStoryState:
    """Team state derived from prior chapters only."""
    
    team_name: str                      # Team display name
    score_so_far: int | None            # Cumulative score (if derivable)


@dataclass
class StoryState:
    """Running story state derived deterministically from prior chapters.
    
    This state is updated incrementally after processing each chapter.
    It contains ONLY information from chapters 0..N-1 when generating Chapter N.
    
    CONTRACT:
    - Must be computed only from chapters already processed
    - Must be serializable as JSON
    - Must be stable/deterministic (same input → same output)
    - Must be minimal (bounded lists to prevent prompt bloat)
    """
    
    # Meta
    chapter_index_last_processed: int   # Last chapter included in this state
    
    # Players (top 6 by points_so_far)
    players: dict[str, PlayerStoryState]  # Keyed by player name
    
    # Teams
    teams: dict[str, TeamStoryState]    # Keyed by team name
    
    # Momentum
    momentum_hint: str                  # Enum: surging/steady/slipping/volatile/unknown
    
    # Themes
    theme_tags: list[str]               # Bounded list (max 8)
    
    # Constraints (metadata)
    constraints: dict[str, Any]         # Must include no_future_knowledge: true
```

### JSON Schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "StoryState",
  "description": "Running story state derived from prior chapters only",
  "type": "object",
  "required": [
    "chapter_index_last_processed",
    "players",
    "teams",
    "momentum_hint",
    "theme_tags",
    "constraints"
  ],
  "properties": {
    "chapter_index_last_processed": {
      "type": "integer",
      "minimum": 0,
      "description": "Last chapter index included in this state (0-based)"
    },
    "players": {
      "type": "object",
      "description": "Top 6 players by points_so_far",
      "additionalProperties": {
        "type": "object",
        "required": [
          "player_name",
          "points_so_far",
          "made_fg_so_far",
          "made_3pt_so_far",
          "made_ft_so_far",
          "notable_actions_so_far"
        ],
        "properties": {
          "player_name": {"type": "string", "minLength": 1},
          "points_so_far": {"type": "integer", "minimum": 0},
          "made_fg_so_far": {"type": "integer", "minimum": 0},
          "made_3pt_so_far": {"type": "integer", "minimum": 0},
          "made_ft_so_far": {"type": "integer", "minimum": 0},
          "notable_actions_so_far": {
            "type": "array",
            "maxItems": 5,
            "items": {"type": "string"}
          }
        }
      }
    },
    "teams": {
      "type": "object",
      "description": "Team states",
      "additionalProperties": {
        "type": "object",
        "required": ["team_name", "score_so_far"],
        "properties": {
          "team_name": {"type": "string", "minLength": 1},
          "score_so_far": {
            "type": ["integer", "null"],
            "minimum": 0,
            "description": "Cumulative score if derivable from PBP"
          }
        }
      }
    },
    "momentum_hint": {
      "type": "string",
      "enum": ["surging", "steady", "slipping", "volatile", "unknown"],
      "description": "Simple momentum indicator"
    },
    "theme_tags": {
      "type": "array",
      "maxItems": 8,
      "items": {"type": "string"},
      "description": "Deterministic theme tags"
    },
    "constraints": {
      "type": "object",
      "required": ["no_future_knowledge", "source"],
      "properties": {
        "no_future_knowledge": {
          "type": "boolean",
          "const": true,
          "description": "Must always be true"
        },
        "source": {
          "type": "string",
          "const": "derived_from_prior_chapters_only",
          "description": "Must always be this value"
        }
      }
    }
  },
  "additionalProperties": false
}
```

### Bounded Lists (Prevent Prompt Bloat)

| Field | Max Size | Truncation Rule |
|-------|----------|-----------------|
| `players` | 6 | Top 6 by `points_so_far` |
| `notable_actions_so_far` | 5 per player | Keep most recent 5 |
| `theme_tags` | 8 | Keep most frequent 8 |

**Rationale:** Prevents unbounded growth as game progresses.

---

## Deterministic Derivation Rules (NBA v1)

### How Story State is Derived

Story State is computed **deterministically** from prior chapter plays, **without AI**.

### NBA v1 Extraction Rules

#### 1. Points Accumulation

Track cumulative points from made shots and free throws:

```python
# For each play in prior chapters:
if "makes" in play.description.lower():
    if "3-pt" in play.description.lower() or "three" in play.description.lower():
        player.points_so_far += 3
        player.made_3pt_so_far += 1
        player.made_fg_so_far += 1
    elif "free throw" in play.description.lower():
        player.points_so_far += 1
        player.made_ft_so_far += 1
    else:
        player.points_so_far += 2
        player.made_fg_so_far += 1
```

**Rules:**
- Only count made shots (not misses)
- Derive from play description text
- No box score lookup

#### 2. Notable Actions

Track specific action types based on play text:

**Eligible Notable Actions:**
- `dunk` — "dunk" in description
- `block` — "block" in description
- `steal` — "steal" in description
- `3PT` — "3-pt" or "three" in description
- `and-1` — "and-1" or "and 1" in description
- `technical` — "technical" in description
- `flagrant` — "flagrant" in description
- `challenge` — "challenge" or "review" in description
- `clutch_shot` — Made shot in crunch time (Q4 <5min + close)

**Bounded List:**
- Keep most recent 5 per player
- Deterministic (FIFO)

#### 3. Team Score

If score is present in PBP events:

```python
# For each play:
if "home_score" in play and "away_score" in play:
    teams["Home"].score_so_far = play.home_score
    teams["Away"].score_so_far = play.away_score
```

**If score not derivable:** Set to `None`.

#### 4. Momentum Hint

Simple rules based on chapter reason codes:

```python
# Check most recent chapter reason codes
if "CRUNCH_START" in recent_chapter.reason_codes:
    momentum_hint = "volatile"
else:
    momentum_hint = "steady"
```

**Default:** `"unknown"` if no signal.

#### 5. Theme Tags

Deterministic tags based on chapter reason codes and play patterns:

**Eligible Theme Tags:**
- `defensive_intensity` — Multiple blocks/steals in chapter
- `hot_shooting` — High FG% in chapter (if derivable)
- `free_throw_battle` — Many FTs in chapter
- `timeout_heavy` — Multiple TIMEOUT reason codes
- `crunch_time` — CRUNCH_START reason code
- `overtime` — OVERTIME_START reason code
- `review_heavy` — Multiple REVIEW reason codes

**Bounded List:**
- Keep most frequent 8
- Deterministic (frequency-based)

---

## No Advanced Inference

**v1 Rules are intentionally simple:**

❌ No sentiment analysis  
❌ No AI-derived themes  
❌ No guessing player names from partial text  
❌ No box score lookup  
❌ No external data sources  

✅ Only explicit play text parsing
✅ Only deterministic rules
✅ Only bounded lists

---

## Validation Rules

### 1. No Future Context

When building AI input for Chapter N:

```python
assert all(ch.chapter_id < current_chapter.chapter_id for ch in prior_chapters)
assert story_state.chapter_index_last_processed == N - 1
assert "no_future_knowledge" in story_state.constraints
assert story_state.constraints["no_future_knowledge"] is True
```

### 2. Determinism

```python
# Same prior chapters → same story state
state1 = build_story_state(chapters[0:3])
state2 = build_story_state(chapters[0:3])
assert state1 == state2
```

### 3. Bounded Lists

```python
assert len(story_state.players) <= 6
for player in story_state.players.values():
    assert len(player.notable_actions_so_far) <= 5
assert len(story_state.theme_tags) <= 8
```

### 4. Schema Compliance

```python
# Validate against JSON Schema
validate(story_state.to_dict(), STORY_STATE_SCHEMA)
```

---

## Examples

### Example 1: Chapter 2 Input (Sequential Mode)

```json
{
  "chapter": {
    "chapter_id": "ch_002",
    "plays": [
      {"description": "LeBron James makes layup", "quarter": 1},
      {"description": "Anthony Davis makes dunk", "quarter": 1}
    ],
    "reason_codes": ["PERIOD_START"],
    "period": 1
  },
  "prior_chapters": [
    {
      "chapter_id": "ch_001",
      "summary": "The Lakers started strong with an 8-2 run.",
      "reason_codes": ["PERIOD_START"],
      "period": 1
    }
  ],
  "story_state": {
    "chapter_index_last_processed": 0,
    "players": {
      "LeBron James": {
        "points_so_far": 6,
        "made_fg_so_far": 3,
        "notable_actions_so_far": ["dunk"]
      }
    },
    "teams": {
      "Lakers": {"score_so_far": 8},
      "Celtics": {"score_so_far": 2}
    },
    "momentum_hint": "surging",
    "theme_tags": ["hot_shooting"],
    "constraints": {
      "no_future_knowledge": true,
      "source": "derived_from_prior_chapters_only"
    }
  }
}
```

**AI Output:**
```json
{
  "chapter_id": "ch_002",
  "title": "Lakers Extend Lead",
  "summary": "Building on their hot start, LeBron added 4 more points with a layup and Davis threw down a thunderous dunk. The Lakers now lead 12-2."
}
```

**Note:** "now lead 12-2" is allowed because it's derived from story state.

---

### Example 2: Full Book Input (Hindsight Mode)

```json
{
  "game_id": 12345,
  "sport": "NBA",
  "chapters": [
    {
      "chapter_id": "ch_001",
      "title": "Hot Start",
      "summary": "Lakers jumped out 8-2..."
    },
    {
      "chapter_id": "ch_002",
      "title": "Lakers Extend Lead",
      "summary": "LeBron added 4 more points..."
    },
    {
      "chapter_id": "ch_003",
      "title": "Celtics Fight Back",
      "summary": "Tatum scored 7 straight..."
    },
    {
      "chapter_id": "ch_004",
      "title": "Crunch Time",
      "summary": "With 3 minutes left, LeBron hit the dagger 3..."
    }
  ],
  "metadata": {
    "final_score": "Lakers 112, Celtics 108"
  }
}
```

**AI Output:**
```json
{
  "compact_story": "The Lakers defeated the Celtics 112-108 in a thrilling finish. After jumping out to an early lead, the Lakers weathered a Celtics comeback before LeBron James hit a dagger 3-pointer with 3 minutes left. His 28 points led the Lakers to victory."
}
```

**Note:** Hindsight language ("dagger", "led to victory", "28 points") is allowed in full book mode.

---

## Summary

### AI Context Rules

✅ **Prior chapters only** — No future knowledge  
✅ **Two generation modes** — Sequential (no hindsight) vs Full Book (hindsight allowed)  
✅ **"So far" language** — Enabled by story state  
✅ **Callbacks** — Enabled by prior summaries  

### Story State Schema

✅ **Deterministic** — Same input → same output  
✅ **Minimal** — Bounded lists prevent bloat  
✅ **Serializable** — JSON-compatible  
✅ **No AI** — Derived from play text only  

### Validation

✅ **No future context test** — Enforces prior-only rule  
✅ **Determinism test** — Validates reproducibility  
✅ **Schema test** — Validates structure  
✅ **Bounded list test** — Prevents unbounded growth  

---

**Status:** Authoritative
**Enforcement:** Structural (payload builder) + Unit tests
