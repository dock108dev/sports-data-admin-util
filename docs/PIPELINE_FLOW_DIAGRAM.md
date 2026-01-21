# Timeline Generation Pipeline Flow

> Visual representation of the pipeline stages, data flow, and problem injection points.

**Last Updated:** 2026-01-21

---

## High-Level Pipeline Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                         INPUT DATA                                  │
├─────────────────────────────────────────────────────────────────────┤
│  • Play-by-play events (raw)                                        │
│  • Game metadata (teams, scores, clock)                             │
│  • Social posts (optional)                                          │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│  STAGE 1: NORMALIZE_PBP                                             │
├─────────────────────────────────────────────────────────────────────┤
│  • Clean and normalize play-by-play data                            │
│  • Fix score inconsistencies                                        │
│  • Build canonical PBP stream                                       │
│                                                                     │
│  Output: Normalized PBP events                                      │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│  STAGE 2: DERIVE_SIGNALS                                            │
├─────────────────────────────────────────────────────────────────────┤
│  • Compute Lead Ladder states (tier, leader)                        │
│  • Detect tier crossings (up/down)                                  │
│  • Identify scoring runs                                            │
│  • Build game phase context                                         │
│                                                                     │
│  Output: Lead states, tier crossings, runs, thresholds             │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│  STAGE 3: GENERATE_MOMENTS                                          │
├─────────────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  3.1: DETECT BOUNDARIES                                     │   │
│  │  • Tier crossings → LEAD_BUILD, CUT                         │   │
│  │  • Leader changes → FLIP                                    │   │
│  │  • Tie states → TIE                                         │   │
│  │  • Closing situations → CLOSING_CONTROL                     │   │
│  │  • High-impact events → HIGH_IMPACT                         │   │
│  │                                                             │   │
│  │  ⚠️  PROBLEM ZONE: Density gating, hysteresis              │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                  │                                  │
│                                  ▼                                  │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  3.2: CREATE MOMENTS                                        │   │
│  │  • Partition timeline at boundaries                         │   │
│  │  • Assign moment types                                      │   │
│  │  • Calculate scores, clock, participants                    │   │
│  │  • Attach run metadata                                      │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                  │                                  │
│                                  ▼                                  │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  3.3: MERGE MOMENTS                                         │   │
│  │  • Merge consecutive same-type moments                      │   │
│  │  • Merge invalid/low-value moments                          │   │
│  │  • Enforce quarter limits (max 7 per quarter)               │   │
│  │                                                             │   │
│  │  ⚠️  PROBLEM ZONE: Merge timing, incomplete merging        │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  Output: Raw moments with generation trace                          │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│  STAGE 4: FINALIZE_MOMENTS                                          │
├─────────────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  4.1: IMPORTANCE SCORING                                    │   │
│  │  • Calculate importance scores (0-100)                      │   │
│  │  • Weight by lead change, game phase, run size              │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                  │                                  │
│                                  ▼                                  │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  4.2: NARRATIVE SELECTION                                   │   │
│  │  • Select top moments within budget                         │   │
│  │  • Ensure balanced distribution across quarters             │   │
│  │  • Preserve protected moments (FLIP, CLOSING_CONTROL)       │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                  │                                  │
│                                  ▼                                  │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  4.3: CONSTRUCTION IMPROVEMENTS (Phase 3)                   │   │
│  │  • Task 3.1: Create chapter moments (back-and-forth)        │   │
│  │  • Task 3.2: Enforce quarter quotas                         │   │
│  │  • Task 3.4: Closing expansion (late-game detail)           │   │
│  │  • Task 3.3: Semantic splitting (mega-moments)              │   │
│  │                                                             │   │
│  │  ⚠️  PROBLEM ZONE: Split type inheritance, missing merge   │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                  │                                  │
│                                  ▼                                  │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  4.4: ENRICHMENT                                            │   │
│  │  • Aggregate player stats per moment                        │   │
│  │  • Generate AI headlines & summaries                        │   │
│  │  • Add display hints (weight, icon, color)                  │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  Output: Final timeline artifact                                    │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         OUTPUT DATA                                 │
├─────────────────────────────────────────────────────────────────────┤
│  • Timeline artifact (JSON)                                         │
│  • Moments with full metadata                                       │
│  • Generation trace (for debugging)                                 │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Problem Injection Points

### Problem Zone 1: Boundary Detection (Stage 3.1)

**Location:** `api/app/services/moments_boundaries.py`

```
PBP Events → Boundary Detection → Boundaries
                    │
                    ├─ Hysteresis Check
                    │  ⚠️  Too low → noise
                    │  ⚠️  Too high → missed events
                    │
                    ├─ Density Gating
                    │  ⚠️  Window too small → FLIP/TIE spam
                    │  ⚠️  Window too large → missed drama
                    │
                    └─ Late-Game Suppression
                       ⚠️  Threshold too permissive → garbage time drama
                       ⚠️  Threshold too strict → missed comebacks
```

