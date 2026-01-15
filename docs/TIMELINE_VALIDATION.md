# Timeline Validation

> **Status:** Canonical  
> **Parent Contract:** [TIMELINE_ASSEMBLY.md](./TIMELINE_ASSEMBLY.md)  
> **Last Updated:** 2026-01-14

---

## Purpose

This document defines validation checks for generated timelines. Run these checks against every new timeline to catch regressions, weirdness, and narrative gaps before they reach users.

---

## Validation Levels

| Level | When to Run | Fails Block Publish? |
|-------|-------------|---------------------|
| **Critical** | Every timeline | Yes |
| **Warning** | Every timeline | No, but log |
| **Diagnostic** | On demand / debugging | No |

---

## Critical Checks

These must pass. Failures indicate broken logic.

### C1: Phase Order Integrity

```python
def check_phase_order(timeline):
    """
    All events in phase N must appear before all events in phase N+1.
    """
    phase_order = ["pregame", "q1", "q2", "halftime", "q3", "q4", "ot1", "ot2", "postgame"]
    
    last_phase_index = -1
    for event in timeline:
        phase = event.get("phase") or infer_phase(event)
        current_index = phase_order.index(phase) if phase in phase_order else 50
        
        if current_index < last_phase_index:
            return Fail(f"Phase regression: {phase} appeared after later phase")
        
        last_phase_index = max(last_phase_index, current_index)
    
    return Pass()
```

**Failure:** "Phase regression: q2 appeared after q3"

---

### C2: No Duplicate Events

```python
def check_no_duplicates(timeline):
    """
    No event should appear twice.
    """
    seen = set()
    
    for event in timeline:
        key = event_identity_key(event)
        if key in seen:
            return Fail(f"Duplicate event: {key}")
        seen.add(key)
    
    return Pass()

def event_identity_key(event):
    if event["event_type"] == "pbp":
        return ("pbp", event.get("play_index"))
    elif event["event_type"] == "tweet":
        return ("tweet", event.get("synthetic_timestamp"), event.get("author"))
    else:
        return ("other", id(event))
```

**Failure:** "Duplicate event: ('pbp', 145)"

---

### C3: Timeline Not Empty

```python
def check_not_empty(timeline):
    """
    Timeline must have at least one event.
    """
    if len(timeline) == 0:
        return Fail("Timeline is empty")
    
    pbp_count = sum(1 for e in timeline if e["event_type"] == "pbp")
    if pbp_count == 0:
        return Fail("Timeline has no PBP events")
    
    return Pass()
```

**Failure:** "Timeline has no PBP events"

---

### C4: Required Phase Boundaries Present

```python
def check_phase_boundaries(timeline):
    """
    Period start/end events must exist for each phase with PBP.
    """
    phases_with_pbp = set()
    phase_starts = set()
    phase_ends = set()
    
    for event in timeline:
        if event["event_type"] != "pbp":
            continue
        
        phase = event.get("phase")
        phases_with_pbp.add(phase)
        
        if is_period_start(event):
            phase_starts.add(phase)
        if is_period_end(event):
            phase_ends.add(phase)
    
    for phase in phases_with_pbp:
        if phase not in phase_starts:
            return Fail(f"Missing period start for {phase}")
        if phase not in phase_ends:
            return Fail(f"Missing period end for {phase}")
    
    return Pass()
```

**Failure:** "Missing period end for q3"

---

### C5: Synthetic Timestamps Monotonic Within Phase

```python
def check_timestamps_monotonic(timeline):
    """
    Within each phase, synthetic timestamps must be non-decreasing.
    """
    by_phase = group_by(timeline, lambda e: e.get("phase"))
    
    for phase, events in by_phase.items():
        timestamps = [parse_timestamp(e["synthetic_timestamp"]) for e in events]
        
        for i in range(1, len(timestamps)):
            if timestamps[i] < timestamps[i-1]:
                return Fail(f"Timestamp regression in {phase}: {timestamps[i-1]} → {timestamps[i]}")
    
    return Pass()
```

**Failure:** "Timestamp regression in q2: 2025-11-24T00:25:00 → 2025-11-24T00:24:30"

---

## Warning Checks

These indicate potential issues. Log but don't block.

### W1: Social Post Isolation

```python
def check_social_isolation(timeline):
    """
    Social posts should not be isolated far from PBP events.
    A tweet with no PBP within 5 minutes (synthetic time) is suspicious.
    """
    warnings = []
    
    for i, event in enumerate(timeline):
        if event["event_type"] != "tweet":
            continue
        
        tweet_time = parse_timestamp(event["synthetic_timestamp"])
        
        # Find nearest PBP
        nearest_pbp_gap = float("inf")
        for other in timeline:
            if other["event_type"] == "pbp":
                gap = abs((parse_timestamp(other["synthetic_timestamp"]) - tweet_time).total_seconds())
                nearest_pbp_gap = min(nearest_pbp_gap, gap)
        
        if nearest_pbp_gap > 300:  # 5 minutes
            warnings.append(f"Isolated tweet at {event['synthetic_timestamp']}: {nearest_pbp_gap}s from nearest PBP")
    
    return Warn(warnings) if warnings else Pass()
```

