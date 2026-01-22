# NBA v1 Chapter Boundary Rules

**Issue:** 0.3  
**Status:** Complete  
**Date:** 2026-01-21  
**Sport:** NBA only  
**Version:** v1 (Intentionally Simple)

---

## Overview

This document defines the authoritative chapter boundary rules for NBA v1.

**Philosophy:** A chapter represents a scene change, not a possession change or every score.

Boundaries separate:
- Different stretches of control
- Tactical resets
- Emotional or structural shifts in the game

Boundaries must be rare enough to keep chapters meaningful.

---

## Boundary Categories

### 1. Hard Boundaries (Always Break)

These events **always** start a new chapter. No additional context required.

| Event | Reason Code | Description |
|-------|-------------|-------------|
| **Start of quarter** | `PERIOD_START` | Q1, Q2, Q3, Q4 start |
| **End of quarter** | `PERIOD_END` | Handled by next period's start |
| **Start of overtime** | `OVERTIME_START` | Q5+ (OT periods) |
| **End of game** | `GAME_END` | Final event in timeline |

**Rules:**
- Quarter change always creates boundary
- First event of game is always `PERIOD_START`
- Overtime (quarter > 4) gets `OVERTIME_START` instead of `PERIOD_START`
- Last event always ends with `GAME_END` chapter

**Precedence:** Highest (100+)

---

### 2. Scene Reset Boundaries (Usually Break)

These events **normally** start a new chapter (tactical/structural resets).

| Event | Reason Code | Description |
|-------|-------------|-------------|
| **Team timeout** | `TIMEOUT` | Full timeout or 20-second timeout |
| **Official timeout** | `TIMEOUT` | TV timeout or official timeout |
| **Instant replay** | `REVIEW` | Instant replay review |
| **Coach's challenge** | `REVIEW` | Challenge/review |

**Rules:**
- Timeout detected by "timeout" in description or play_type
- Review detected by "review" or "challenge" in description
- Consecutive timeouts collapse into one boundary (deduplication)
- Timeout immediately following period start is absorbed by period boundary

**Precedence:** Medium (50-99)

---

### 3. Momentum Boundaries (Conditional, Minimal v1)

These events **may** start a new chapter when they indicate a scene change.

| Event | Reason Code | Description |
|-------|-------------|-------------|
| **Run starts** | `RUN_START` | Significant scoring run begins |
| **Run ends, opponent responds** | `RUN_END_RESPONSE` | Run broken by opponent |
| **Crunch time starts** | `CRUNCH_START` | Late + close game |

#### NBA v1 Run Definition (High Level)

A **run** is a sequence of unanswered scoring by one team that:
- Accumulates **6+ points**
- Spans at least **3 scoring plays**
- Occurs without the opponent scoring

**IMPORTANT:** Tier crossings and lead changes alone are NOT boundaries.  
Only actual scoring runs create boundaries.

**v1 Status:** Run boundaries stubbed (return `False`). Will be implemented in Phase 1.

#### NBA v1 Crunch Time Definition

**Crunch time** is defined as:
- **Time:** Last 5 minutes of Q4 or any overtime period
- **Score:** Margin ≤ 5 points

**Rule:** First event that meets both criteria creates a `CRUNCH_START` boundary.

**Precedence:** Low (1-49)

---

## Explicit Non-Boundaries (Never Break)

These events **NEVER** create chapter boundaries by themselves.

This list is critical to prevent regression into over-segmentation.

| Event Type | Why Not a Boundary |
|------------|-------------------|
| **Individual made baskets** | Normal game flow |
| **Free throws** | Part of possession sequence |
| **Substitutions** | Unless part of timeout/review |
| **Fouls** | Unless technical/flagrant with review |
| **Rebounds** | Normal game flow |
| **Missed shots** | Normal game flow |
| **Isolated turnovers** | Normal game flow |

**Implementation:** `is_non_boundary_event()` function explicitly filters these out.

---

## Rule Precedence Order

When multiple boundary triggers occur simultaneously, precedence determines which reason code(s) apply.

### Precedence Hierarchy

