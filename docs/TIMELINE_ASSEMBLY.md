# Timeline Assembly

> **Status:** Canonical
> **Last Updated:** 2026-01-14

---

## Purpose

This document defines the **exact recipe** for assembling a unified game timeline from heterogeneous event sources. The process is deterministic and explainable.

---

## Inputs

| Source | Fields Used | Count (typical) |
|--------|-------------|-----------------|
| PBP events | `quarter`, `game_clock`, `play_index`, `description` | 400-500 |
| Social posts | `posted_at`, `text`, `source_handle`, `media_type` | 0-50 |
| Game metadata | `game_date`, `home_team`, `away_team`, `final_score` | 1 |

---

## The Assembly Recipe

### Step 0: Compute Phase Boundaries

Before processing events, compute the time boundaries for each narrative phase.

```python
def compute_phase_boundaries(game):
    """
    Returns a dict of phase -> (start_time, end_time)
    """
    tip = game.game_date  # Scheduled start
    
    # Standard NBA timing (adjust per sport)
    QUARTER_DURATION = timedelta(minutes=12)
    HALFTIME_DURATION = timedelta(minutes=20)
    BUFFER_PREGAME = timedelta(hours=2)
    BUFFER_POSTGAME = timedelta(hours=2)
    
    boundaries = {
        "pregame": (tip - BUFFER_PREGAME, tip),
        "q1": (tip, tip + QUARTER_DURATION),
        "q2": (tip + QUARTER_DURATION, tip + 2 * QUARTER_DURATION),
        "halftime": (tip + 2 * QUARTER_DURATION, tip + 2 * QUARTER_DURATION + HALFTIME_DURATION),
        "q3": (tip + 2 * QUARTER_DURATION + HALFTIME_DURATION, tip + 3 * QUARTER_DURATION + HALFTIME_DURATION),
        "q4": (tip + 3 * QUARTER_DURATION + HALFTIME_DURATION, tip + 4 * QUARTER_DURATION + HALFTIME_DURATION),
        "postgame": (tip + 4 * QUARTER_DURATION + HALFTIME_DURATION, tip + 4 * QUARTER_DURATION + HALFTIME_DURATION + BUFFER_POSTGAME),
    }
    
    # Add overtime phases if detected from PBP
    # ...
    
    return boundaries
```

---

### Step 1: Assign PBP Events to Phases

Each PBP event is assigned to a phase based on its `quarter` field. The `game_clock` is used only for ordering within the phase.

```python
def assign_pbp_phase(play):
    """
    PBP phase assignment is direct from quarter number.
    """
    quarter = play.quarter
    
    if quarter == 1:
        return "q1"
    elif quarter == 2:
        return "q2"
    elif quarter == 3:
        return "q3"
    elif quarter == 4:
        return "q4"
    elif quarter > 4:
        return f"ot{quarter - 4}"
    else:
        return "unknown"
```

**Output:** Each PBP event now has a `phase` field.

---

### Step 2: Compute PBP Sort Keys

Within a phase, PBP events are ordered by game clock (descending → ascending progress).

```python
def pbp_sort_key(play):
    """
    Returns a sort key for ordering within phase.
    Lower key = earlier in phase.
    """
    phase = play.phase
    clock_seconds = parse_clock_to_seconds(play.game_clock)  # "8:45" → 525
    
    # Invert clock: 12:00 (720s) → 0, 0:00 (0s) → 720
    QUARTER_SECONDS = 720
    progress = QUARTER_SECONDS - clock_seconds
    
    return (phase_order(phase), progress, play.play_index)


def phase_order(phase):
    """Canonical phase ordering."""
    ORDER = {
        "pregame": 0,
        "q1": 1,
        "q2": 2,
        "halftime": 3,
        "q3": 4,
        "q4": 5,
        "ot1": 6,
        "ot2": 7,
        "ot3": 8,
        "postgame": 99,
    }
    return ORDER.get(phase, 50)
```

**Output:** Each PBP event has a deterministic sort key.

---

### Step 3: Assign Social Posts to Phases

Social posts are assigned to phases based on `posted_at` relative to phase boundaries.

```python
def assign_social_phase(post, boundaries):
    """
    Social phase assignment is from wall-clock time.
    """
    posted_at = post.posted_at
    
    for phase, (start, end) in boundaries.items():
        if start <= posted_at < end:
            return phase
    
    # Fallback: if after all phases, it's late postgame
    if posted_at >= boundaries["postgame"][1]:
        return "postgame"
    
    # If before all phases, it's early pregame
    return "pregame"
```

**Output:** Each social post now has a `phase` field.

---

### Step 4: Compute Social Sort Keys

Within a phase, social posts are ordered by `posted_at` (wall-clock time).

```python
def social_sort_key(post):
    """
    Returns a sort key for ordering within phase.
    """
    phase = post.phase
    
    return (phase_order(phase), post.posted_at, post.id)
```

**Note:** `post.id` is used as a tiebreaker for posts with identical timestamps.

---

### Step 5: Merge Events by Phase

Combine PBP and social events, grouped by phase, then sorted within each phase.

