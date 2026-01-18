# Compact Mode

> **Status:** Canonical  
> **Parent Contract:** [TIMELINE_ASSEMBLY.md](./TIMELINE_ASSEMBLY.md)  
> **Last Updated:** 2026-01-14

---

## Purpose

Compact mode reduces timeline density while preserving narrative coherence. It compresses **routine action** and preserves **meaningful moments** — without revealing scores or outcomes.

---

## Core Principle

> **Compress the predictable. Preserve the surprising.**

A timeline in compact mode should feel like watching highlights with context, not a raw play-by-play log.

---

## Compressibility Rules

### Never Compress (Always Show)

| Unit Type | Rationale |
|-----------|-----------|
| **Social posts** | Human voice; always intentional |
| **Scoring plays** | Narrative anchor points |
| **Lead changes** | Story inflection points |
| **Period boundaries** | Structural markers (end of Q1, halftime, etc.) |
| **First play of period** | Establishes phase transition |
| **Last play of period** | Closes the phase |
| **Technical fouls / ejections** | Rare, dramatic events |
| **Injury stoppages** | Context-critical |
| **Timeout in final 2 min** | Strategic moment |
| **Milestone events** | Career-high, triple-double, etc. |

### Always Compress (Collapse)

| Unit Type | Rationale |
|-----------|-----------|
| **Substitution sequences** | Routine roster management |
| **Back-to-back misses without action** | Dead possessions |
| **Repeated fouls in bonus** | Routine free throw parade |
| **Jump balls (non-opening)** | Procedural |
| **Offensive rebounds → immediate miss** | Failed second chance |

### Conditionally Compress (Context-Dependent)

| Unit Type | Show If... | Compress If... |
|-----------|------------|----------------|
| **Defensive rebounds** | Ends a run, precedes fast break | Routine possession change |
| **Turnovers** | Leads to score, in final 2 min | Mid-quarter, no consequence |
| **Assists** | Part of scoring play | Standalone mention |
| **Blocks** | Leads to fast break | Routine stop |
| **Steals** | Leads to score | Mid-possession |

---

## Moments (Narrative Units)

> **LEAD LADDER REWRITE (2026-01):** Moment detection is now based on **Lead Ladder**
> tier crossings, not pattern matching. The old `RUN`, `BATTLE`, `CLOSING` types have
> been replaced with more precise crossing-based types.

Compact mode operates on **Moments**, not individual plays. A Moment is a contiguous sequence of plays that form a coherent narrative unit.

### Moment Types (Lead Ladder v2)

| MomentType | Definition | Compression Behavior |
|------------|------------|---------------------|
| **LEAD_BUILD** | Lead tier increased | Light compression (show key plays) |
| **CUT** | Lead tier decreased (comeback) | Light compression (show key plays) |
| **TIE** | Game returned to even | Never compress |
| **FLIP** | Leader changed | Never compress |
| **CLOSING_CONTROL** | Late-game lock-in (dagger) | Never compress |
| **HIGH_IMPACT** | Ejection, injury, etc. | Never compress |
| **NEUTRAL** | Normal flow, no tier changes | Heavy compression |

### Moment Detection (Lead Ladder)

```python
# moments/ package - Lead Ladder-based partitioning
def partition_game(timeline, summary, thresholds):
    """
    Partition timeline into Moments based on Lead Ladder tier crossings.
    
    GUARANTEES:
    1. Every play belongs to exactly one Moment
    2. Moments are contiguous (no gaps)
    3. Moments are chronologically ordered
    4. Boundaries occur only on tier crossings
    
    Args:
        timeline: Full timeline events
        summary: Game summary metadata
        thresholds: Lead Ladder thresholds (sport-specific, e.g., [3,6,10,16] for NBA)
    """
    # Detect tier crossings using Lead Ladder
    boundaries = _detect_boundaries(timeline, thresholds)
    
    # Create moments from boundaries
    # Types are determined by crossing type:
    # - TIER_UP → LEAD_BUILD
    # - TIER_DOWN → CUT
    # - FLIP → FLIP
    # - TIE_REACHED → TIE
    # ...
    
    # Attach runs as metadata (not separate moments)
    runs = _detect_runs(timeline)
    _attach_runs_to_moments(moments, runs)
    
    return moments
```

---

## Compression Levels

Compact mode has three density levels:

| Level | Name | Retention Rate | Use Case |
|-------|------|----------------|----------|
| 1 | **Highlights** | ~15-20% of PBP | Quick recap |
| 2 | **Standard** | ~40-50% of PBP | Default compact |
| 3 | **Detailed** | ~70-80% of PBP | Engaged viewing |

### Level Application by Group Type

| Group Type | Level 1 | Level 2 | Level 3 |
|------------|---------|---------|---------|
| Scoring Run | All scores | All scores | All scores + key assists |
| Swing | Pivot play only | Pivot + setup | Full sequence |
| Drought | Summary marker | Start + end | Start + mid + end |
| Finish | Full | Full | Full |
| Opener | First + last | First 3 + last | Light trim |
| Routine | Skip entirely | Bookend plays | Every 3rd play |

---

## Excitement Inference

Compact mode infers excitement **without exposing scores** using these signals:

### Excitement Signals (Score-Blind)

