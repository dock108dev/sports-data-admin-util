# Game Flow Components - Phase 5 UI Rendering Rules

This directory contains components for rendering the game flow UI according to the Phase 5 contract.

## Core Principle

**The collapsed view is the primary product.** Social content is optional.

## Component Architecture

### CollapsedGameFlow

The primary, self-sufficient game story view.

**May contain ONLY:**
- Narrative blocks (from Phase 1)
- Embedded tweets (from Phase 4 - max 5 per game, max 1 per block)

**Must NOT contain:**
- Pregame tweets (bulk)
- Postgame tweets (bulk)
- Social lists or grids
- Hidden expandable sections

**Rendering rules:**
- Narrative blocks define vertical rhythm
- Embedded tweets are interleaved between blocks
- Tweets are visually secondary to narrative
- Removing all tweets produces the SAME layout

### ExpandableSocialSections

Optional social context through explicit user action.

**Structure:**
- Pregame card (collapsed by default)
- In-game sections per quarter/half/period (collapsed by default)
- Postgame card (collapsed by default)

**Rules:**
- NEVER reorders narrative blocks
- NEVER inserts content into collapsed flow
- Visually distinct and clearly secondary
- No implicit expansion
- No auto-scrolling

### GameFlowView

Combines CollapsedGameFlow and ExpandableSocialSections with clear visual hierarchy.

## Legacy Affordances - PROHIBITED

**Do NOT add:**

1. **"Related plays" language**
   - Tweets do not relate to plays
   - Tweets do not explain plays
   - Tweets are reaction, not evidence

2. **Tweet count badges on moments/blocks**
   - No "3 tweets" badge on a moment
   - No "5 reactions" indicator on a block
   - Social counts only in dedicated social sections

3. **Cause-and-effect styling**
   - No arrows from tweets to plays
   - No "explained by" labels
   - No "supported by" indicators
   - No linking icons between tweets and narrative

4. **Implied verification**
   - No checkmarks suggesting tweet validates play
   - No "confirmed" styling
   - No "verified by social" indicators

## Visual Hierarchy

```
┌─────────────────────────────────────────┐
│  COLLAPSED GAME FLOW (PRIMARY)          │
│  ┌─────────────────────────────────────┐│
│  │ Block 1: SETUP                      ││
│  │ Narrative text...                   ││
│  │   [optional embedded tweet]         ││
│  └─────────────────────────────────────┘│
│  ┌─────────────────────────────────────┐│
│  │ Block 2: MOMENTUM_SHIFT             ││
│  │ Narrative text...                   ││
│  └─────────────────────────────────────┘│
│  ...more blocks...                      │
└─────────────────────────────────────────┘

- - - - - - - - - - - - - - - - - - - - -

┌─────────────────────────────────────────┐
│  SOCIAL CONTEXT (SECONDARY/OPTIONAL)    │
│  ▶ Pregame (5)                          │
│  ▶ Q1 (3)                               │
│  ▶ Q2 (2)                               │
│  ▶ Halftime (1)                         │
│  ▶ Q3 (4)                               │
│  ▶ Q4 (6)                               │
│  ▶ Postgame (8)                         │
└─────────────────────────────────────────┘
```

## Testing Checklist

- [ ] Collapsed view is readable without any interaction
- [ ] Total read time is 60-90 seconds
- [ ] Removing all tweets produces identical narrative layout
- [ ] Social sections are collapsed by default
- [ ] No UI element suggests tweets explain plays
- [ ] Visual hierarchy favors narrative over social
