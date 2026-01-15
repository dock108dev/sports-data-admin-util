# Narrative Time Model

> **Status:** Canonical  
> **Scope:** All timeline-consuming systems (API, iOS app, web)  
> **Last Updated:** 2026-01-14

---

## Core Principle

**Narrative time is the primary ordering model. Wall-clock time is secondary and approximate.**

A game timeline is a story, not a log. Events are ordered by when they matter to the narrative, not when they occurred in the real world.

---

## Definitions

### Narrative Time
The logical position of an event within the story of the game. Expressed as a **phase** + **sequence index**.

Narrative time answers: *"Where does this event belong in the experience?"*

### Wall-Clock Time
The real-world UTC timestamp when an event occurred (e.g., when a tweet was posted, when a play happened). 

Wall-clock time answers: *"When did this actually happen?"*

### Synthetic Timestamp
A computed timestamp used for sorting. Derived from narrative position, not from wall-clock time. Exists solely for merge-sorting heterogeneous event types.

---

## Narrative Phases

Every timeline event belongs to exactly one phase:

| Phase | Code | Description | Typical Duration |
|-------|------|-------------|------------------|
| **Pregame** | `pregame` | Before tip-off. Lineups, predictions, hype. | -2h to tip |
| **Q1** | `q1` | First quarter/period | ~12 min |
| **Q2** | `q2` | Second quarter/period | ~12 min |
| **Halftime** | `halftime` | Intermission | ~15-20 min |
| **Q3** | `q3` | Third quarter/period | ~12 min |
| **Q4** | `q4` | Fourth quarter/period | ~12 min |
| **Overtime** | `ot`, `ot2`, ... | Overtime periods | ~5 min each |
| **Postgame** | `postgame` | After final whistle. Reactions, highlights, analysis. | +2h from final |

---

## Event Assignment Rules

### Play-by-Play Events
- **Phase:** Derived from `quarter` field (1→q1, 2→q2, etc.)
- **Position within phase:** Derived from `game_clock` (descending: 12:00 → 0:00)
- **Synthetic timestamp:** Computed from phase start + clock-based progress

### Social Events (Tweets)
- **Phase:** Derived from wall-clock time relative to game window
- **Position within phase:** Wall-clock order within that phase
- **Synthetic timestamp:** Actual `posted_at` value

### Phase Assignment for Social Events

```
if posted_at < game_start:
    phase = "pregame"
elif posted_at < q1_end:
    phase = "q1"
elif posted_at < q2_end:
    phase = "q2"
elif posted_at < halftime_end:
    phase = "halftime"
elif posted_at < q3_end:
    phase = "q3"
elif posted_at < q4_end:
    phase = "q4"
elif posted_at < game_end + buffer:
    phase = "postgame"
else:
    phase = "postgame"  # Late reactions still belong to this game
```

---

## Ordering Guarantees

### Within a Phase
Events are ordered by their **synthetic timestamp**. This produces an interleaved stream where PBP and social events appear in narrative order.

**Guarantee:** All events in phase N appear before all events in phase N+1.

### Across Event Types
No strict ordering guarantee between a PBP event and a social event with the same synthetic timestamp. Ties are acceptable; consumers should not depend on sub-second ordering.

### Stability
The same input data always produces the same output order. Timeline generation is deterministic.

---

## What This Model Does NOT Guarantee

1. **Wall-clock accuracy:** A tweet's `synthetic_timestamp` may differ from its `posted_at` if we adjust for narrative flow.

2. **Real-time ordering:** A tweet posted at 8:45 PM might appear in the Q3 phase even if Q3 "officially" started at 8:50 PM by the broadcast clock.

3. **Completeness:** Not all wall-clock events become narrative events. Filtering is intentional.

---

## Consumer Contracts

### For the iOS/Web App
- **DO:** Use `synthetic_timestamp` for display ordering
- **DO:** Use phase codes for UI sectioning (if needed)
- **DON'T:** Parse synthetic timestamps as real times for display
- **DON'T:** Assume tweets and PBP interleave perfectly by real time

### For the Timeline Generator
- **DO:** Assign every event a phase and synthetic timestamp
- **DO:** Filter events that don't belong to the game narrative
- **DON'T:** Include events outside the narrative window without explicit phase assignment

### For the Scraper
- **DO:** Store wall-clock `posted_at` for all social events
- **DO:** Associate posts with games based on time windows
- **DON'T:** Pre-filter based on synthetic time (that's the generator's job)

---

## Example

**Wall-clock reality:**
```
19:58:00  Tweet: "Let's go Suns!"
20:00:00  Tip-off
20:02:15  PBP: Jump ball won by Green
20:03:00  Tweet: "Great start!"
```

**Narrative timeline:**
```
[pregame]  Tweet: "Let's go Suns!"     synthetic: 2025-11-24T19:58:00
[q1]       PBP: Jump ball              synthetic: 2025-11-24T20:00:00
[q1]       Tweet: "Great start!"       synthetic: 2025-11-24T20:03:00
```

The pregame tweet stays in pregame even though it's only 2 minutes before tip. The narrative phase boundary is the source of truth.

---

## Rationale

Real-world sports timelines are messy:
- Games start late
- Broadcasts have delays
- Teams post reactions minutes after plays
- Overtime changes the expected timeline

By defining narrative time as primary, we:
1. Create a stable, predictable structure for the app
2. Avoid chasing exact real-time synchronization
3. Allow intentional curation of the story

---

## Changelog

| Date | Change |
|------|--------|
| 2026-01-14 | Initial canonical definition |