```python
def assemble_timeline(pbp_events, social_posts, boundaries):
    """
    The canonical timeline assembly algorithm.
    """
    # Step 1-2: Assign phases and sort keys to PBP
    for play in pbp_events:
        play.phase = assign_pbp_phase(play)
        play.sort_key = pbp_sort_key(play)
    
    # Step 3-4: Assign phases and sort keys to social
    for post in social_posts:
        post.phase = assign_social_phase(post, boundaries)
        post.sort_key = social_sort_key(post)
    
    # Step 5: Group by phase
    phases = defaultdict(list)
    
    for play in pbp_events:
        phases[play.phase].append(("pbp", play.sort_key, play))
    
    for post in social_posts:
        phases[post.phase].append(("social", post.sort_key, post))
    
    # Step 6: Sort within each phase
    timeline = []
    
    for phase in sorted(phases.keys(), key=phase_order):
        events_in_phase = phases[phase]
        
        # Sort by sort_key (phase_order is same, so this sorts by progress/time)
        events_in_phase.sort(key=lambda x: x[1])
        
        for event_type, sort_key, event in events_in_phase:
            timeline.append(to_timeline_event(event_type, event, phase))
    
    return timeline
```

---

### Step 6: Emit Timeline Events

Convert internal representations to the output schema.

```python
def to_timeline_event(event_type, event, phase):
    """
    Produce the canonical timeline event format.
    """
    if event_type == "pbp":
        return {
            "event_type": "pbp",
            "phase": phase,
            "quarter": event.quarter,
            "game_clock": event.game_clock,
            "play_index": event.play_index,
            "description": event.description,
            "team_id": event.team_id,
            "home_score": event.home_score,
            "away_score": event.away_score,
            "synthetic_timestamp": compute_synthetic_timestamp(event),
        }
    else:  # social
        return {
            "event_type": "tweet",
            "phase": phase,
            "role": assign_role(event),
            "author": event.source_handle,
            "handle": event.source_handle,
            "text": event.text,
            "synthetic_timestamp": event.posted_at.isoformat(),
        }
```

---

## Forbidden Patterns

### ❌ Global Timestamp Sort

```python
# FORBIDDEN: Do not do this
all_events = pbp_events + social_posts
all_events.sort(key=lambda e: e.timestamp)  # NO
```

**Why:** This treats timestamps as truth. Timestamps are approximate. Phase ordering is the source of truth.

### ❌ Interleave Without Phase Assignment

```python
# FORBIDDEN: Merging without explicit phases
merged = merge_by_time(pbp, social)  # NO
```

**Why:** This hides the phase assignment logic. Phases must be explicit and inspectable.

### ❌ Implicit Ordering Assumptions

```python
# FORBIDDEN: Assuming order from insertion
timeline = []
for play in pbp_events:
    timeline.append(play)
for post in social_posts:
    insert_at_right_position(timeline, post)  # NO
```

**Why:** This makes ordering dependent on implementation details. The recipe must be explicit.

---

## Guarantees

| Guarantee | Description |
|-----------|-------------|
| **Phase integrity** | All Q1 events appear before all Q2 events. Always. |
| **Determinism** | Same inputs → same output. No randomness. |
| **Explainability** | Every event's position can be explained by its phase + sort key. |
| **Inspectability** | The `phase` field is visible in output for debugging. |

---

## Visualization

```
INPUT:                          ASSEMBLY:                       OUTPUT:
                                
┌─────────────┐                 ┌──────────────┐                ┌─────────────────┐
│ PBP Events  │──► Assign ──►   │   pregame    │                │ [pregame]       │
│ (by quarter)│    Phase        │   ┌──────┐   │                │   Tweet: hype   │
└─────────────┘                 │   │social│   │                │   Tweet: lineup │
                                │   └──────┘   │  Sort within   ├─────────────────┤
┌─────────────┐                 ├──────────────┤  each phase    │ [q1]            │
│ Social Posts│──► Assign ──►   │      q1      │ ────────────►  │   PBP: tip-off  │
│ (by time)   │    Phase        │   ┌────┐     │                │   PBP: bucket   │
└─────────────┘                 │   │pbp │     │                │   Tweet: react  │
                                │   │pbp │     │                │   PBP: foul     │
                                │   │soc │     │                ├─────────────────┤
                                │   │pbp │     │                │ [q2]            │
                                │   └────┘     │                │   ...           │
                                ├──────────────┤                └─────────────────┘
                                │      q2      │
                                │     ...      │
                                └──────────────┘
```

---

## Implementation Checklist

- [ ] Phase boundaries computed from game metadata
- [ ] PBP events assigned phase from `quarter`
- [ ] Social posts assigned phase from `posted_at` vs boundaries
- [ ] Sort keys computed (phase_order, progress/time, tiebreaker)
- [ ] Events grouped by phase
- [ ] Events sorted within phase
- [ ] Output includes explicit `phase` field
- [ ] No global timestamp sort anywhere in pipeline

---

## Changelog

| Date | Change |
|------|--------|
| 2026-01-14 | Initial assembly recipe defined |
