# AI Signals for NBA v1

> **Status:** Authoritative
> **Last Updated:** 2026-01-24
> **Scope:** NBA v1

This document defines the signals exposed to AI during story rendering.

---

## Overview

The story renderer receives structured input and renders it into prose in a single AI call. This document defines what signals the AI sees and how it should use them.

**Key Principle:** AI sees only what's in the section input. It does not accumulate or infer.

---

## Section Input Structure

Each section provided to AI contains:

```python
@dataclass
class SectionRenderInput:
    header: str                    # Deterministic (use verbatim)
    beat_type: BeatType            # Classification of what happened
    team_stat_deltas: list[dict]   # Team stats for this section
    player_stat_deltas: list[dict] # Top 1-3 players for this section
    notes: list[str]               # Machine-generated observations
    start_score: dict[str, int]    # Score at section start
    end_score: dict[str, int]      # Score at section end
    start_period: int | None       # Period at start
    end_period: int | None         # Period at end
    start_time_remaining: int | None  # Seconds remaining at start
    end_time_remaining: int | None    # Seconds remaining at end
```

---

## A. Beat Type Signals

Beat types classify what happened in a section.

### Allowed Beat Types (NBA v1)

| Beat Type | Description | AI Should Convey |
|-----------|-------------|------------------|
| `FAST_START` | High-scoring opening | Energy, pace, rhythm |
| `MISSED_SHOT_FEST` | Low-efficiency stretch | Cold shooting, searching |
| `BACK_AND_FORTH` | Neither team separating | Trading, tight, even |
| `EARLY_CONTROL` | One team establishing lead | Edge emerging, tilt |
| `RUN` | 8+ unanswered points | Disruption, separation |
| `RESPONSE` | Comeback after a run | Clawing back, answering |
| `STALL` | Scoring drought | Flat, searching |
| `CRUNCH_SETUP` | Late tight game | Stakes rising, tension |
| `CLOSING_SEQUENCE` | Final minutes | Urgency, outcome |
| `OVERTIME` | Extra period | Extended, survival |

### How AI Uses Beat Types

Beat types inform tone and framing, not explicit labeling.

**Good:**
- RUN: "The Lakers rattled off an 11-0 run..."
- RESPONSE: "But the Celtics answered quickly..."
- STALL: "Scoring dried up as both offenses searched..."

**Bad:**
- "This was a RUN beat type"
- "The section was classified as STALL"

---

## B. Team Stat Signals

Team stats are provided as deltas for each section.

### Allowed Team Stats

| Field | Type | Description |
|-------|------|-------------|
| `team_name` | string | Display name |
| `points_scored` | int | Points scored in this section |
| `personal_fouls_committed` | int | Fouls in this section |
| `technical_fouls_committed` | int | Techs in this section |
| `timeouts_used` | int | Timeouts used in this section |

### How AI Uses Team Stats

Stats explain WHAT happened in context.

**Good:**
- "The Lakers outscored the Celtics 14-6 in this stretch"
- "Boston picked up 3 quick fouls"

**Bad:**
- "Team stats: Lakers 14, Celtics 6"
- Listing stats without narrative context

---

## C. Player Stat Signals

Player stats are provided for top 1-3 players per section.

### Allowed Player Stats

| Field | Type | Description |
|-------|------|-------------|
| `player_name` | string | Display name |
| `points_scored` | int | Points in this section |
| `fg_made` | int | Field goals made |
| `three_pt_made` | int | 3-pointers made |
| `ft_made` | int | Free throws made |
| `personal_foul_count` | int | Fouls committed |
| `foul_trouble_flag` | bool | Player in foul trouble |

### Player Bounding

- Only top 1-3 players per section are exposed
- Selection based on points scored in section
- Players not in stats are invisible to AI

### How AI Uses Player Stats

Player stats should be SELECTIVE and attached to moments.

**Good:**
- "LeBron scored 8 in the run"
- "Curry connected on back-to-back threes"

