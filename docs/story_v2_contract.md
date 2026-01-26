# Story V2 Contract

## Foundational Axiom

**A story is an ordered list of condensed moments. A condensed moment is a small set of Play-by-Play (PBP) plays with at least one explicitly narrated play.**

All definitions, constraints, and guarantees in this document derive from this statement.

---

## 1. Purpose and Scope

Story V2 produces a readable, condensed replay of a game.

- The output is a sequence of condensed moments
- Each moment is grounded in specific plays
- The sequence preserves game chronology

**This system is not a recap generator.** It does not summarize. It does not abstract. It condenses and narrates concrete events.

---

## 2. Core Unit: Condensed Moment

A **condensed moment** is:

- A small, contiguous set of PBP plays (typically 1–5)
- At least one play in the set is explicitly narrated
- The set represents a discrete, meaningful segment of game action

### What a condensed moment is NOT

| Concept | Why it differs |
|---------|----------------|
| Quarter | A quarter is a time boundary. A condensed moment is a meaning boundary. |
| Section | A section implies hierarchy and headers. A condensed moment has no title. |
| Beat | A beat is a narrative abstraction. A condensed moment is play-backed. |
| Summary paragraph | A summary describes without grounding. A condensed moment narrates specific plays. |

### Why condensed moments are the atomic unit

- **Nothing smaller works.** A single play lacks sufficient context for narrative flow.
- **Nothing larger works.** Aggregating beyond a small set loses traceability. Every sentence must map to plays.

A condensed moment is the smallest unit that supports both narrative coherence and full play traceability.

---

## 3. Required Fields of a Condensed Moment

| Field | Type | Guarantees | Purpose | Failure Mode |
|-------|------|------------|---------|--------------|
| `play_ids` | list of unique identifiers | Non-empty; all IDs exist in source PBP | Defines the plays backing this moment | Without this, narrative is ungrounded |
| `explicitly_narrated_play_ids` | list of unique identifiers | Non-empty; strict subset of `play_ids` | Identifies which plays are directly described | Without this, no guarantee of narrative traceability |
| `start_clock` | game clock value | Valid clock at first play | Anchors moment in game time | Without this, ordering is ambiguous |
| `end_clock` | game clock value | Valid clock at last play | Bounds the moment | Without this, moment boundaries are undefined |
| `period` | integer | Valid period number | Places moment in game structure | Without this, clock values are uninterpretable |
| `score_before` | tuple (home, away) | Score at moment start | Provides context | Without this, score progression is lost |
| `score_after` | tuple (home, away) | Score at moment end | Provides context | Without this, impact is unclear |
| `narrative` | string | Non-empty; describes at least one play from `explicitly_narrated_play_ids` | The readable text | Without this, the moment is data, not story |

No optional fields are defined. Extensions require contract amendment.

---

## 4. Narrative Rules

### Explicit narration requirement

Every condensed moment contains at least one explicitly narrated play. "Explicitly narrated" means:

- The play is directly referenced in the narrative text
- A reader can identify which play is being described
- The narrative sentence makes a claim that the play substantiates

### Traceability requirement

Every narrative sentence must be traceable to one or more plays in `play_ids`. No sentence may make claims unsupported by the backing plays.

### Ordering, not abstraction

Narrative flow emerges from the sequence of condensed moments. The system achieves coherence through:

- Chronological ordering
- Score progression
- Explicit transitions between moments

The system does not achieve coherence through:

- Thematic grouping
- Abstract narrative arcs
- Retrospective commentary

### Implied vs. stated

- **Stated:** Any claim about what happened (who scored, what play occurred)
- **Implied:** Emotional stakes, momentum shifts, significance

Implied content is permitted only when it follows directly from stated facts. Implied content must never contradict or extend beyond the backing plays.

---

## 5. Expansion Contract

**Expansion is a consumption concern, not a generation concern.**

When a consumer expands a condensed moment:

- The full list of `play_ids` is revealed
- Each play's raw PBP data becomes visible
- The relationship between narrative and plays becomes inspectable

### Expansion guarantees

- Expansion shows exactly the plays in `play_ids`
- Expansion shows which plays are in `explicitly_narrated_play_ids`
- Expansion never introduces new narrative claims
- Expansion never reorders plays
- Expansion never adds plays not in `play_ids`

### Expansion does not

- Generate additional text
- Summarize the expanded plays
- Provide commentary beyond the original narrative

---

## 6. Explicit Non-Goals (Hard Exclusions)

The following are **excluded from Story V2 by design**. These are not deferred features. They are incompatible with the system.

- **Headers or section titles.** Stories have no named divisions.
- **Abstract narrative themes.** No "turning points," "momentum swings," or "key stretches" as organizational units.
- **Beat-based prose guidance.** No prescribed narrative structures.
- **Word count targets.** Length is a function of moments, not a parameter.
- **Quarter-based storytelling.** Quarters are metadata, not narrative boundaries.
- **Game flow summaries.** Any summary not backed by specific plays is prohibited.
- **Retrospective narration.** No moment may reference plays that occur after it.
- **Interpretive headlines.** No text exists outside the ordered moment sequence.

An implementation that includes any of the above is non-compliant.

---

## 7. Success Criteria

A Story V2 output is correct if and only if:

### Structural tests

- [ ] The story is a non-empty ordered list of condensed moments
- [ ] Each moment contains all required fields
- [ ] All `play_ids` exist in source PBP data
- [ ] All `explicitly_narrated_play_ids` are subsets of their moment's `play_ids`
- [ ] Moments are ordered by game time (period, then clock)
- [ ] No plays appear in multiple moments

### Narrative tests

- [ ] Each moment's narrative references at least one play from `explicitly_narrated_play_ids`
- [ ] No narrative sentence makes claims unsupported by `play_ids`
- [ ] No narrative references plays outside its moment's `play_ids`
- [ ] No narrative references future events

### Verification questions

A compliant system answers these questions for any output:

1. "Which plays back this sentence?" → Returns specific `play_ids`
2. "What was the score when this moment occurred?" → Returns `score_before` and `score_after`
3. "What plays are in this moment but not explicitly narrated?" → Returns `play_ids` minus `explicitly_narrated_play_ids`
4. "Is this moment grounded in PBP data?" → Always yes

---

## Document Status

This contract is binding. Implementation must conform to these definitions and constraints. Amendments require explicit revision of this document.
