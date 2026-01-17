# Moment System Contract

> **This document is a contract.** Do not modify the moment system without reading this first.
> If you're tempted to "improve" something here, stop and ask: does this violate the contract?

---

## What Is a Moment?

A **Moment** is a contiguous segment of plays forming a narrative unit.

- Every play belongs to exactly **one** moment
- Moments are chronologically ordered by `start_play`
- Moments never overlap
- Moments never have gaps

A moment exists because **something meaningful changed**. If nothing changed, extend the current moment.

---

## The Lead Ladder (How Moments Are Created)

Moments are created by the **Lead Ladder**, not by runs or scoring.

The Lead Ladder defines meaningful lead separation tiers for each sport:

| Sport | Thresholds |
|-------|------------|
| NBA   | 3, 6, 10, 16 |
| NHL   | 1, 2, 3 |
| NFL   | 3, 7, 14, 21 |
| MLB   | 1, 2, 4 |

A moment boundary is created when:
1. **Tier crossing** - Lead moves to a new tier (LEAD_BUILD or CUT)
2. **Flip** - Lead changes hands (FLIP)
3. **Tie** - Game returns to even (TIE)
4. **High impact** - Ejection, injury, technical (HIGH_IMPACT)
5. **Closing lock** - Late-game control established (CLOSING_CONTROL)

Runs do NOT create moments. A 10-0 run that doesn't cross a tier threshold is just metadata on an existing moment.

---

## Moment Types

| Type | Meaning | When Created |
|------|---------|--------------|
| LEAD_BUILD | Lead tier increased | Tier went up |
| CUT | Lead tier decreased | Tier went down (comeback) |
| TIE | Game returned to even | Score became equal |
| FLIP | Leader changed | Control shifted teams |
| CLOSING_CONTROL | Late-game lock-in | Q4 <5min, lead stabilized |
| HIGH_IMPACT | Dramatic non-scoring event | Ejection, injury, technical |
| NEUTRAL | Normal flow | Default when no boundary |

---

## Hard Limits (Non-Negotiable)

### Budget

| Sport | Max Moments |
|-------|-------------|
| NBA   | 30 |
| NCAAB | 32 |
| NFL   | 22 |
| NHL   | 28 |
| MLB   | 26 |

If a game exceeds budget, moments are **merged** until under budget. No exceptions.

### Per-Quarter Limit

**Maximum 7 moments per quarter/period.** Prevents "chaotic quarter" bloat.

### Merge Priority

When merging is needed:
1. Consecutive NEUTRAL moments (always merge)
2. Consecutive LEAD_BUILD moments
3. Consecutive CUT moments
4. Any consecutive same-type moments (hard clamp)
5. Any consecutive moments (nuclear option)

**Protected types** (prefer not to merge): FLIP, TIE, CLOSING_CONTROL, HIGH_IMPACT

---

## AI's Role (Narrative Renderer)

OpenAI is a **narrative renderer**, not a decision engine.

### AI Does:
- Write headlines (max 60 chars)
- Write summaries (max 150 chars)
- Add energy, momentum, pressure language
- Capture the SportsCenter-style voice

### AI Does NOT:
- Decide moment boundaries (Lead Ladder does that)
- Decide importance (MomentType does that)
- Decide ordering (chronology does that)
- Know the final outcome (spoiler-safe)

### AI Call Shape

**One call per game.** All moments enriched in a single batch.

Input:
```json
{
  "game": { "home_team": "...", "away_team": "...", "final_score": "..." },
  "moments": [
    { "id": "m_001", "type": "LEAD_BUILD", "score_swing": "0-0 → 5-0", ... }
  ]
}
```

Output:
```json
{
  "game_headline": "...",
  "game_subhead": "...",
  "moments": [
    { "id": "m_001", "headline": "...", "summary": "..." }
  ]
}
```

### Fail Loud

If AI fails → the build fails. No silent fallbacks. No templates.

---

## Validation

### Forbidden Words (Spoilers)

These words in AI output cause **validation failure**:
- wins, won, winner, winning
- loses, lost, loser, losing
- sealed, clinched, secured
- dagger, decisive, decided
- victory, victorious, defeat, defeated
- champion, championship
- eliminated
- proved to be, turned out to be
- would go on to, went on to
- in the end, ultimately
- game over, it's over
- seals the deal, puts it away

### Content Linting (Warnings)

These patterns are logged as warnings:
- Verbatim score restating (e.g., "107-102")
- Future knowledge hallucinations ("would later", "eventually")
- Short headlines (<10 chars) or summaries (<20 chars)

---

## Display Hints

Every moment includes display hints so frontend doesn't guess:

| Field | Values | Purpose |
|-------|--------|---------|
| `display_weight` | high, medium, low | How prominent to render |
| `display_icon` | swap, equals, trending-up, etc. | Icon suggestion |
| `display_color_hint` | tension, positive, neutral, highlight | Color intent |

---

## What NOT to Do

1. **Don't create new grouping abstractions.** Moments are the only unit.
2. **Don't let runs create moments.** Runs are metadata, not boundaries.
3. **Don't add AI "thinking" to structure.** AI renders, it doesn't decide.
4. **Don't add legacy fallback paths.** Fail loud or don't ship.
5. **Don't exceed budgets.** The clamp is mandatory.
6. **Don't change thresholds casually.** They define the product feel.

---

## Definition of Done

You are done when:

- [ ] A typical NBA game produces 25–35 moments
- [ ] No quarter produces more than 7 moments
- [ ] No run creates a moment unless it changes control tier
- [ ] No legacy fallback paths exist anywhere
- [ ] AI output is schema-validated and content-linted
- [ ] Frontend renders moments without special-casing
- [ ] You can explain the system in 5 minutes without diagrams

---

## Files That Implement This

| File | Responsibility |
|------|----------------|
| `api/app/services/moments.py` | Lead Ladder, partitioning, merging, budgets |
| `api/app/services/game_analysis.py` | Orchestrates partition + AI enrichment |
| `api/app/services/ai_client.py` | OpenAI batch call, validation, linting |
| `api/app/routers/sports/games.py` | Moments API endpoint |

---

## Last Updated

2026-01-17 — Finalized after moment system refactor.

**Do not update this document without updating the implementation to match.**