**Bad:**
- "LeBron had 8 pts (3 FG, 1 3PT, 1 FT)"
- Listing every player's full stat line

---

## D. Score Signals

Scores are provided at section start and end.

### Score Fields

| Field | Description |
|-------|-------------|
| `start_score` | `{"home": int, "away": int}` |
| `end_score` | `{"home": int, "away": int}` |

### Score Presentation Rules

- May include running score where it fits naturally
- End score should appear in last paragraph of section
- "Team A outscored Team B X-Y" is section scoring (NOT a run)
- A "run" is specifically 8+ UNANSWERED points

**Good:**
- "...leaving the score at 102-98"
- "The Lakers outscored the Celtics 14-6"

**Bad:**
- "Score: 102-98"
- Calling section scoring a "run"

---

## E. Time Context Signals

Time context anchors moments for readers.

### Time Fields

| Field | Description |
|-------|-------------|
| `start_period` | Period at section start (1-4, 5+ for OT) |
| `end_period` | Period at section end |
| `start_time_remaining` | Seconds remaining at start |
| `end_time_remaining` | Seconds remaining at end |

### Time Presentation Rules

**Allowed Expressions:**
- Explicit clock: "with 2:05 left in the first"
- Natural phrasing: "midway through the third"
- Approximate: "late in the half"

**Prohibited:**
- "in this section"
- "during the segment"
- "stretch", "phase"

---

## F. Notes Signals

Notes are machine-generated observations about the section.

### Note Types

- Scoring differential: "Lakers outscored Celtics 14-6"
- Run detection: "11-0 run"
- Game state: "Lead changed hands"
- Notable events: "Technical foul called"

### How AI Uses Notes

Notes provide facts to weave into narrative.

**Good:**
- Incorporate note facts into flowing prose
- Use notes to explain WHY momentum shifted

**Bad:**
- Quote notes verbatim
- List notes as bullet points

---

## G. Disallowed Signals

The following are NOT exposed to AI:

### Stats Not Provided
- ❌ Shooting percentages (FG%, 3PT%, FT%)
- ❌ Plus/minus
- ❌ Rebounds, assists (not tracked in sections)
- ❌ Box score totals

### Predictive Metrics
- ❌ Win probability
- ❌ Clutch rating
- ❌ Importance score

### External Context
- ❌ Season stats
- ❌ Career stats
- ❌ Team records
- ❌ Historical comparisons

### Subjective Judgments
- ❌ "Best player"
- ❌ "Clutch performer"
- ❌ Quality rankings

---

## H. AI Language Guidelines

### Allowed Phrasing

**Stats:**
- "scored 8 in the run"
- "connected on three threes"
- "picked up his fourth foul"

**Momentum:**
- "The lead grew"
- "The gap widened"
- "They clawed back"

**Time:**
- "With 2:05 left"
- "Midway through the third"
- "Late in the fourth"

### Disallowed Phrasing

**Quality Judgments:**
- "efficient", "inefficient"
- "dominant", "struggled"
- "impressive", "clutch"

**Internal Language:**
- "stretch of scoring"
- "segment", "section"
- "in this phase"

**Hedging:**
- "somewhat", "arguably"
- "to some degree"

---

## I. Validation

### Signal Whitelist Test
- Assert AI input contains only defined fields
- No extra signals allowed

### Bounding Test
- Max 3 players per section
- Stats are section deltas, not cumulative

### Language Test
- No prohibited phrases in output
- No internal structural language

---

## Summary

**What AI Sees:**
- Header (use verbatim)
- Beat type (informs tone)
- Team stats (section deltas)
- Player stats (top 1-3, section deltas)
- Notes (machine observations)
- Scores (start/end)
- Time context (period, clock)

**What AI Does NOT See:**
- Cumulative game stats
- Box score data
- External context
- Quality metrics

**Guarantees:**
- Section-scoped data only
- Deterministic & bounded
- No inference required