**Problem Patterns Created:**
- FLIP/TIE chains (density gating failure)
- Short moments (hysteresis too low)
- False drama cuts (late-game suppression failure)

---

### Problem Zone 2: Moment Merging (Stage 3.3)

**Location:** `api/app/services/moments_merging.py`

```
Raw Moments → Merge Logic → Merged Moments
                  │
                  ├─ Consecutive Same Type
                  │  ⚠️  Not merging → duplicate moments
                  │
                  ├─ Invalid Moments
                  │  ⚠️  Not absorbing → redundant neutrals
                  │
                  └─ Quarter Limits
                     ⚠️  Enforced too early → construction breaks it
```

**Problem Patterns Created:**
- Consecutive same-type moments
- Redundant neutral moments
- Quarter limit violations

---

### Problem Zone 3: Construction Improvements (Stage 4.3)

**Location:** `api/app/services/moment_construction/`

```
Selected Moments → Construction → Final Moments
                       │
                       ├─ Chapter Creation
                       │  ✅ Usually works well
                       │
                       ├─ Quarter Quotas
                       │  ✅ Usually works well
                       │
                       ├─ Closing Expansion
                       │  ✅ Usually works well
                       │
                       ├─ Semantic Splitting
                       │  ⚠️  Type inheritance failure → NEUTRAL spam
                       │
                       └─ Final Merge Pass
                          ⚠️  MISSING → consecutive same-type not fixed
```

**Problem Patterns Created:**
- Semantic split spam (type inheritance failure)
- Consecutive same-type moments (no final merge)
- Redundant neutrals (no final merge)

---

## Data Flow Through Problem Zones

### Example: FLIP/TIE Chain Formation

```
Play 50: Score 45-47 (away leads by 2, tier 0)
Play 51: Score 47-47 (tied)
         ↓
    [Boundary Detection]
    TIE hysteresis = 1 play
    ✅ TIE boundary created
         ↓
Play 52: Score 49-47 (home leads by 2, tier 0)
         ↓
    [Boundary Detection]
    FLIP hysteresis = 2 plays
    ⏳ Waiting for confirmation...
         ↓
Play 53: Score 51-47 (home leads by 4, tier 1)
         ↓
    [Boundary Detection]
    ✅ FLIP boundary created (confirmed)
         ↓
Play 54: Score 51-49 (home leads by 2, tier 0)
         ↓
    [Boundary Detection]
    Tier drop: 1 → 0
    ✅ CUT boundary created
         ↓
Play 55: Score 51-51 (tied)
         ↓
    [Boundary Detection]
    ⚠️  Density gating check:
        - 3 FLIP/TIE boundaries in last 5 plays
        - Window = 8 plays
        - NOT GATED (within window)
    ✅ TIE boundary created
         ↓
    [Moment Creation]
    Moments created:
    - m_010: NEUTRAL (plays 40-50)
    - m_011: TIE (plays 51-51)      ← 1 play
    - m_012: FLIP (plays 52-53)     ← 2 plays
    - m_013: CUT (plays 54-54)      ← 1 play
    - m_014: TIE (plays 55-55)      ← 1 play
         ↓
    ⚠️  PROBLEM: 4 moments in 5 plays (FLIP/TIE chain)
```

**Root Cause:** Density gating window (8 plays) too small to catch this sequence.

**Fix:** Increase window to 12 plays or 180 seconds.

---

### Example: Consecutive Same-Type Formation

```
    [After Boundary Detection]
    Moments:
    - m_005: LEAD_BUILD (Q1 8:00-6:30, tier 0→1)
    - m_006: LEAD_BUILD (Q1 6:30-5:00, tier 1→2)
    - m_007: LEAD_BUILD (Q1 5:00-3:30, tier 2→3)
         ↓
    [Merge Consecutive Moments]
    LEAD_BUILD in ALWAYS_MERGE_TYPES
    ✅ Merged to: m_005: LEAD_BUILD (Q1 8:00-3:30)
         ↓
    [Narrative Selection]
    Select top moments by importance
         ↓
    [Construction: Semantic Splitting]
    m_005 has 35 plays (> 18 threshold)
    Split at tier crossings:
    - m_005a: LEAD_BUILD (Q1 8:00-6:30, tier 0→1)
    - m_005b: LEAD_BUILD (Q1 6:30-5:00, tier 1→2)
    - m_005c: LEAD_BUILD (Q1 5:00-3:30, tier 2→3)
         ↓
    ⚠️  PROBLEM: Split recreated consecutive LEAD_BUILD moments
    ⚠️  PROBLEM: No final merge pass to fix this
```

**Root Cause:** Splitting happens after merging, and no final merge pass exists.

**Fix:** Add final merge pass after all construction phases.

---

## Configuration Impact Map

