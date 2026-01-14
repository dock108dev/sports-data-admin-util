# Narrative Time Model (Contract)

## Purpose
The system **does not** treat timestamps as ground truth. Narrative time is the canonical ordering model for the game timeline; wall-clock time is secondary and approximate.

## Canonical Time Definition
- **Narrative time (primary):** The ordered, story-driven sequence of events presented to users. Narrative time is the only source of truth for ordering within a timeline.
- **Wall-clock time (secondary):** Real-world timestamps (e.g., post timestamps, feed times) used only as hints when narrative ordering is ambiguous or when narrative time is absent.

## Narrative Phases
Narrative time is segmented into ordered phases:
1. **Pregame**
2. **Early game**
3. **Mid game**
4. **Late game**
5. **Postgame**

## Phase Assignment Rules
Events are assigned to phases using the following precedence:
1. **Game clock / period context** (if available) determines the phase.
2. **Explicit event metadata** (e.g., “halftime,” “final,” “postgame”) determines the phase.
3. **Wall-clock time relative to game start/end** provides a fallback approximation.
4. **Unknown context** defaults to the earliest reasonable phase, and is flagged for review if possible.

## Ordering Guarantees
- **Across phases:** Phases are strictly ordered: pregame → early → mid → late → postgame. No event may be ordered into an earlier phase once assigned to a later phase.
- **Within a phase:** Narrative ordering is primary. Wall-clock time may be used to break ties, but must not reorder events that have a defined narrative sequence (e.g., play-by-play order).
- **Mixed sources:** When merging sources (e.g., play-by-play, social), narrative phase and within-phase narrative order take precedence over timestamp order.

## Contract Summary
“Time” in this system means **narrative time**: a deterministic, phase-based ordering of events designed for coherent storytelling. Wall-clock timestamps are **supporting signals only** and must never override narrative ordering.