**Warning:** "Isolated tweet at 2025-11-24T00:48:41: 420s from nearest PBP"

---

### W2: Scoring Play Density

```python
def check_scoring_density(timeline):
    """
    Warn if any phase has unusually low or high scoring density.
    """
    warnings = []
    by_phase = group_by(timeline, lambda e: e.get("phase"))
    
    for phase, events in by_phase.items():
        if phase in ("pregame", "halftime", "postgame"):
            continue
        
        pbp_events = [e for e in events if e["event_type"] == "pbp"]
        scoring = [e for e in pbp_events if is_scoring_play(e)]
        
        if len(pbp_events) > 0:
            ratio = len(scoring) / len(pbp_events)
            
            if ratio < 0.05:
                warnings.append(f"{phase}: Very low scoring ({len(scoring)}/{len(pbp_events)} = {ratio:.1%})")
            elif ratio > 0.4:
                warnings.append(f"{phase}: Very high scoring ({len(scoring)}/{len(pbp_events)} = {ratio:.1%})")
    
    return Warn(warnings) if warnings else Pass()
```

**Warning:** "q2: Very low scoring (2/85 = 2.4%)"

---

### W3: Phase Duration Anomaly

```python
def check_phase_duration(timeline):
    """
    Warn if phase synthetic duration is far from expected.
    """
    warnings = []
    EXPECTED_DURATION = {
        "q1": 720, "q2": 720, "q3": 720, "q4": 720,  # 12 min
        "ot1": 300, "ot2": 300,  # 5 min
    }
    
    by_phase = group_by(timeline, lambda e: e.get("phase"))
    
    for phase, events in by_phase.items():
        if phase not in EXPECTED_DURATION:
            continue
        
        timestamps = [parse_timestamp(e["synthetic_timestamp"]) for e in events]
        if len(timestamps) < 2:
            continue
        
        duration = (max(timestamps) - min(timestamps)).total_seconds()
        expected = EXPECTED_DURATION[phase]
        
        if duration < expected * 0.5:
            warnings.append(f"{phase}: Too short ({duration:.0f}s vs expected {expected}s)")
        elif duration > expected * 2:
            warnings.append(f"{phase}: Too long ({duration:.0f}s vs expected {expected}s)")
    
    return Warn(warnings) if warnings else Pass()
```

**Warning:** "q3: Too short (180s vs expected 720s)"

---

### W4: Tweet Text Missing

```python
def check_tweet_text(timeline):
    """
    Warn if any tweet has null or empty text.
    """
    warnings = []
    
    for event in timeline:
        if event["event_type"] == "tweet":
            text = event.get("text")
            if text is None or text.strip() == "":
                warnings.append(f"Tweet with no text at {event['synthetic_timestamp']} by {event.get('author')}")
    
    return Warn(warnings) if warnings else Pass()
```

**Warning:** "Tweet with no text at 2025-11-24T00:48:41 by Suns"

---

### W5: Compact Mode Overcorrection

```python
def check_compact_retention(full_timeline, compact_timeline):
    """
    Compact mode should retain reasonable percentage of events.
    """
    warnings = []
    
    full_pbp = sum(1 for e in full_timeline if e["event_type"] == "pbp")
    compact_pbp = sum(1 for e in compact_timeline if e["event_type"] == "pbp")
    
    if full_pbp > 0:
        retention = compact_pbp / full_pbp
        
        if retention < 0.1:
            warnings.append(f"Over-compressed: only {retention:.1%} PBP retained")
        elif retention > 0.9:
            warnings.append(f"Under-compressed: {retention:.1%} PBP retained (compact mode ineffective)")
    
    # Social posts should be 100% retained
    full_tweets = sum(1 for e in full_timeline if e["event_type"] == "tweet")
    compact_tweets = sum(1 for e in compact_timeline if e["event_type"] == "tweet")
    
    if compact_tweets < full_tweets:
        warnings.append(f"CRITICAL: Tweets dropped in compact mode ({compact_tweets}/{full_tweets})")
    
    return Warn(warnings) if warnings else Pass()
```

**Warning:** "Over-compressed: only 8% PBP retained"

---

## Diagnostic Checks

Run on demand for deeper inspection.

### D1: Event Distribution Histogram

```python
def diagnostic_distribution(timeline):
    """
    Show event counts by phase and type.
    """
    distribution = {}
    
    for event in timeline:
        phase = event.get("phase", "unknown")
        event_type = event["event_type"]
        key = (phase, event_type)
        distribution[key] = distribution.get(key, 0) + 1
    
    return distribution

# Output:
# {
#   ("q1", "pbp"): 112,
#   ("q1", "tweet"): 0,
#   ("q2", "pbp"): 98,
#   ("q2", "tweet"): 1,
#   ...
# }
```

