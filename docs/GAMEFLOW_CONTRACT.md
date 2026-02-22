# Game Flow Contract

## Foundational Axiom

**A game flow consists of 3-7 narrative blocks. Each block is grounded in one or more moments. Each moment is backed by specific plays.**

This creates a two-level structure:
- **Blocks** — Consumer-facing narratives (3-7 per game, 1-5 sentences each, ~65 words)
- **Moments** — Internal traceability (15-25 per game, linking blocks to plays)

---

## 1. Purpose and Scope

Game Flow produces a readable, condensed replay of a game designed for 60-90 second consumption.

- The output is a sequence of narrative blocks
- Each block has a semantic role (SETUP, MOMENTUM_SHIFT, RESOLUTION, etc.)
- The sequence preserves game chronology
- Total read time: 60-90 seconds (~600 words max)

**This system narrates consequences, not transactions.** It condenses game action into reporter-style prose, collapsing sequences into runs and describing effects rather than enumerating individual plays.

---

## 2. Core Units

### Narrative Block (Consumer-Facing)

A **narrative block** is:

- A short narrative (1-5 sentences, ~65 words)
- Assigned a semantic role describing its function
- Grounded in one or more moments
- Part of a 3-7 block sequence

**Semantic Roles:**
| Role | Description |
|------|-------------|
| SETUP | Early context, how game began (always first) |
| MOMENTUM_SHIFT | First meaningful swing |
| RESPONSE | Counter-run, stabilization |
| DECISION_POINT | Sequence that decided outcome |
| RESOLUTION | How game ended (always last) |

**Block Limits:**
- Minimum: 3 blocks per game (blowouts)
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
| `score_before` | [away, home] | Score at block start |
| `score_after` | [away, home] | Score at block end |
| `narrative` | string | 1-5 sentences (~65 words) |
| `embedded_social_post_id` | int | null | Optional social post ID (max 1 per block) |
| `peak_margin` | int (optional) | Largest absolute margin within this block (0 if omitted) |
| `peak_leader` | int (optional) | Who led at peak: 1=home, -1=away, 0=tied (0 if omitted) |

### Moment Fields (Traceability)

| Field | Type | Purpose |
|-------|------|---------|
| `play_ids` | list[int] | Backing plays |
| `explicitly_narrated_play_ids` | list[int] | Key plays (1-5) |
| `period` | int | Game period |
| `start_clock` | string | Clock at first play |
| `end_clock` | string | Clock at last play |
| `score_before` | [away, home] | Score at moment start |
| `score_after` | [away, home] | Score at moment end |

---

## 4. Narrative Rules

### Block Narratives

Each block narrative:
- Is 1-5 sentences, approximately 65 words
- Describes a stretch of play with consequence-based narration
- Key plays provide context; referencing them is editorial judgment, not mandatory
- Is role-aware (SETUP blocks set context, RESOLUTION blocks conclude)
- Uses SportsCenter-style broadcast prose
- Collapses consecutive scoring into runs where appropriate

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

## 5. Embedded Social Posts

Blocks may contain an embedded social post ID that adds social context.

**Constraints:**
- Maximum 5 embedded social posts per game
- Maximum 1 embedded social post per block
- Social posts are optional -- removing all social posts produces the same game flow structure
- Social posts do not influence narrative content

**Backfill:** When the pipeline runs before social scraping completes, all blocks may have `embedded_social_post_id = NULL`. A post-generation backfill attaches tweet references once social data becomes available. This is the sole permitted mutation to a finalized game flow — block structure, roles, and narratives are never altered.

**Selection Criteria:**
- In-game posts preferred over pregame/postgame
- High engagement and media content preferred
- Assigned to blocks by temporal matching (tweet `posted_at` matched to block time windows)

---

## 6. Guardrail Invariants (Non-Negotiable)

| Invariant | Limit | Enforcement |
|-----------|-------|-------------|
| Block count | 3-7 | Pipeline fails on violation |
| Embedded social posts | ≤ 5 per game | Hard cap enforced |
| Social post per block | ≤ 1 | Hard cap enforced |
| Total words | ≤ 600 | Warning, not failure |
| Words per block | 30-120 | Warning, not failure |
| Sentences per block | 1-5 | Warning, not failure |
| Read time | 60-90 seconds | Implicit via word limits |

Violations are logged at ERROR level with full context.

---

## 7. Social Independence

**Zero required social dependencies.** The game flow structure must be identical with or without social data.

Validation checks:
- Block count is identical with/without social
- Block narratives are identical with/without social
- Semantic roles are identical with/without social

Social content (embedded social posts) is additive, never structural.

---

## 8. Success Criteria

A Game Flow output is correct if and only if:

### Structural Tests

- [ ] The game flow contains 3-7 blocks
- [ ] Each block has a semantic role
- [ ] First block is SETUP, last block is RESOLUTION
- [ ] No role appears more than twice
- [ ] Score continuity across block boundaries

### Narrative Tests

- [ ] Each narrative is 30-120 words
- [ ] Each narrative has 1-5 sentences
- [ ] Total word count ≤ 600
- [ ] No forbidden phrases
- [ ] No retrospective commentary
- [ ] No raw PBP artifacts (initials, score artifacts)

### Traceability Tests

- [ ] Each block maps to moments via `moment_indices`
- [ ] Each moment maps to plays via `play_ids`
- [ ] All play references exist in source PBP

### Social Independence Tests

- [ ] Removing embedded social posts changes nothing but social post fields
- [ ] Block count, roles, and narratives are social-independent

---

## 9. Verification Questions

A compliant system answers these questions for any output:

1. "How many blocks?" → 3-7
2. "What role is block N?" → One of the semantic roles
3. "Which plays back this block?" → Via moments → plays
4. "Total read time?" → 60-90 seconds
5. "Does this work without social?" → Yes, identical structure

---

## Document Status

This contract is binding. Implementation must conform to these definitions and constraints. Amendments require explicit revision of this document.