```
┌────────────────────────────────────────────────────────────────┐
│  Configuration Parameter → Impact on Pipeline                  │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  FLIP_TIE_DENSITY_WINDOW_PLAYS                                 │
│    ↓                                                           │
│  [Boundary Detection] → Density Gating                         │
│    ↓                                                           │
│  Fewer FLIP/TIE boundaries → Fewer FLIP/TIE moments           │
│                                                                │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  DEFAULT_FLIP_HYSTERESIS_PLAYS                                 │
│    ↓                                                           │
│  [Boundary Detection] → FLIP Confirmation                      │
│    ↓                                                           │
│  Delayed FLIP detection → Fewer FLIP moments                  │
│                                                                │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  DECIDED_GAME_SAFE_MARGIN                                      │
│    ↓                                                           │
│  [Boundary Detection] → Late-Game Suppression                  │
│    ↓                                                           │
│  More aggressive suppression → Fewer late CUT moments         │
│                                                                │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  ENABLE_POST_CONSTRUCTION_MERGE (NEW)                          │
│    ↓                                                           │
│  [Construction] → Final Merge Pass                             │
│    ↓                                                           │
│  Merge consecutive same-type → Fewer duplicate moments        │
│                                                                │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  SEMANTIC_SPLIT_INHERIT_TYPE (NEW)                             │
│    ↓                                                           │
│  [Construction] → Semantic Splitting                           │
│    ↓                                                           │
│  Preserve parent type → Fewer NEUTRAL spam                    │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

---

## Moment Type Flow

```
┌─────────────────────────────────────────────────────────────────┐
│  Boundary Type → Moment Type → Notable?                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  tier_up (tier Δ ≥ 2)   → LEAD_BUILD   → ✅ Notable            │
│  tier_up (tier Δ < 2)   → LEAD_BUILD   → ❌ Not notable        │
│                                                                 │
│  tier_down (tier Δ ≥ 2) → CUT          → ✅ Notable            │
│  tier_down (tier Δ < 2) → CUT          → ❌ Not notable        │
│                                                                 │
│  flip                   → FLIP         → ✅ Notable (always)    │
│  tie                    → TIE          → ✅ Notable (always)    │
│  closing_lock           → CLOSING_CONTROL → ✅ Notable (always) │
│  high_impact            → HIGH_IMPACT  → ✅ Notable (always)    │
│                                                                 │
│  (no boundary)          → NEUTRAL      → ❌ Not notable         │
│                                                                 │
│  (recap boundary)       → *_RECAP      → ✅ Notable (always)    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Validation Checkpoints

```
┌─────────────────────────────────────────────────────────────────┐
│  Stage → Validation → What's Checked                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  NORMALIZE_PBP                                                  │
│    ↓                                                            │
│  Score Continuity Check                                         │
│    • No score jumps                                             │
│    • Monotonically increasing                                   │
│                                                                 │
│  GENERATE_MOMENTS                                               │
│    ↓                                                            │
│  Moment Continuity Check                                        │
│    • No gaps in play coverage                                   │
│    • No overlaps                                                │
│    • Chronologically ordered                                    │
│                                                                 │
│  FINALIZE_MOMENTS                                               │
│    ↓                                                            │
│  Budget Compliance Check                                        │
│    • Total moments ≤ sport budget                               │
│    • Moments per quarter ≤ 7                                    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Debugging Flow

When a problem is detected in the output:

```
Problem Detected
    ↓
Identify Pattern
    ↓
┌─────────────────────────────────────────────────┐
│  FLIP/TIE Chain?                                │
│    → Check: Boundary Detection (Stage 3.1)      │
│    → Tune: Density gating parameters            │
├─────────────────────────────────────────────────┤
│  Consecutive Same Type?                         │
│    → Check: Merge Logic (Stage 3.3)             │
│    → Fix: Add final merge pass                  │
├─────────────────────────────────────────────────┤
│  Redundant Neutrals?                            │
│    → Check: Merge Logic (Stage 3.3)             │
│    → Fix: Aggressive NEUTRAL absorption         │
├─────────────────────────────────────────────────┤
│  False Drama Cuts?                              │
│    → Check: Late-Game Suppression (Stage 3.1)   │
│    → Tune: Safe margin threshold                │
├─────────────────────────────────────────────────┤
│  Semantic Split Spam?                           │
│    → Check: Splitting Logic (Stage 4.3)         │
│    → Fix: Type inheritance                      │
└─────────────────────────────────────────────────┘
    ↓
Apply Fix
    ↓
Re-run Analysis
    ↓
Compare Metrics
```

---

## Related Documentation

- `docs/PROMPT_0_BASELINE_REPORT.md` - Full baseline analysis
- `docs/PIPELINE_CONFIG_REFERENCE.md` - Configuration reference
- `docs/MOMENT_SYSTEM_CONTRACT.md` - Moment system contract
- `data/analysis/README.md` - Analysis guide

---

**Diagram Version:** 1.0  
**Last Updated:** 2026-01-21
