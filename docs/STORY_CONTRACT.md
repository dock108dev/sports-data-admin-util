# Story Contract

## Foundational Axiom

**A story consists of 4-7 narrative blocks. Each block is grounded in one or more moments. Each moment is backed by specific plays.**

This creates a two-level structure:
- **Blocks** — Consumer-facing narratives (4-7 per game, 2-4 sentences each, ~65 words)
- **Moments** — Internal traceability (15-25 per game, linking blocks to plays)

---

## 1. Purpose and Scope

Story produces a readable, condensed replay of a game designed for 60-90 second consumption.

- The output is a sequence of narrative blocks
- Each block has a semantic role (SETUP, MOMENTUM_SHIFT, RESOLUTION, etc.)
- The sequence preserves game chronology
- Total read time: 60-90 seconds (~500 words max)

**This system is not a recap generator.** It does not summarize. It does not abstract. It condenses and narrates concrete events.

---

## 2. Core Units

### Narrative Block (Consumer-Facing)

A **narrative block** is:

- A short narrative (2-4 sentences, ~65 words)
- Assigned a semantic role describing its function
- Grounded in one or more moments
- Part of a 4-7 block sequence

**Semantic Roles:**
| Role | Description |
|------|-------------|
| SETUP | Early context, how game began (always first) |
| MOMENTUM_SHIFT | First meaningful swing |
| RESPONSE | Counter-run, stabilization |
| DECISION_POINT | Sequence that decided outcome |
| RESOLUTION | How game ended (always last) |

**Block Limits:**
- Minimum: 4 blocks per game
- Maximum: 7 blocks per game
- No role appears more than twice

### Moment (Internal Traceability)

A **moment** is:

- A contiguous set of PBP plays (typically 15-50 plays)
- At least one play (up to 5) is explicitly narrated
- A discrete, meaningful segment of game action
- Used for tracing blocks back to specific plays

Moments do not have consumer-facing narratives. They exist for auditability.

---

## 3. Required Fields

### Block Fields

| Field | Type | Purpose |
|-------|------|---------|
| `block_index` | int | Position (0-6) |
| `role` | string | Semantic role |
| `moment_indices` | list[int] | Which moments are grouped |
| `score_before` | [home, away] | Score at block start |
| `score_after` | [home, away] | Score at block end |
| `narrative` | string | 2-4 sentences (~65 words) |
| `embedded_tweet` | object | null | Optional tweet (max 1 per block) |

### Moment Fields (Traceability)

| Field | Type | Purpose |
|-------|------|---------|
| `play_ids` | list[int] | Backing plays |
| `explicitly_narrated_play_ids` | list[int] | Key plays (1-5) |
| `period` | int | Game period |
| `start_clock` | string | Clock at first play |
| `end_clock` | string | Clock at last play |
| `score_before` | [home, away] | Score at moment start |
| `score_after` | [home, away] | Score at moment end |

---

## 4. Narrative Rules

### Block Narratives

Each block narrative:
- Is 2-4 sentences, approximately 65 words
- Describes a stretch of play with cause-and-effect connections
- References key plays from its underlying moments
- Is role-aware (SETUP blocks set context, RESOLUTION blocks conclude)
- Uses SportsCenter-style broadcast prose

### Forbidden Language

Narratives must not contain:
- "momentum", "turning point", "shift"
- "crucial", "pivotal", "key moment"
- "dominant", "clutch", "huge", "massive"
- Retrospective commentary ("would later prove...")
- Speculation ("appeared to", "seemed to")

### Traceability

Every narrative claim is traceable:
1. Block → Moments (via `moment_indices`)
2. Moment → Plays (via `play_ids`)
3. Play → Source data (via PBP records)

---

## 5. Embedded Tweets (Phase 4)

Blocks may contain embedded tweets that add social context.

**Constraints:**
- Maximum 5 embedded tweets per game
- Maximum 1 embedded tweet per block
- Tweets are optional — removing all tweets produces the same story structure
- Tweets do not influence narrative content

**Selection Criteria:**
- In-game tweets preferred over pregame/postgame
- High engagement and media content preferred
- Distributed across blocks (early, mid, late)

---

## 6. Guardrail Invariants (Non-Negotiable)

| Invariant | Limit | Enforcement |
|-----------|-------|-------------|
| Block count | 4-7 | Pipeline fails on violation |
| Embedded tweets | ≤ 5 per game | Hard cap enforced |
| Tweet per block | ≤ 1 | Hard cap enforced |
| Total words | ≤ 500 | Warning, not failure |
| Words per block | 30-100 | Warning, not failure |
| Sentences per block | 2-4 | Warning, not failure |
| Read time | 60-90 seconds | Implicit via word limits |

Violations are logged at ERROR level with full context.

---

## 7. Social Independence

**Zero required social dependencies.** The story structure must be identical with or without social data.

Validation checks:
- Block count is identical with/without social
- Block narratives are identical with/without social
- Semantic roles are identical with/without social

Social content (embedded tweets) is additive, never structural.

---

## 8. Success Criteria

A Story output is correct if and only if:

### Structural Tests

- [ ] The story contains 4-7 blocks
- [ ] Each block has a semantic role
- [ ] First block is SETUP, last block is RESOLUTION
- [ ] No role appears more than twice
- [ ] Score continuity across block boundaries

### Narrative Tests

- [ ] Each narrative is 30-100 words
- [ ] Each narrative has 2-4 sentences
- [ ] Total word count ≤ 500
- [ ] No forbidden phrases
- [ ] No retrospective commentary
- [ ] No raw PBP artifacts (initials, score artifacts)

### Traceability Tests

- [ ] Each block maps to moments via `moment_indices`
- [ ] Each moment maps to plays via `play_ids`
- [ ] All play references exist in source PBP

### Social Independence Tests

- [ ] Removing embedded tweets changes nothing but tweet fields
- [ ] Block count, roles, and narratives are social-independent

---

## 9. Verification Questions

A compliant system answers these questions for any output:

1. "How many blocks?" → 4-7
2. "What role is block N?" → One of the semantic roles
3. "Which plays back this block?" → Via moments → plays
4. "Total read time?" → 60-90 seconds
5. "Does this work without social?" → Yes, identical structure

---

## Document Status

This contract is binding. Implementation must conform to these definitions and constraints. Amendments require explicit revision of this document.
