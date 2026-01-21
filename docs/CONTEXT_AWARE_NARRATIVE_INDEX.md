# Context-Aware Narrative System — Complete Index

**Status:** ✅ PHASES 1-3 COMPLETE  
**Date:** 2026-01-21  
**Ready For:** Testing and validation

---

## Quick Navigation

| Phase | Document | Status | Purpose |
|-------|----------|--------|---------|
| **Prompt 0** | [Baseline Report](#prompt-0-baseline) | ✅ Complete | Pipeline analysis and root causes |
| **Prompt 1** | [Context Loss Analysis](#prompt-1-context-loss) | ✅ Complete | Where and why context is lost |
| **Prompt 2** | [Context Plumbing](#prompt-2-context-plumbing) | ✅ Complete | Attach context data (no behavior change) |
| **Phase 3** | [AI Integration](#phase-3-ai-integration) | ✅ Complete | Context-aware AI enrichment |
| **Phase 4** | [Structural Dampening](#phase-4-structural-dampening) | ✅ Complete | Narrative coherence enforcement |

---

## Prompt 0: Baseline

### Documents
- `docs/PROMPT_0_BASELINE_REPORT.md` (deleted, replaced by analysis)
- `docs/PROMPT_0_SUMMARY.md` (deleted)
- `scripts/analyze_baseline_metrics.py` - Analysis tool

### Key Findings
- 5 root causes identified
- 16 configuration parameters documented
- 5 problem patterns with detection rules
- Minimal config surface proposed

### Outputs for Future Steps
- Baseline metrics schema
- Problem pattern detection rules
- Configuration reference
- Acceptance test list

---

## Prompt 1: Context Loss

### Documents
- `docs/PROMPT_1_CONTEXT_LOSS_ANALYSIS.md` - Full analysis
- `docs/PROMPT_1_SUMMARY.md` - Executive summary
- `docs/PROMPT_1_CONTEXT_FLOW_DIAGRAM.md` - Visual diagrams
- `docs/PROMPT_1_INDEX.md` - Master index

### Key Findings
- 3 critical context loss junctions identified
- 8 phase signals exist but are dropped
- 3 types of redundancy classified
- Minimal context contract proposed (12 fields)

### Solution Proposed
`MomentContext` payload with:
- Phase awareness (4 fields)
- Narrative continuity (4 fields)
- Volatility context (2 fields)
- Control context (3 fields)

---

## Prompt 2: Context Plumbing

### Documents
- `docs/PROMPT_2_IMPLEMENTATION_REPORT.md` - Technical report
- `docs/PROMPT_2_SUMMARY.md` - Executive summary

### Implementation
✅ **Phase 1:** Game phase state attached to every moment  
✅ **Phase 2:** Previous moment tracking in creation loop  
✅ **Phase 3:** MomentContext payload built and attached  

### Files Modified
1. `api/app/services/moments/types.py` - Added `MomentContext`, enhanced `Moment`
2. `api/app/services/moments/helpers.py` - Added `build_moment_context()`, enhanced `create_moment()`
3. `api/app/services/moments/partition.py` - Enhanced `partition_game()` with context tracking
4. `api/app/services/moments_merging.py` - Enhanced `merge_two_moments()` to preserve context

**Result:** Every moment has memory and awareness (no behavior changes)

---

## Phase 3: AI Integration

### Documents
- `docs/PHASE_3_IMPLEMENTATION_REPORT.md` - Technical report
- `docs/PHASE_3_SUMMARY.md` - Executive summary

### Implementation
✅ **Task 3.1:** Extended AI input contract with context  
✅ **Task 3.2:** Rewrote AI prompt with 5 narrative rules  
✅ **Task 3.3:** Added narrative intent hints  
✅ **Task 3.4:** Implemented hard constraint validation  

### Files Modified
1. `api/app/services/ai_client.py` - Enhanced input, prompt, validation
2. `api/app/services/game_analysis.py` - Enhanced input builder

**Result:** AI generates context-aware text (behavior changes)

---

## Complete Feature Overview

### What Changed

**Moment Generation:** UNCHANGED
- Same boundaries detected
- Same moments created
- Same merge logic
- Same selection logic

**Moment Data:** ENHANCED
- Every moment has `phase_state`
- Every moment has `narrative_context`
- Context preserved through merges
- Context serialized in API responses

**AI Enrichment:** TRANSFORMED
- AI receives 10 context signals per moment
- AI follows 5 narrative awareness rules
- AI respects 4 hard constraints
- AI generates varied, context-aware text

---

## Context Signals (15 Total)

### Phase Awareness (6 signals)
1. `game_phase` - "opening" | "middle" | "closing"
2. `phase_progress` - 0.0 to 1.0
3. `is_overtime` - Boolean
4. `is_closing_window` - Boolean
5. `elapsed_seconds` - Total elapsed
6. `remaining_seconds` - Total remaining

### Narrative Continuity (4 signals)
7. `previous_moment_type` - What came before
8. `previous_narrative_delta` - What was established
9. `is_continuation` - Extending vs reversing
10. `parent_moment_id` - If split from another

### Volatility Context (2 signals)
11. `recent_flip_tie_count` - FLIPs/TIEs in window
12. `volatility_phase` - "stable" | "volatile" | "back_and_forth"

### Control Context (3 signals)
13. `controlling_team` - "home" | "away" | null
14. `control_duration` - Consecutive same-control
15. `tier_stability` - "stable" | "oscillating" | "shifting"

---

## AI Narrative Rules (5 Rules)

### Rule 1: Continuity Awareness
**Trigger:** `is_continuation = true`  
**Behavior:** Use continuation language ("continues", "extends")  
**Fixes:** Repeated "chip away", generic "momentum shift"

### Rule 2: Phase Sensitivity
**Trigger:** `game_phase` value  
**Behavior:** Match urgency to game phase  
**Fixes:** Early-game urgency, premature resolution

### Rule 3: Volatility Constraints
**Trigger:** `recent_flip_tie_count`, `volatility_phase`  
**Behavior:** Describe sequence, not isolated events  
**Fixes:** FLIP/TIE chain repetition

### Rule 4: Control Memory
**Trigger:** `control_duration >= 2`  
**Behavior:** Use "continues" not "takes"  
**Fixes:** Repeated "takes control"

### Rule 5: Late-Game False Drama Guard
**Trigger:** `game_phase = "closing"` + stable control  
**Behavior:** Downshift language  
**Fixes:** Garbage time drama

---

## Hard Constraints (4 Enforced)

1. ❌ **No urgency in opening** - "crucial", "desperate" in Q1
2. ❌ **No shift with stable** - "swing", "surge" when stable
3. ❌ **No resolution outside closing** - "seals", "locks up" in Q1-Q3
4. ❌ **No repeated "comeback"** - Multiple consecutive comeback language

**Enforcement:** Validation logs violations as warnings

---

## Expected Improvements

### Quantitative Targets

| Metric | Target | Measurement |
|--------|--------|-------------|
| "Chip away" frequency | < 2 per game | Count in summaries |
| Early-game "crucial" | 0 instances | Count in Q1 moments |
| FLIP/TIE chain variety | 80%+ unique | Distinct phrases / total |
| Continuation language | 70%+ | "continues", "extends", etc. |
| Control awareness | Present | "maintains", "keeps" when duration >= 2 |

### Qualitative Targets

**Does this read like someone who watched the game?**
- ✅ Opening feels like setup, not crisis
- ✅ Middle feels like development, not chaos
- ✅ Closing feels like resolution (if appropriate)
- ✅ Language varies naturally
- ✅ Story has coherent arc

---

## Testing Workflow

### Step 1: Generate Test Timelines

```bash
# Test game 1: Blowout
POST /api/admin/sports/timelines/generate/109953

# Test game 2: Close game
POST /api/admin/sports/timelines/generate/{close_game_id}

# Test game 3: Back-and-forth
POST /api/admin/sports/timelines/generate/{volatile_game_id}
```

---

### Step 2: Inspect Moments

```bash
# Get moments with context
GET /api/admin/sports/games/{game_id}/moments

# Check for:
# - phase_state populated
# - narrative_context populated
# - context-aware headlines/summaries
```

---

### Step 3: Measure Improvements

```python
# Count "chip away" instances
grep -i "chip away" game_moments.json | wc -l

# Count "crucial" in Q1
grep "Q1" game_moments.json | grep -i "crucial" | wc -l

# Count unique phrases in FLIP/TIE chains
# (manual inspection)
```

---

### Step 4: Manual Review

Read 3 full game narratives:
1. Blowout - Should feel concise, intentional
2. Close game - Should feel worth scrolling
3. Back-and-forth - Should feel coherent, not chaotic

Ask:
- Does language vary naturally?
- Is urgency appropriate to phase?
- Do consecutive moments flow?
- Does it feel like a story?

---

## Code Locations

### Context Data Structures
```
api/app/services/moments/
├── types.py                    # MomentContext, enhanced Moment
└── helpers.py                  # build_moment_context()
```

### Context Attachment
```
api/app/services/moments/
├── partition.py                # Context tracking in partition_game()
└── helpers.py                  # Enhanced create_moment()
```

### Context Preservation
```
api/app/services/
└── moments_merging.py          # Preserve context in merges
```

### AI Integration
```
api/app/services/
├── ai_client.py                # Enhanced input, prompt, validation
└── game_analysis.py            # Enhanced input builder
```

---

## Rollback Plan

If Phase 3 doesn't improve narrative quality:

### Option 1: Revert AI Integration
```python
# In game_analysis.py:_build_enrichment_inputs()
# Remove context extraction, pass context=None
```

### Option 2: Adjust Prompt
- Relax constraints
- Adjust narrative rules
- Iterate on intent hints

### Option 3: Adjust Context
- Change volatility thresholds
- Adjust phase boundaries
- Tune sliding window size

**All reversible** - No structural changes to moment generation.

---

## Phase 4: Structural Dampening

### Documents
- `docs/PHASE_4_IMPLEMENTATION_REPORT.md` - Technical report
- `docs/PHASE_4_SUMMARY.md` - Executive summary

### Implementation
✅ **Task 4.1:** Narrative state machine (lightweight, explicit)  
✅ **Task 4.2:** Late-game false drama hard suppression  
✅ **Task 4.3:** Narrative dormancy detection  
✅ **Task 4.4:** Semantic split quality gate  
✅ **Task 4.5:** Final coherence pass (5-pass algorithm)  

### Files Modified
1. `api/app/services/moments/narrative_state.py` - State machine (NEW, 500 lines)
2. `api/app/services/moments/coherence.py` - Coherence enforcement (NEW, 450 lines)
3. `api/app/services/moments/partition.py` - Integration (+20 lines)

**Result:** Moment list represents genuine narrative state changes (structural fixes)

---

## Summary: What We Built

### Prompt 0 (Baseline)
- ✅ Pipeline analysis
- ✅ Root cause identification
- ✅ Configuration reference
- ✅ Analysis tooling

### Prompt 1 (Context Loss)
- ✅ Context loss junctions mapped
- ✅ Phase signals inventoried
- ✅ Redundancy taxonomy
- ✅ Minimal context contract

### Prompt 2 (Context Plumbing)
- ✅ MomentContext dataclass (12 fields)
- ✅ Phase state attachment
- ✅ Previous moment tracking
- ✅ Context building function

### Phase 3 (AI Integration)
- ✅ AI input contract extended
- ✅ AI prompt rewritten (5 rules)
- ✅ Narrative intent hints
- ✅ Hard constraint validation

**Total:** 3 prompts, 4 phases, ~17 documents, ~1800 lines of code

---

## Status: Ready for Testing

**Implementation:** COMPLETE  
**Syntax Validation:** PASS  
**Behavior Changes:** YES (AI output only)  
**Moment Generation:** UNCHANGED  
**Next:** Generate test timelines and validate improvements

---

**Index Version:** 2.0  
**Last Updated:** 2026-01-21  
**Total Work:** ~12 hours, 17 documents, 1800 lines of code
