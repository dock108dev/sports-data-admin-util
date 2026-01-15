# Summary Generation

> **Status:** Canonical  
> **Parent Contract:** [TIMELINE_ASSEMBLY.md](./TIMELINE_ASSEMBLY.md)  
> **Last Updated:** 2026-01-14

---

## Core Principle

> **The summary is a reading guide, not a recap.**

The summary helps users understand what kind of game they're about to scroll through. It sets expectations, points out where attention should increase, and explains how the story unfolds — without replacing the timeline.

---

## The Summary's Job

### What It Does
- Sets expectations for what kind of game this was
- Points out where attention should increase while scrolling
- Explains how the story unfolds as the timeline progresses

### What It Doesn't Do
- Summarize the game objectively
- List events chronologically
- Repeat detailed play descriptions
- Replace the timeline experience

---

## Output Schema

```json
{
  "overview": "1-2 paragraph reading guide",
  "attention_points": [
    "The first few minutes set the early tempo",
    "A stretch in the second or third where the gap starts to open",
    "A decisive run that effectively ends it",
    "In-game reactions mark the moments that landed"
  ],
  "flow": "blowout",
  "phases_in_timeline": ["q1", "q2", "q3", "q4", "postgame"],
  "social_counts": {"total": 10, "by_phase": {"q4": 1, "postgame": 9}}
}
```

### `overview`
1-2 paragraphs that set the tone. Should feel like a friend telling you what to expect.

**Good examples:**
- "This one gets away early. Houston takes control and never really lets go."
- "Back and forth for most of it, with stretches where either team could take over."
- "Tight throughout. The kind of game where every possession in the fourth matters."

**Bad examples:**
- "Durant led with 32 points..." (box score framing)
- "The game started with a tip-off..." (chronological rehash)
- "An exciting game between two teams." (generic filler)

### `attention_points`
Array of strings highlighting where to focus while scrolling.

**Good patterns:**
- "The first few minutes set the early tempo"
- "There's a stretch in the third where momentum clearly shifts"
- "The final minutes are where everything tightens"
- "Reactions pick up as it winds down"

**Bad patterns:**
- "Durant scores 28 points" (stat dump)
- "At 8:42 in Q2, Curry hits a three" (too specific)
- "The game was exciting" (meaningless)

---

## Flow Classification

The `flow` field describes the game shape:

| Flow | Margin | Tone |
|------|--------|------|
| `close` | ≤5 points | Every possession matters |
| `competitive` | 6-12 points | Back and forth with swings |
| `comfortable` | 13-20 points | Winner in control but not dominant |
| `blowout` | >20 points | One team runs away with it |

---

## Social Reactions as Atmosphere

Treat social posts as atmosphere indicators, not evidence.

### ✅ Good
- "Reactions pick up as it winds down"
- "You'll feel when the energy shifts"
- "In-game reactions mark the moments that landed"
- "Postgame reactions capture the aftermath"

### ❌ Bad
- "The @Suns tweet said 'LUKA MAGIC'" (quoting)
- "There were 9 postgame tweets" (enumerating)
- "The team posted about the dunk" (too specific)

---

## Reading Guide Patterns

### By Flow Type

**Blowout:**
```
"This one gets away early. [Winner] takes control and never really lets go. 
Watch for the runs — there are stretches where momentum clearly swings."
```

**Comfortable:**
```
"A game that looks closer on paper than it felt. [Winner] stays in command 
through the middle quarters."
```

**Competitive:**
```
"Back and forth for most of it, with stretches where either team could take over."
```

**Close:**
```
"Tight throughout. The kind of game where every possession in the fourth 
starts to matter."
```

**Overtime:**
```
"This one needs extra time. The tension builds steadily, especially in the 
final minutes of regulation."
```

---

## Attention Points by Game Type

| Game Type | Attention Points |
|-----------|------------------|
| Blowout | Opening tempo, gap-opening run, decisive stretch |
| Competitive | Mid-game swings, control changes, fourth quarter |
| Close | Every phase matters, final minutes are key |
| Overtime | Regulation final minutes, OT intensity |

### Social-Driven Points

| Social Pattern | Attention Point |
|----------------|-----------------|
| In-game tweets | "In-game reactions mark the moments that landed" |
| Heavy postgame | "Postgame reactions capture the aftermath" |
| Pregame buzz | "Pre-game buzz sets the tone before things get going" |

---

## Anti-Patterns

### ❌ Box Score Framing
```
"Durant scored 32 points on 11-18 shooting with 7 rebounds and 5 assists."
```
**Problem:** Reader didn't see these stats. Not a reading guide.

### ❌ Chronological Rehash
```
"In Q1, Team A scored, then Team B scored, then Team A scored again..."
```
**Problem:** Just repeats timeline without synthesis.

### ❌ Generic Filler
```
"It was an exciting game with many great plays from both teams."
```
**Problem:** Says nothing. Could describe any game.

### ❌ Neutral Sportswriting
```
"The Houston Rockets defeated the Phoenix Suns 114-92 on Sunday night."
```
**Problem:** Wikipedia tone. Not a reading guide.

---

## The Summary Should Feel Incomplete

This is intentional. The summary's purpose is to **guide how the timeline is read**, not replace it.

A good summary makes you want to scroll the timeline.
A bad summary makes the timeline feel redundant.

---

## Example: Game 98948

### Input
- Flow: blowout (22-point margin)
- Social: 1 in-game reaction, 9 postgame
- Highlights: Multiple scoring runs

### Output

```json
{
  "overview": "This one gets away early. Houston Rockets takes control and never really lets go. Watch for the runs — there are stretches where momentum clearly swings. Reactions pick up as it winds down — you'll feel when the energy shifts.",
  "attention_points": [
    "The first few minutes set the early tempo",
    "A stretch in the second or third where the gap starts to open",
    "A decisive run that effectively ends it",
    "In-game reactions mark the moments that landed",
    "Postgame reactions capture the aftermath"
  ]
}
```

### Why It Works
- ✅ Sets expectation ("gets away early")
- ✅ Points to momentum shifts ("watch for the runs")
- ✅ References social atmosphere ("reactions pick up")
- ✅ Feels incomplete without timeline
- ✅ No stats, no box score framing
- ✅ Could only describe THIS game's shape

---

## Changelog

| Date | Change |
|------|--------|
| 2026-01-14 | Rewrite: Summary is now a "reading guide" with overview + attention_points |
| 2026-01-14 | Initial summary generation spec |
