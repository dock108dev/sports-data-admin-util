# Social Event Roles

> **Status:** Canonical  
> **Parent Contract:** [NARRATIVE_TIME_MODEL.md](./NARRATIVE_TIME_MODEL.md)  
> **Last Updated:** 2026-01-14

---

## Purpose

Social posts are not random noise. Each post serves a **narrative role** — a reason it belongs in the timeline. This document defines the role taxonomy and assignment rules.

---

## Role Taxonomy

| Role | Code | Intent | Example |
|------|------|--------|---------|
| **Hype** | `hype` | Build anticipation before the game | "Game day! Let's get this W 🔥" |
| **Context** | `context` | Provide information (lineups, injuries, stakes) | "Booker is questionable tonight with ankle soreness" |
| **Reaction** | `reaction` | Respond to in-game action | "WHAT A DUNK!" |
| **Momentum** | `momentum` | Mark a shift in game flow | "We're on a 12-0 run 💪" |
| **Milestone** | `milestone` | Celebrate a notable achievement | "Luka's 10th triple-double of the season!" |
| **Highlight** | `highlight` | Share a video clip or replay | [Video] "Watch this block again 👀" |
| **Commentary** | `commentary` | General observation about the game | "This defense is suffocating tonight" |
| **Result** | `result` | Announce or react to final outcome | "Final: Rockets 114, Suns 92" |
| **Reflection** | `reflection` | Postgame analysis or takeaway | "Tough loss. Back at it Wednesday." |
| **Ambient** | `ambient` | Atmosphere, crowd, arena content | "The arena is LOUD tonight 🗣️" |

---

## Role Assignment

### Primary Signal: Time Window

```
posted_at relative to game:

  ─────────────────────────────────────────────────────────────────►
  │         │                                    │                 │
  -2h     start                                 end              +2h
  │         │                                    │                 │
  └─pregame─┴──────────── in-game ───────────────┴──── postgame ───┘
```

| Window | Default Role | Rationale |
|--------|--------------|-----------|
| `posted_at < game_start` | `hype` or `context` | Building anticipation |
| `game_start <= posted_at <= game_end` | `reaction` | Responding to action |
| `posted_at > game_end` | `result` or `reflection` | Processing outcome |

### Secondary Signal: Content Heuristics

Time window sets the default. Content can **refine** the role:

```python
def refine_role(post, default_role):
    text = post.text.lower() if post.text else ""
    
    # Pregame refinements
    if default_role in ("hype", "context"):
        if contains_lineup_info(text):
            return "context"
        if contains_injury_mention(text):
            return "context"
        return "hype"
    
    # In-game refinements
    if default_role == "reaction":
        if contains_score_update(text):
            return "momentum"
        if contains_stat_milestone(text):
            return "milestone"
        if has_video_attachment(post):
            return "highlight"
        if is_short_exclamation(text):  # "BANG!" "LET'S GO!"
            return "reaction"
        return "commentary"
    
    # Postgame refinements
    if default_role in ("result", "reflection"):
        if contains_final_score(text):
            return "result"
        return "reflection"
    
    return default_role
```

### Content Heuristic Patterns

| Pattern | Detected Role |
|---------|---------------|
| "starting lineup", "injury report", "out tonight" | `context` |
| "game day", "let's go", "tip-off" | `hype` |
| Score format (e.g., "45-38", "up by 10") | `momentum` |
| "triple-double", "career-high", "Nth of the season" | `milestone` |
| Video/media attachment | `highlight` |
| < 20 chars, ends with emoji/exclamation | `reaction` |
| "final", "W", "L", final score | `result` |
| "on to the next", "tough loss", "great win" | `reflection` |
| "crowd", "arena", "atmosphere" | `ambient` |

---

## Role-to-Phase Mapping

Roles have **affinity** to phases but are not strictly bound:

| Role | Primary Phase | Can Appear In |
|------|---------------|---------------|
| `hype` | pregame | pregame only |
| `context` | pregame | pregame, q1 |
| `reaction` | q1-q4, ot | any in-game phase |
| `momentum` | q1-q4, ot | any in-game phase |
| `milestone` | q1-q4, ot | any in-game phase, postgame |
| `highlight` | q1-q4, ot, postgame | any phase |
| `commentary` | q1-q4, ot | any in-game phase |
| `result` | postgame | q4 (late), postgame |
| `reflection` | postgame | postgame only |
| `ambient` | any | any |

---

## Handling Ambiguity

### Case 1: Post at Phase Boundary

A tweet posted at exactly game start time:

```python
if abs(posted_at - game_start) < timedelta(minutes=2):
    # Could be last-second hype or first reaction
    if has_pregame_signals(text):
        role = "hype"
        phase = "pregame"
    else:
        role = "reaction"
        phase = "q1"
```

**Rule:** Content signals break ties. When content is ambiguous, prefer the later phase (in-game over pregame).

### Case 2: Post With No Text

```python
if post.text is None or post.text.strip() == "":
    if has_video_attachment(post):
        role = "highlight"
    elif has_image_attachment(post):
        role = "ambient"
    else:
        role = "ambient"  # Unknown intent, neutral role
```

**Rule:** Media type determines role for text-less posts. Default to `ambient` if unknown.

### Case 3: Delayed Reaction

A tweet posted 5 minutes after game end but clearly about a play:

```
"That Booker fadeaway in the 4th was INSANE 🔥"
posted_at: game_end + 5 minutes
```

```python
if is_clearly_about_in_game_action(text):
    role = "highlight"  # Not "reflection"
    phase = "postgame"  # But phase is still postgame
```

**Rule:** Role reflects intent. Phase reflects time. A highlight clip posted postgame is role=`highlight`, phase=`postgame`.

### Case 4: Score-Revealing Content

Posts that reveal the final score must be handled for spoiler-free experiences:

```python
if contains_final_score(text) or role == "result":
    post.reveal_risk = True
```

**Rule:** `result` role always implies reveal risk. Other roles may also have reveal risk based on content.

---

## Schema Extension

Add `role` field to social events in the timeline:

```json
{
  "event_type": "tweet",
  "role": "reaction",
  "author": "Suns",
  "handle": "Suns",
  "text": "Sidestep. Swish.",
  "synthetic_timestamp": "2025-11-24T01:18:52+00:00",
  "phase": "q3"
}
```

---

## Downstream Usage

### For App Rendering

```swift
switch event.role {
case "highlight":
    // Show video player, larger card
case "reaction":
    // Compact inline display
case "result":
    // Check reveal settings before showing
case "hype":
    // Show in pregame section with energy styling
default:
    // Standard tweet card
}
```

### For AI Summarization

```
Given a timeline with roles, summarize the game:
- Use "hype" posts to establish pregame mood
- Use "momentum" posts to identify turning points
- Use "milestone" posts for notable achievements
- Use "result" and "reflection" for conclusion
```

### For Filtering

```python
# Spoiler-free mode: hide result and some highlights
visible_roles = {"hype", "context", "reaction", "momentum", "ambient"}

# Highlights-only mode
visible_roles = {"highlight", "milestone"}
```

---

## Role Assignment Priority

When multiple signals conflict:

1. **Explicit metadata** (if post is tagged by source) — highest
2. **Media type** (video → highlight)
3. **Content patterns** (regex/keyword matches)
4. **Time window** (phase-based default) — lowest

---

## Changelog

| Date | Change |
|------|--------|
| 2026-01-14 | Initial role taxonomy defined |