```
100: PERIOD_START (highest)
 95: OVERTIME_START
 90: PERIOD_END
 85: GAME_END
 60: REVIEW
 50: TIMEOUT
 20: CRUNCH_START
 15: RUN_START
 10: RUN_END_RESPONSE (lowest)
```

### Precedence Rules

1. **Period boundary > timeout > run logic**
   - If period starts and timeout occurs, only `PERIOD_START` is used
   - Timeout absorbed by higher precedence boundary

2. **Timeout immediately following period start**
   - Does NOT create new chapter
   - Absorbed by `PERIOD_START` boundary

3. **Multiple triggers at same event**
   - Deduplicated by precedence
   - Higher precedence codes override lower ones
   - Period boundaries suppress scene reset boundaries

### Example Resolutions

```python
# Example 1: Period start + timeout
[TIMEOUT, PERIOD_START] → [PERIOD_START]

# Example 2: Overtime start + timeout
[TIMEOUT, OVERTIME_START] → [OVERTIME_START]

# Example 3: Review + run start
[RUN_START, REVIEW] → [REVIEW]

# Example 4: Multiple scene resets
[TIMEOUT, REVIEW] → [REVIEW, TIMEOUT]  # Both included (same tier)
```

**Implementation:** `resolve_boundary_precedence()` function

---

## Reason Code Enum (Locked)

```python
class BoundaryReasonCode(str, Enum):
    # Hard boundaries
    PERIOD_START = "PERIOD_START"
    PERIOD_END = "PERIOD_END"
    OVERTIME_START = "OVERTIME_START"
    GAME_END = "GAME_END"
    
    # Scene reset boundaries
    TIMEOUT = "TIMEOUT"
    REVIEW = "REVIEW"
    
    # Momentum boundaries
    RUN_START = "RUN_START"
    RUN_END_RESPONSE = "RUN_END_RESPONSE"
    CRUNCH_START = "CRUNCH_START"
```

**Properties:**
- Fixed enum (no dynamic codes)
- Diagnostic, not narrative
- Multiple codes allowed per chapter
- Deterministic assignment

---

## Implementation

### Boundary Detection Flow

```
For each play in timeline:
  1. Check if play is explicit non-boundary → skip
  2. Evaluate hard boundaries (period, OT, game end)
  3. Evaluate scene reset boundaries (timeout, review)
  4. Evaluate momentum boundaries (run, crunch)
  5. Collect triggered reason codes
  6. Resolve precedence
  7. Create boundary if codes exist
```

### Key Functions

- `NBABoundaryRules.is_period_start()` — Detect quarter changes
- `NBABoundaryRules.is_overtime_start()` — Detect OT start
- `NBABoundaryRules.is_timeout()` — Detect timeouts
- `NBABoundaryRules.is_review()` — Detect reviews
- `NBABoundaryRules.is_crunch_start()` — Detect crunch time entry
- `is_non_boundary_event()` — Filter normal game flow
- `resolve_boundary_precedence()` — Deduplicate by precedence

**Location:** `api/app/services/chapters/boundary_rules.py`

---

## Examples

### Example 1: Simple Quarter Game

```python
Timeline:
  Q1: 20 plays (no timeouts)
  Q2: 20 plays (no timeouts)
  Q3: 20 plays (no timeouts)
  Q4: 20 plays (no timeouts)

Chapters:
  ch_001: Q1 (reason: PERIOD_START)
  ch_002: Q2 (reason: PERIOD_START)
  ch_003: Q3 (reason: PERIOD_START)
  ch_004: Q4 (reason: PERIOD_START)

Result: 4 chapters (one per quarter)
```

### Example 2: Quarter with Timeout

```python
Timeline:
  Q1 play 1-10: Normal flow
  Q1 play 11: Timeout
  Q1 play 12-20: After timeout

Chapters:
  ch_001: Plays 1-10 (reason: PERIOD_START)
  ch_002: Plays 11-20 (reason: TIMEOUT)

Result: 2 chapters (quarter split by timeout)
```

### Example 3: Crunch Time