---

### D2: Social Placement Analysis

```python
def diagnostic_social_placement(timeline):
    """
    For each tweet, show surrounding context.
    """
    results = []
    
    for i, event in enumerate(timeline):
        if event["event_type"] != "tweet":
            continue
        
        prev_pbp = None
        next_pbp = None
        
        # Find previous PBP
        for j in range(i - 1, -1, -1):
            if timeline[j]["event_type"] == "pbp":
                prev_pbp = timeline[j]
                break
        
        # Find next PBP
        for j in range(i + 1, len(timeline)):
            if timeline[j]["event_type"] == "pbp":
                next_pbp = timeline[j]
                break
        
        results.append({
            "tweet": event,
            "prev_pbp": prev_pbp,
            "next_pbp": next_pbp,
            "gap_before": time_gap(prev_pbp, event) if prev_pbp else None,
            "gap_after": time_gap(event, next_pbp) if next_pbp else None,
        })
    
    return results
```

---

### D3: Narrative Gap Detection

```python
def diagnostic_narrative_gaps(timeline):
    """
    Find unusually long gaps in the timeline.
    """
    gaps = []
    
    for i in range(1, len(timeline)):
        prev_time = parse_timestamp(timeline[i-1]["synthetic_timestamp"])
        curr_time = parse_timestamp(timeline[i]["synthetic_timestamp"])
        gap = (curr_time - prev_time).total_seconds()
        
        if gap > 180:  # 3 minutes
            gaps.append({
                "after_event": timeline[i-1],
                "before_event": timeline[i],
                "gap_seconds": gap,
            })
    
    return gaps
```

---

### D4: Phase Transition Smoothness

```python
def diagnostic_phase_transitions(timeline):
    """
    Check that phase transitions are clean.
    """
    transitions = []
    current_phase = None
    
    for event in timeline:
        phase = event.get("phase")
        if phase != current_phase:
            transitions.append({
                "from": current_phase,
                "to": phase,
                "event": event,
            })
            current_phase = phase
    
    # Flag suspicious transitions
    issues = []
    for t in transitions:
        if t["from"] == "q1" and t["to"] != "q2":
            issues.append(f"Unexpected transition: {t['from']} → {t['to']}")
        # ... more rules
    
    return {"transitions": transitions, "issues": issues}
```

---

## Validation Report Format

```json
{
  "game_id": 98948,
  "timeline_version": "v1",
  "generated_at": "2026-01-14T00:32:36Z",
  "validation_run_at": "2026-01-14T02:15:00Z",
  
  "critical": {
    "passed": 5,
    "failed": 0,
    "checks": [
      {"name": "C1_phase_order", "status": "pass"},
      {"name": "C2_no_duplicates", "status": "pass"},
      {"name": "C3_not_empty", "status": "pass"},
      {"name": "C4_phase_boundaries", "status": "pass"},
      {"name": "C5_timestamps_monotonic", "status": "pass"}
    ]
  },
  
  "warnings": {
    "count": 2,
    "checks": [
      {"name": "W4_tweet_text", "status": "warn", "details": ["Tweet with no text at 2025-11-24T00:48:41 by Suns"]},
      {"name": "W1_social_isolation", "status": "pass"}
    ]
  },
  
  "diagnostics": {
    "event_count": 458,
    "pbp_count": 456,
    "tweet_count": 2,
    "phases": ["q1", "q2", "q3", "q4"],
    "narrative_gaps": 0
  },
  
  "verdict": "PASS_WITH_WARNINGS"
}
```

---

## Verdict Levels

| Verdict | Meaning |
|---------|---------|
| `PASS` | All checks green |
| `PASS_WITH_WARNINGS` | Critical passed, warnings logged |
| `FAIL` | One or more critical checks failed |

---

## Integration

### Run on Timeline Generation

```python
async def generate_timeline_artifact(session, game_id, ...):
    # ... generate timeline ...
    
    # Validate before persisting
    report = validate_timeline(timeline)
    
    if report.verdict == "FAIL":
        logger.error("timeline_validation_failed", extra=report.to_dict())
        raise TimelineGenerationError("Validation failed")
    
    if report.verdict == "PASS_WITH_WARNINGS":
        logger.warning("timeline_validation_warnings", extra=report.to_dict())
    
    # Persist timeline
    ...
```

### Expose via Diagnostic Endpoint

```python
@router.get("/games/{game_id}/timeline/validate")
async def validate_game_timeline(game_id: int, ...):
    timeline = await get_timeline(game_id)
    report = validate_timeline(timeline)
    return report
```

---

## Changelog

| Date | Change |
|------|--------|
| 2026-01-14 | Initial validation spec |
