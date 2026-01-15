# PBP Timestamp Usage Rules

> **Status:** Canonical  
> **Parent Contract:** [NARRATIVE_TIME_MODEL.md](./NARRATIVE_TIME_MODEL.md)  
> **Last Updated:** 2026-01-14

---

## Context

Play-by-play events have a `synthetic_timestamp` computed from:
- Game start time
- Quarter/period number
- Game clock value

This timestamp is **estimated**, not observed. It represents approximately when the play occurred in wall-clock time, derived from game clock math.

---

## The Three Rules

### Rule 1: Timestamps Assign Buckets

PBP timestamps determine which **narrative phase** an event belongs to.

```
Q1 game clock 8:45 → phase: q1
Q3 game clock 2:30 → phase: q3
Q4 game clock 0:00 → phase: q4
```

**Use for:** Sectioning the timeline into logical chunks.

**Do not use for:** Precise millisecond ordering against external events.

---

### Rule 2: Buckets Define Reading Order

Within a phase, events are sorted by synthetic timestamp. This produces a **reading order** — the sequence a user experiences.

```
[q2] 6:30 → Dončić makes 3-pt shot
[q2] 6:15 → Tweet: "LUKA!"
[q2] 6:02 → Green defensive rebound
```

**Use for:** Interleaving PBP and social events into a coherent stream.

**Do not use for:** Claiming the tweet was posted exactly 15 seconds after the shot.

---

### Rule 3: Timestamps Do Not Imply Causality

A social post appearing after a PBP event in the timeline does **not** mean:
- The post was a reaction to that specific play
- The post was authored after the play occurred
- The events are related

Timeline proximity is **narrative**, not **causal**.

```
[q3] 4:12 → Booker turnover
[q3] 4:10 → Tweet: "Defense stepping up!"

// These may be unrelated. The tweet might be about
// a sequence from 30 seconds ago. That's fine.
```

**Use for:** Telling a story that feels coherent.

**Do not use for:** Inferring that tweet X is about play Y.

---

## Implementation Guidance

### For Timeline Generator

```python
# CORRECT: Use timestamp for phase bucketing
phase = get_phase_from_timestamp(event.synthetic_timestamp)

# CORRECT: Sort by timestamp within phase
events_in_phase.sort(key=lambda e: e.synthetic_timestamp)

# INCORRECT: Assume causal relationship
if tweet.timestamp > play.timestamp:
    tweet.is_reaction_to = play  # NO - don't do this
```

### For App Rendering

```swift
// CORRECT: Display events in timeline order
for event in timeline {
    renderEvent(event)
}

// CORRECT: Use phase for section headers
let sections = timeline.groupBy { $0.phase }

// INCORRECT: Show "Posted 15 seconds after play"
let timeSincePlay = tweet.timestamp - previousPlay.timestamp  // NO
```

### For Social Post Matching

```python
# CORRECT: Associate post with game by time window
if game.start <= post.posted_at <= game.end + buffer:
    post.game_id = game.id

# INCORRECT: Associate post with specific play
post.related_play_id = find_nearest_play(post.posted_at)  # NO
```

---

## Why This Matters

### The Math Is Approximate

PBP timestamps are computed as:

```python
quarter_start = game_start + (quarter - 1) * quarter_duration
seconds_elapsed = quarter_seconds - parse_clock(game_clock)
synthetic_timestamp = quarter_start + seconds_elapsed
```

This assumes:
- Quarters are exactly 12 minutes ❌ (stoppages exist)
- Games start on time ❌ (they rarely do)
- Clock parsing is perfect ❌ (edge cases exist)

**Result:** Timestamps are ~correct but not precise.

### Social Posts Are Also Approximate

Tweet `posted_at` reflects when Twitter recorded the post, not when:
- The user started typing
- The user saw the play
- The play actually happened

**Result:** A "reaction" tweet might appear 30-90 seconds after the play it references.

### Combining Two Approximations

Interleaving PBP (estimated) with social (delayed) produces a **plausible** narrative, not a **precise** one.

This is acceptable. The goal is storytelling, not forensic reconstruction.

---

## Quick Reference

| Use Case | Timestamp Role | Correct? |
|----------|---------------|----------|
| Assign event to Q3 | Phase bucket | ✅ |
| Sort events within Q3 | Reading order | ✅ |
| Group by quarter for UI sections | Phase bucket | ✅ |
| "This tweet was posted 10 seconds after the dunk" | Causality | ❌ |
| Link tweet to specific play programmatically | Causality | ❌ |
| Display "2 minutes ago" relative to play | Causality | ❌ |

---

## Changelog

| Date | Change |
|------|--------|
| 2026-01-14 | Initial rules defined |