```python
Timeline:
  Q4 play 1-50: Normal flow (6+ min remaining)
  Q4 play 51: First play under 5 min with margin <= 5
  Q4 play 52-80: Crunch time

Chapters:
  ch_001: Plays 1-50 (reason: PERIOD_START)
  ch_002: Plays 51-80 (reason: CRUNCH_START)

Result: 2 chapters (crunch time split)
```

### Example 4: No Extra Boundaries

```python
Timeline:
  Q1 play 1: Jump ball
  Q1 play 2: LeBron makes layup
  Q1 play 3: Tatum makes 3-pointer
  Q1 play 4: Davis makes jumper
  Q1 play 5: Brown makes layup

Chapters:
  ch_001: Plays 1-5 (reason: PERIOD_START)

Result: 1 chapter (scores alone don't create boundaries)
```

---

## Testing

### Test Coverage

**File:** `api/tests/test_boundary_rules.py`  
**Tests:** 27 (all passing)

#### Test Categories:
1. **Hard Boundary Enforcement** (3 tests)
   - Period start, overtime start, game end

2. **Non-Boundary Guard** (8 tests)
   - Made baskets, free throws, fouls, rebounds, etc.
   - Sequence integration (no over-segmentation)

3. **Reason Code Assignment** (5 tests)
   - Period start, timeout, review, crunch time
   - Every chapter has reason code

4. **Boundary Precedence** (4 tests)
   - Period over timeout
   - Overtime over timeout
   - Review over run
   - Timeout after period

5. **Scene Reset Boundaries** (2 tests)
   - Timeout creates boundary
   - Review creates boundary

6. **Crunch Time Detection** (3 tests)
   - Q4 under 5 min + close
   - Not close enough (margin > 5)
   - Overtime always crunch

7. **Integration** (2 tests)
   - Full game structure
   - Determinism

### Running Tests

```bash
cd api
pytest tests/test_boundary_rules.py -v
# Expected: 27 passed
```

---

## v1 Limitations (By Design)

NBA v1 is intentionally simple. The following are NOT implemented:

❌ **Advanced run detection** — Stubbed (returns `False`)  
❌ **Run-based boundaries** — Phase 1+  
❌ **Ladder tier logic** — Explicitly excluded  
❌ **Moment types** — Explicitly excluded  
❌ **Score-based heuristics** — Only crunch time uses score  
❌ **Possession-level boundaries** — Explicitly excluded  

These will be added in future phases if needed, but v1 proves the architecture works without them.

---

## Future Enhancements (Phase 1+)

### Phase 1: Run Detection
- Implement `is_run_start()` and `is_run_end_response()`
- Track active runs in context
- Define run significance thresholds

### Phase 2: Sport-Specific Tuning
- NHL boundary rules (period structure, no timeouts)
- NFL boundary rules (quarters, 2-minute warning)
- MLB boundary rules (innings, pitching changes)

### Phase 3: Advanced Momentum
- Momentum shift detection beyond runs
- Defensive stops as boundaries
- Clutch play sequences

**v1 is sufficient for validation. Advanced rules are optional.**

---

## Validation

### Structural Guarantees

✅ **No over-segmentation** — Non-boundaries explicitly excluded  
✅ **Deterministic** — Same input → same output  
✅ **Complete coverage** — Every play in exactly one chapter  
✅ **Reason codes required** — Every chapter explains why it exists  

### Rule Compliance

✅ **Hard boundaries enforced** — Quarter changes always break  
✅ **Non-boundaries respected** — Scores alone don't break  
✅ **Precedence honored** — Period > timeout > run  
✅ **Crunch time detected** — Q4 <5min + close  

---

## Summary

NBA v1 boundary rules are:
- **Simple** — Easy to understand and explain
- **Testable** — 27 tests validate behavior
- **Deterministic** — No randomness or AI
- **Extensible** — Can add rules without breaking contracts

**The rules are locked. Future tuning must extend, not replace.**

---

**Document Status:** Authoritative  
**Code:** `api/app/services/chapters/boundary_rules.py`  
**Tests:** `api/tests/test_boundary_rules.py`  
**Next:** Phase 1 (advanced run detection)
