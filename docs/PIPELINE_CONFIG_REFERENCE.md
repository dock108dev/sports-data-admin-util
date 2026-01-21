# Pipeline Configuration Reference

> Complete reference for all configurable parameters in the timeline generation pipeline.

**Last Updated:** 2026-01-21  
**Pipeline Version:** 3.x (with construction improvements)

---

## Table of Contents

1. [Configuration Files](#configuration-files)
2. [Hysteresis Configuration](#hysteresis-configuration)
3. [Boundary Detection](#boundary-detection)
4. [Moment Budget](#moment-budget)
5. [Game Phase Detection](#game-phase-detection)
6. [Closing Situations](#closing-situations)
7. [Moment Construction](#moment-construction)
8. [Advanced Parameters](#advanced-parameters)

---

## Configuration Files

### Primary Configuration
**File:** `api/app/services/moments/config.py`  
**Purpose:** Core moment system constants

### Boundary Configuration
**File:** `api/app/services/boundary_types.py`  
**Purpose:** Boundary detection parameters

### Construction Configuration
**File:** `api/app/services/moment_construction/config.py`  
**Purpose:** Phase 3 construction parameters

---

## Hysteresis Configuration

Hysteresis prevents noise by requiring state changes to persist for multiple plays before registering.

### Tier Crossing Hysteresis

```python
DEFAULT_HYSTERESIS_PLAYS = 2
```

**What it does:** Number of plays a tier must persist before registering a tier crossing.

**Impact:**
- **Lower (1):** More responsive, but noisier (more false boundaries)
- **Higher (3-4):** More stable, but may miss quick tier changes

**Recommended range:** 2-3

---

### FLIP Hysteresis

```python
DEFAULT_FLIP_HYSTERESIS_PLAYS = 2
```

**What it does:** Number of plays a new leader must hold before confirming a FLIP.

**Impact:**
- **Lower (1):** Immediate FLIP detection, may create spam in volatile games
- **Higher (3-4):** Requires sustained lead change, reduces FLIP spam

**Recommended range:** 2-3

**Special case:** Early-game FLIPs at tier 1+ bypass hysteresis (considered significant).

---

### TIE Hysteresis

```python
DEFAULT_TIE_HYSTERESIS_PLAYS = 1
```

**What it does:** Number of plays the game must stay tied before confirming a TIE.

**Impact:**
- **Lower (1):** Immediate TIE detection (current behavior)
- **Higher (2-3):** Requires sustained tie, reduces TIE spam

**Recommended range:** 1-2

**Note:** TIEs are inherently dramatic, so lower hysteresis is usually appropriate.

---

### CUT Sustained Plays

```python
CUT_SUSTAINED_PLAYS = 5
```

**What it does:** Number of plays a tier drop must persist to be considered a true comeback (CUT).

**Impact:**
- **Lower (3-4):** More sensitive to tier drops, may create false comebacks
- **Higher (6-7):** Requires sustained tier drop, reduces false comeback noise

**Recommended range:** 5-7

**Why it matters:** Prevents momentary tier drops from creating CUT moments when the lead quickly returns.

---

## Boundary Detection

### Density Gating

Prevents rapid FLIP/TIE sequences from creating too many boundaries.

```python
DEFAULT_FLIP_TIE_DENSITY_WINDOW_PLAYS = 8
DEFAULT_FLIP_TIE_DENSITY_WINDOW_SECONDS = 120
```

**What it does:** If 3+ FLIP/TIE boundaries occur within this window, subsequent boundaries are gated (suppressed).

**Impact:**
- **Smaller window (6 plays, 90s):** More aggressive gating, fewer FLIP/TIE moments
- **Larger window (12 plays, 180s):** Less aggressive, allows more back-and-forth

**Recommended ranges:**
- Plays: 8-12
- Seconds: 120-180

**When to adjust:**
- **Increase** if you see FLIP/TIE chains in baseline metrics
- **Decrease** if you're missing legitimate back-and-forth drama

---

### Late-Game False Drama Suppression

Prevents "garbage time" drama in decided games.

```python
LATE_GAME_MIN_QUARTER = 4
LATE_GAME_MAX_SECONDS = 300
LATE_GAME_SAFE_MARGIN = 10
LATE_GAME_SAFE_TIER = 2
```

**What it does:** In Q4 with < 5 minutes remaining, if the game is decided (tier ≥ 2 AND margin > 10), suppress tier-down boundaries.

**Impact:**
- **Lower safe margin (8):** More aggressive suppression
- **Higher safe margin (12):** Less aggressive, allows more late drama

**Recommended ranges:**
- Safe margin: 10-12
- Safe tier: 2-3

**When to adjust:**
- **Increase margin** if you see garbage-time CUT moments in baseline metrics
- **Decrease margin** if you're suppressing legitimate late comebacks

---

## Moment Budget

### Sport-Specific Budgets

```python
MOMENT_BUDGET = {
    "NBA": 30,
    "NCAAB": 32,
    "NFL": 22,
    "NHL": 28,
    "MLB": 26,
}
DEFAULT_MOMENT_BUDGET = 30
```

**What it does:** Hard limit on total moments per game (excluding recap moments).

**Impact:**
- **Lower budget:** More aggressive merging and selection
- **Higher budget:** More granular narrative

**Recommended ranges:**
- NBA: 28-32
- NHL: 26-30
- NFL: 20-24
- MLB: 24-28

**When to adjust:**
- **Decrease** if games consistently hit budget with low-value moments
- **Increase** if important moments are being cut

---

### Quarter Moment Limit

```python
QUARTER_MOMENT_LIMIT = 7
```

**What it does:** Maximum moments per quarter/period (prevents "chaotic quarter" bloat).

**Impact:**
- **Lower (5-6):** More aggressive per-quarter compression
- **Higher (8-9):** Allows more detail in volatile quarters

**Recommended range:** 6-8

**When to adjust:**
- **Decrease** if you see quarters with excessive moment spam
- **Increase** if important moments are being cut from volatile quarters

---

## Game Phase Detection

### Phase Thresholds

```python
EARLY_GAME_PROGRESS_THRESHOLD = 0.35
MID_GAME_PROGRESS_THRESHOLD = 0.75
```

**What it does:** Defines game phases based on progress percentage.

- **Early game:** 0-35%
- **Mid game:** 35-75%
- **Late game:** 75-100%

**Impact:**
- **Lower early threshold (0.25):** Shorter early game, gating ends sooner
- **Higher early threshold (0.40):** Longer early game, gating lasts longer

**Recommended ranges:**
- Early: 0.30-0.40
- Mid: 0.70-0.80

**When to adjust:**
- **Decrease early** if you're suppressing legitimate early drama
- **Increase early** if you see too much early-game noise

---

### Early-Game Immediate FLIP/TIE Tier

```python
EARLY_GAME_MIN_TIER_FOR_IMMEDIATE = 1
```

**What it does:** In early game, FLIP/TIE at this tier or higher bypass hysteresis.

**Impact:**
- **Lower (0):** All early FLIPs/TIEs are immediate (no hysteresis)
- **Higher (2):** Only significant early FLIPs/TIEs bypass hysteresis

**Recommended range:** 1-2

**When to adjust:**
- **Increase** if you see too many early FLIP/TIE moments
- **Decrease** if you're missing early lead changes

---

## Closing Situations

The pipeline recognizes two types of closing situations:

### 1. Close Game Closing (Expansion Mode)

Game is competitive in final minutes → expand detail, allow micro-moments.

```python
CLOSING_WINDOW_SECONDS = 300
CLOSE_GAME_MAX_TIER = 1
CLOSE_GAME_POSSESSION_THRESHOLD = 6
```

**Triggers:**
- Q4/OT with < 5 minutes remaining
- Tier ≤ 1 OR margin ≤ 6

**Behavior:**
- Relax density gating
- Allow short moments
- Expand narrative detail

---

### 2. Decided Game Closing (Compression Mode)

Game is decided in final minutes → suppress drama, compress narrative.

```python
CLOSING_WINDOW_SECONDS = 300
DECIDED_GAME_MIN_TIER = 2
DECIDED_GAME_SAFE_MARGIN = 10
```

**Triggers:**
- Q4/OT with < 5 minutes remaining
- Tier ≥ 2 AND margin > 10

**Behavior:**
- Suppress tier-down boundaries
- Absorb runs
- No semantic escalation

---

## Moment Construction

Phase 3 construction improvements (post-selection reshaping).

### Chapter Moments (Task 3.1)

Detect back-and-forth phases and create chapter moments.

```python
# From moment_construction/config.py
@dataclass
class ChapterConfig:
    enabled: bool = True
    min_flip_tie_count: int = 4
    max_time_gap_seconds: int = 300
    min_volatility_score: float = 0.6
```

**What it does:** Detects volatile periods with 4+ FLIP/TIE moments and creates a chapter moment.

**Impact:**
- **Lower min_flip_tie_count (3):** More chapters, may create false chapters
- **Higher min_flip_tie_count (5):** Fewer chapters, may miss back-and-forth phases

---

### Quarter Quotas (Task 3.2)

Dynamic per-quarter moment allocation.

```python
@dataclass
class QuotaConfig:
    enabled: bool = True
    base_quota_per_quarter: int = 7
    allow_overflow: bool = True
    max_overflow: int = 2
```

**What it does:** Allocates moment budget across quarters based on volatility.

**Impact:**
- **Lower base_quota (6):** More aggressive per-quarter compression
- **Higher base_quota (8):** More detail per quarter

---

### Closing Expansion (Task 3.4)

Late-game narrative detail expansion.

```python
@dataclass
class ClosingConfig:
    enabled: bool = True
    window_seconds: int = 300
    allow_short_moments: bool = True
    min_moment_plays: int = 2
```

**What it does:** In close games, allows shorter moments and more detail in final 5 minutes.

**Impact:**
- **Larger window (360s):** Expansion starts earlier
- **Smaller window (240s):** Expansion starts later

---

### Semantic Splitting (Task 3.3)

Split mega-moments at semantic boundaries.

```python
@dataclass
class SplitConfig:
    enabled: bool = True
    min_plays_for_split: int = 18
    max_segments: int = 3
    min_segment_plays: int = 5
```

**What it does:** Splits long moments at tier crossings or run boundaries.

**Impact:**
- **Lower min_plays_for_split (15):** More splitting, more granular moments
- **Higher min_plays_for_split (20):** Less splitting, longer moments

**Forbidden types:** FLIP, TIE, CLOSING_CONTROL, HIGH_IMPACT, recap moments (never split).

---

## Advanced Parameters

### High-Impact Play Types

```python
HIGH_IMPACT_PLAY_TYPES = frozenset({
    "ejection",
    "flagrant",
    "technical",
    "injury",
})
```

**What it does:** Play types that trigger HIGH_IMPACT moments.

**Impact:** Adding types will create more HIGH_IMPACT moments.

---

### Protected Moment Types

```python
PROTECTED_TYPES = frozenset({
    MomentType.FLIP,
    MomentType.CLOSING_CONTROL,
    MomentType.HIGH_IMPACT,
    MomentType.MOMENTUM_SHIFT,
})
```

**What it does:** Moment types that can NEVER be merged.

**Impact:** Adding types will prevent merging, increasing moment count.

---

### Always Merge Types

```python
ALWAYS_MERGE_TYPES = frozenset({
    MomentType.NEUTRAL,
    MomentType.LEAD_BUILD,
    MomentType.CUT,
})
```

**What it does:** Moment types that should always merge when consecutive.

**Impact:** Removing types will prevent merging, increasing moment count.

---

## Quick Reference: Common Tuning Scenarios

### Scenario 1: Too Many FLIP/TIE Moments

**Problem:** Baseline shows 8+ FLIP/TIE chains

**Solution:**
```python
DEFAULT_FLIP_TIE_DENSITY_WINDOW_PLAYS = 12  # Increase from 8
DEFAULT_FLIP_TIE_DENSITY_WINDOW_SECONDS = 180  # Increase from 120
DEFAULT_FLIP_HYSTERESIS_PLAYS = 3  # Increase from 2
```

---

### Scenario 2: Garbage Time Drama

**Problem:** Baseline shows late-game CUT moments in decided games

**Solution:**
```python
DECIDED_GAME_SAFE_MARGIN = 12  # Increase from 10
DECIDED_GAME_MIN_TIER = 3  # Increase from 2 (more aggressive)
```

---

### Scenario 3: Consecutive Same-Type Moments

**Problem:** Baseline shows many consecutive LEAD_BUILD or CUT moments

**Solution:**
- Ensure `merge_consecutive_moments()` is called after all construction phases
- Add final merge pass in `apply_construction_improvements()`

---

### Scenario 4: Too Many Neutral Moments

**Problem:** Baseline shows 10+ NEUTRAL moments

**Solution:**
```python
# Ensure NEUTRAL is in ALWAYS_MERGE_TYPES (already is)
# Add aggressive NEUTRAL absorption in merge logic
```

---

### Scenario 5: Missing Late-Game Detail

**Problem:** Close games feel compressed in final minutes

**Solution:**
```python
# In ClosingConfig
window_seconds = 360  # Increase from 300
min_moment_plays = 2  # Allow shorter moments
allow_short_moments = True  # Ensure enabled
```

---

## Configuration Change Workflow

1. **Establish baseline** using `analyze_baseline_metrics.py`
2. **Identify problem patterns** in baseline report
3. **Map problems to config parameters** using this reference
4. **Adjust parameters** in appropriate config file
5. **Regenerate timeline** for test games
6. **Re-run baseline analysis** and compare metrics
7. **Iterate** until acceptance criteria met

---

## Related Documentation

- `docs/PROMPT_0_BASELINE_REPORT.md` - Baseline analysis report
- `docs/MOMENT_SYSTEM_CONTRACT.md` - Moment system contract
- `data/analysis/README.md` - Baseline metrics analysis guide

---

**Configuration Version:** 1.0  
**Last Updated:** 2026-01-21