| Signal | Weight | Detection |
|--------|--------|-----------|
| **Pace** | High | Short clock between plays |
| **Social density** | High | Multiple tweets in short window |
| **Play type variety** | Medium | Blocks, steals, dunks vs. jump shots |
| **Foul frequency** | Medium | Indicates physical play |
| **Timeout clustering** | High | Strategic moments |
| **Substitution absence** | Medium | Teams not resting starters |

### Excitement Score (Internal Only)

```python
def compute_excitement(group):
    """
    Returns 0.0 - 1.0 excitement score.
    Used internally for compression decisions.
    Never exposed to UI or API responses.
    """
    score = 0.0
    
    # Pace signal
    avg_seconds_between_plays = group.avg_play_gap()
    if avg_seconds_between_plays < 20:
        score += 0.3
    
    # Social density
    tweets_in_window = count_tweets_in_group_window(group)
    if tweets_in_window >= 2:
        score += 0.25
    elif tweets_in_window == 1:
        score += 0.1
    
    # Play type variety
    exciting_play_types = {"dunk", "block", "steal", "three_pointer", "and_one"}
    exciting_count = sum(1 for p in group.plays if p.play_type in exciting_play_types)
    score += min(exciting_count * 0.1, 0.3)
    
    # Late game
    if group.is_final_minutes():
        score += 0.2
    
    return min(score, 1.0)
```

### Excitement → Compression Mapping

| Excitement | Compression Behavior |
|------------|---------------------|
| 0.0 - 0.3 | Maximum compression (routine) |
| 0.3 - 0.6 | Standard compression |
| 0.6 - 0.8 | Light compression |
| 0.8 - 1.0 | No compression (show all) |

---

## Compression Output

Compressed plays are replaced with **summary markers**, not deleted entirely.

### Summary Marker Schema

```json
{
  "event_type": "summary",
  "phase": "q2",
  "summary_type": "routine",
  "plays_compressed": 8,
  "duration_seconds": 145,
  "description": "Back-and-forth possession play",
  "synthetic_timestamp": "2025-11-24T00:25:00+00:00"
}
```

### Summary Types

| Type | Description | Example Text |
|------|-------------|--------------|
| `routine` | Normal game flow | "Back-and-forth play" |
| `drought` | Scoring lull | "Both teams cold from the field" |
| `free_throws` | FT sequence | "Free throw shooting" |
| `subs` | Substitution parade | "Both teams make substitutions" |
| `review` | Official review | "Play under review" |

---

## Social Post Handling

### Rule: Social Posts Are Never Compressed

```python
def apply_compression(timeline, level):
    compressed = []
    
    for event in timeline:
        if event.event_type == "tweet":
            # ALWAYS include social posts
            compressed.append(event)
        elif event.event_type == "pbp":
            if should_retain(event, level):
                compressed.append(event)
            else:
                # Accumulate for summary marker
                pending_compression.append(event)
        elif event.event_type == "summary":
            # Already compressed, pass through
            compressed.append(event)
    
    return compressed
```

### Social Posts Create Compression Boundaries

When a social post appears, any pending compression group is finalized:

```python
# Social posts "cut" compression groups
if event.event_type == "tweet":
    if pending_compression:
        compressed.append(create_summary_marker(pending_compression))
        pending_compression = []
    compressed.append(event)
```

This ensures social posts never float away from their narrative context.

---

## Example

### Full Timeline (12 events)
```
[q2] PBP: Booker misses jumper
[q2] PBP: Green defensive rebound
[q2] PBP: Thompson turnover
[q2] PBP: Booker misses three
[q2] PBP: Howard offensive rebound
[q2] PBP: Howard misses layup
[q2] Tweet: "Defense is locked in 🔒"
[q2] PBP: Smith defensive rebound
[q2] PBP: Smith to Johnson
[q2] PBP: Johnson three-pointer MADE ← scoring play
[q2] Tweet: "BANG! 💥"
[q2] PBP: Timeout Phoenix
```

### Compact Level 2 (6 events)
```
[q2] Summary: "Defensive struggle" (6 plays compressed)
[q2] Tweet: "Defense is locked in 🔒"
[q2] PBP: Smith to Johnson
[q2] PBP: Johnson three-pointer MADE
[q2] Tweet: "BANG! 💥"
[q2] PBP: Timeout Phoenix
```

**Note:** Both tweets preserved. Scoring play and timeout preserved. Routine misses compressed.

---

## Implementation Checklist

- [x] Group detection implemented for all group types
- [x] Excitement scoring uses only score-blind signals
- [x] Social posts never compressed
- [x] Social posts create compression boundaries
- [x] Summary markers include play count and duration
- [x] Compression levels are configurable
- [x] Period boundaries always preserved
- [x] Scoring plays always preserved

## API Endpoint

```
GET /api/games/{game_id}/timeline/compact?level=2
```

**Parameters:**
- `level`: Compression level (1=highlights, 2=standard, 3=detailed)

**Response includes:**
- `compression_level`: The applied level
- `original_event_count`: Events before compression
- `compressed_event_count`: Events after compression
- `retention_rate`: Percentage retained
- `timeline_json`: Compressed timeline with summary markers

---

## Changelog

| Date | Change |
|------|--------|
| 2026-01-14 | First real implementation: semantic groups, excitement scoring, summary markers |
| 2026-01-14 | Initial compact mode definition |
