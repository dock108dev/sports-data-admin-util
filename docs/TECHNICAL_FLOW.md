# Technical Flow: PBP to Compact Timeline

> **Audience:** Developers working on the sports data pipeline  
> **Last Updated:** 2026-01-14

---

## AI Usage Principle

> **OpenAI is used only for interpretation and narration — never for ordering, filtering, or correctness.**

Code decides what happened. AI explains why it mattered.

---

## Where OpenAI Is Used

| Area | Purpose | Determinism |
|------|---------|-------------|
| Social Role Classification | Improve role accuracy beyond heuristics | Cached, bounded |
| Game Analysis Enrichment | Label segments more naturally | Cached, derived |
| Summary Generation | Produce the "reading guide" text | Cached, final |

**Everything else remains pure code.** The core timeline assembly (phase assignment, ordering, merging) is 100% deterministic.

---

## Overview

This document traces a game's journey from raw play-by-play data through to the final compact timeline and summary served to clients.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           INGESTION PHASE                                    │
│                                                                             │
│  [Sports Reference]  ──scrape──▶  [Scraper]  ──persist──▶  [PostgreSQL]    │
│                                                                             │
│  Raw HTML ────────────────────▶ NormalizedPlay ─────────▶ SportsGamePlay   │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           GENERATION PHASE                                   │
│                                                                             │
│  [SportsGamePlay]  ──build_pbp_events──▶  [PBP Events with Phases]         │
│  [GameSocialPost]  ──build_social_events──▶ [Social Events with Roles]     │
│                            │                                                │
│                            ▼                                                │
│  [Merged Timeline]  ◀──merge_timeline_events──                              │
│        │                                                                    │
│        ├──▶ [Game Analysis: Segments + Highlights]                          │
│        │                                                                    │
│        └──▶ [Summary: Reading Guide]                                        │
│                            │                                                │
│                            ▼                                                │
│  [SportsGameTimelineArtifact] ──persist──▶ [PostgreSQL]                     │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           SERVING PHASE                                      │
│                                                                             │
│  GET /games/{id}/timeline          ──▶  Full timeline artifact              │
│  GET /games/{id}/timeline/compact  ──▶  Compressed timeline                 │
│  GET /games/{id}/compact/{id}/summary ──▶ Moment summary                    │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Phase 1: Ingestion

### 1.1 PBP Scraping

**Source:** `scraper/bets_scraper/scrapers/nba_sportsref.py`

The scraper fetches play-by-play data from Sports Reference after a game is marked `final`.

```python
# Scraper extracts raw PBP from HTML tables
raw_plays = parse_pbp_table(html)

# Normalizes into structured format
normalized: list[NormalizedPlay] = []
for row in raw_plays:
    normalized.append(NormalizedPlay(
        play_index=index,
        quarter=parse_quarter(row),
        game_clock=row.get("time"),
        play_type=classify_play_type(row),
        description=row.get("description"),
        home_score=parse_score(row, "home"),
        away_score=parse_score(row, "away"),
        raw_data=row,
    ))
```

### 1.2 PBP Persistence

**Source:** `scraper/bets_scraper/persistence/plays.py`

Plays are persisted with upsert logic (append-only, no overwrites).

```python
# Upsert using ON CONFLICT DO NOTHING
stmt = insert(SportsGamePlay).values(
    game_id=game_id,
    play_index=play.play_index,
    quarter=play.quarter,
    game_clock=play.game_clock,
    play_type=play.play_type,
    description=play.description,
    home_score=play.home_score,
    away_score=play.away_score,
    raw_data=play.raw_data,
).on_conflict_do_nothing(index_elements=["game_id", "play_index"])
```

### 1.3 Social Post Collection

**Source:** `scraper/bets_scraper/social/collector.py`

Team social posts are collected within a configurable window around game time.

```python
# Window: game_start - 2h to game_end + 2h
posts = fetch_team_tweets(
    handles=[home_team.x_handle, away_team.x_handle],
    start_time=game_start - timedelta(hours=2),
    end_time=game_end + timedelta(hours=2),
)
```

---

## Phase 2: Timeline Generation

**Entry Point:** `POST /api/games/{game_id}/timeline/generate`  
**Source:** `api/app/services/timeline_generator.py`

### 2.1 Prerequisites

Timeline generation requires:
1. Game status = `final`
2. League = `NBA` (only supported league currently)
3. At least one play-by-play record exists

### 2.2 Build PBP Events

**Function:** `_build_pbp_events(plays, game_start)`

Each raw play becomes a timeline event with:
- **Phase assignment** (q1, q2, halftime, q3, q4, ot, postgame)
- **Synthetic timestamp** (computed from phase + game clock)
- **Intra-phase order** (for sorting within a phase)

```python
for play in plays:
    phase = _nba_phase_for_quarter(play.quarter)  # q1, q2, etc.
    
    # Compute position within phase (inverted clock: 12:00 → 0, 0:00 → 720)
    remaining_seconds = _parse_clock_to_seconds(play.game_clock)
    intra_phase_order = NBA_QUARTER_GAME_SECONDS - remaining_seconds
    
    events.append({
        "event_type": "pbp",
        "phase": phase,
        "intra_phase_order": intra_phase_order,
        "synthetic_timestamp": computed_timestamp,
        "description": play.description,
        "home_score": play.home_score,
        "away_score": play.away_score,
        "quarter": play.quarter,
        "game_clock": play.game_clock,
        "play_type": play.play_type,
    })
```

### 2.3 Build Social Events (AI-Assisted)

**Function:** `_build_social_events_async(posts, phase_boundaries, sport)`  
**AI Client:** `api/app/services/ai_client.py`

Each social post gets:
- **Phase assignment** (based on `posted_at` vs computed phase boundaries) — deterministic
- **Role assignment** (AI-assisted with heuristic fallback) — cached
- **Intra-phase order** (based on `posted_at`) — deterministic

#### Role Assignment Flow

```python
def assign_social_role(post, phase):
    # 1. Fast heuristic pass
    role, confidence = _assign_social_role_heuristic(post.text, phase)
    if confidence >= 0.8:
        return role  # Skip AI for high-confidence heuristics
    
    # 2. Cache lookup
    cache_key = hash(post.text + phase)
    if cached := role_cache.get(cache_key):
        return cached
    
    # 3. OpenAI classification
    role = await classify_social_role(post.text, phase)
    
    # 4. Cache result (30-day TTL)
    role_cache.set(cache_key, role)
    return role
```

#### OpenAI Prompt (Social Role)

```text
You are classifying a sports-related social media post.

Context:
- Sport: NBA
- Game phase: {phase}
- This post is from an official team or league account

Choose exactly one role from:
- hype, context, reaction, momentum, highlight, result, reflection, ambient

Post text: "{tweet_text}"

Respond with ONLY the role.
```

| Setting | Value |
|---------|-------|
| Model | `gpt-4o-mini` |
| Temperature | 0 |
| Max Tokens | 5 |

**Why this is safe + cheap:**
- Heuristics handle most cases (pattern matching)
- AI only runs on ambiguous posts (confidence < 0.8)
- Results cached aggressively (30 days)
- Classification output is tiny and deterministic

**Role Taxonomy:**

| Role | Phase | Description |
|------|-------|-------------|
| `hype` | pregame | Game day excitement |
| `context` | pregame | Injury reports, lineups |
| `reaction` | in-game | Live reactions to plays |
| `momentum` | in-game | Scoring runs, swings |
| `highlight` | any | Video/media content |
| `result` | postgame | Final score announcement |
| `reflection` | postgame | Post-game thoughts |
| `ambient` | any | Atmosphere, crowd |

### 2.4 Merge Timeline Events

**Function:** `_merge_timeline_events(pbp_events, social_events)`

Events are merged using **phase-first ordering**:

```python
def sort_key(event):
    return (
        PHASE_ORDER[event["phase"]],  # Primary: phase (0-99)
        event["intra_phase_order"],    # Secondary: position in phase
        0 if event["event_type"] == "pbp" else 1,  # Tertiary: PBP before social
        event.get("play_index", 0),    # Quaternary: play index for stability
    )

sorted_timeline = sorted(all_events, key=sort_key)
```

**Critical:** Timestamps are NOT used for global ordering. Phase is the source of truth.

### 2.5 Game Analysis (AI-Enhanced)

**Function:** `build_nba_game_analysis_async(timeline, summary, game_id)`  
**Source:** `api/app/services/game_analysis.py`

Analyzes the timeline to identify:

1. **Segments** - Chunks of the game with consistent character (deterministic):
   - `opening` - First ~4 scoring plays of Q1
   - `run` - One team scores 8+ consecutive points
   - `swing` - Lead changes hands
   - `blowout` - Margin exceeds 20 points
   - `close` - Final 5 min with margin ≤5
   - `garbage_time` - Final 5 min with margin ≥18
   - `steady` - Normal play, no drama

2. **Highlights** - Notable moments (deterministic):
   - `scoring_run` - Team scores 8+ consecutive
   - `lead_change` - Lead switches teams
   - `quarter_shift` - Big momentum change between quarters
   - `game_deciding_stretch` - When the winner took permanent lead

3. **AI Enrichment (Optional)** - Human-readable labels and tone:
   - Added to segments after deterministic detection
   - Cached per (game_id, segment_id)
   - Never changes the segment structure, only adds `ai_label` and `ai_tone`

#### AI Enrichment Flow

```python
# After deterministic analysis:
analysis = build_nba_game_analysis(timeline, summary)

# AI enrichment adds labels and tone to segments
analysis["segments"] = await enrich_segments_with_ai(
    segments=analysis["segments"],
    game_id=game_id
)
```

#### OpenAI Prompt (Segment Enrichment)

```text
You are labeling stretches of an NBA game for a timeline-based app.

Segment type: {segment_type}
Phases: {start_phase} → {end_phase}
Play count: {play_count}

Your job:
- Add a short, neutral label describing what this stretch *felt like*
- Do NOT invent events
- Do NOT restate scores

Respond with JSON: {"label": "short phrase", "tone": "calm | tense | decisive | flat"}
```

| Setting | Value |
|---------|-------|
| Model | `gpt-4o-mini` |
| Temperature | 0 |
| Max Tokens | 50 |

```python
# Example output (with AI enrichment)
{
    "segments": [
        {
            "segment_id": "segment_1",
            "segment_type": "opening",
            "ai_label": "Cautious start",
            "ai_tone": "calm",
            ...
        },
        {
            "segment_id": "segment_2",
            "segment_type": "run",
            "ai_label": "One-sided surge",
            "ai_tone": "decisive",
            ...
        },
    ],
    "highlights": [...]
}
```

### 2.6 Summary Generation (Primary AI Use)

**Function:** `build_summary_from_timeline_async(timeline, game_analysis, game_id, timeline_version)`

Generates a **reading guide** (not a traditional recap) from the timeline artifact.

**Key Principle:** The summary only references what's in the timeline. It never queries external data.

This is where OpenAI really earns its keep. Summaries are AI-authored but:
- Grounded strictly in timeline + analysis
- Cached permanently per (game_id, timeline_version)
- Generated once per timeline version
- Falls back to template-based if AI unavailable

#### Summary Generation Flow

```python
def build_summary_from_timeline_async(timeline, game_analysis, game_id, timeline_version):
    cache_key = f"{game_id}:{timeline_version}"
    
    if cached := summary_cache.get(cache_key):
        return cached
    
    # Extract facts from timeline (deterministic)
    phases = extract_phases(timeline)
    segments = game_analysis.get("segments", [])
    highlights = game_analysis.get("highlights", [])
    social_counts = count_social_by_phase(timeline)
    
    # Call OpenAI
    prompt = build_summary_prompt(phases, segments, highlights, social_counts)
    summary = await generate_summary(prompt)
    
    # Cache permanently
    summary_cache.set(cache_key, summary)
    return summary
```

#### OpenAI Prompt (Summary Generation)

```text
You are writing a reading guide for a mobile app that shows a game timeline.

This is NOT a recap.

The user is about to scroll a feed that already contains:
- grouped play-by-play moments
- social reactions before, during, and after the game

Your job:
- Describe what kind of game this was
- Point out where attention should increase while scrolling
- Explain how the story unfolds across the timeline

Use the provided structure only.
Do NOT invent events.
Do NOT list plays chronologically.
Do NOT use box-score language.

Timeline facts:
- Phases present: {phases}
- Key segments: {segment_summaries}
- Highlights: {highlights}
- Social activity by phase: {social_counts}

Write 1–2 short paragraphs maximum.
Tone: neutral, guiding, conversational.

Respond with JSON: {"overview": "...", "attention_points": ["...", "...", "..."]}
```

| Setting | Value |
|---------|-------|
| Model | `gpt-4o` |
| Temperature | 0.2 |
| Max Tokens | 180 |

```python
# Output structure
{
    "overview": "This one gets away early. Houston takes control and never really lets go...",
    "attention_points": [
        "The first few minutes set the early tempo",
        "A stretch in the second or third where the gap starts to open",
        "The closing stretch confirms the outcome"
    ],
    "flow": "blowout",  # blowout, comfortable, competitive, close
    "phases_in_timeline": ["q1", "q2", "q3", "q4", "postgame"],
    "social_counts": {"total": 10, "by_phase": {"q4": 1, "postgame": 9}},
    "ai_generated": true,
}
```

### 2.7 Validation

**Function:** `validate_and_log(timeline, summary, game_id)`  
**Source:** `api/app/services/timeline_validation.py`

Before persistence, the timeline is validated:
- Phase ordering is correct (all Q1 before Q2, etc.)
- No duplicate events
- Social posts have valid phases and roles
- Scores are monotonically increasing (with some tolerance)

**Bad timelines never ship.** Validation failures raise errors.

### 2.8 Persistence

The complete artifact is stored:

```python
artifact = SportsGameTimelineArtifact(
    game_id=game_id,
    sport="NBA",
    timeline_version="v1",
    timeline_json=timeline,        # List of events
    summary_json=summary_json,     # Reading guide
    game_analysis_json=game_analysis,  # Segments + highlights
    generated_at=now_utc(),
    generated_by="api",
)
session.add(artifact)
await session.commit()
```

---

## Phase 3: Compact Mode

**Entry Point:** `GET /api/games/{game_id}/timeline/compact?level=2`  
**Source:** `api/app/services/compact_mode.py`

Compact mode compresses the timeline for mobile/quick-view consumption.

### 3.1 Core Principles

1. **Social posts are NEVER dropped**
2. **Operate on semantic groups, not individual events**
3. **Higher excitement → more detail retained**
4. **Excitement scores are internal only (never exposed)**

### 3.2 Semantic Groups

The timeline is analyzed into semantic groups:

| Group Type | Definition | Compression Behavior |
|------------|------------|---------------------|
| `scoring_run` | 3+ consecutive scores by one team | Show all scoring plays |
| `swing` | Lead change sequence | Show pivot plays |
| `drought` | 2+ min without scoring | Collapse to summary |
| `finish` | Final 2 min of period | Never compress |
| `opener` | First 2 min of period | Light compression |
| `routine` | No scoring, no drama | Heavy compression |

### 3.3 Excitement Scoring (Internal Only)

```python
def compute_excitement(group):
    score = 0.0
    
    # Pace: short gaps between plays
    if avg_play_gap < 20_seconds:
        score += 0.3
    
    # Social density: tweets during this stretch
    if tweets_in_window >= 2:
        score += 0.25
    
    # Play types: dunks, blocks, steals
    exciting_plays = count(["dunk", "block", "steal", "made_three"])
    score += min(exciting_plays * 0.1, 0.3)
    
    # Late game bonus
    if is_final_minutes:
        score += 0.2
    
    return min(score, 1.0)
```

### 3.4 Compression Levels

| Level | Name | PBP Retention | Use Case |
|-------|------|---------------|----------|
| 1 | Highlights | ~15-20% | Quick recap |
| 2 | Standard | ~40-50% | Default compact view |
| 3 | Detailed | ~70-80% | Engaged viewing |

### 3.5 Compression Algorithm

> **TERMINOLOGY NOTE (2026-01):** Compact Mode now operates on **Moments** (defined in 
> `moments/`). There is no separate "SemanticGroup" — Moment is the single narrative unit.

```python
def get_compact_timeline(timeline, level):
    # 1. Compute Moments using the unified partition_game()
    # Moment is the SINGLE narrative unit (from moments/ package)
    moments = partition_game(timeline, summary={})
    
    # 2. For each Moment, compute excitement and apply compression
    compressed = []
    for moment in moments:
        # Extract events belonging to this moment
        moment_events = extract_moment_events(timeline, moment)
        
        # Compute excitement (internal only, never exposed)
        excitement = compute_excitement_for_moment(moment, moment_events)
        
        # Apply compression based on MomentType + excitement + level
        if moment.type == MomentType.CLOSING:
            # Never compress closing moments (final minutes)
            compressed.extend(moment_events)
        elif excitement > 0.7:
            # High excitement: show all
            compressed.extend(moment_events)
        elif level == 1:
            # Highlights only: heavy compression
            compressed.extend(compress_moment(moment, moment_events, keep_every_nth=5))
        elif level == 2:
            # Standard: moderate compression
            compressed.extend(compress_moment(moment, moment_events, keep_every_nth=3))
        else:
            # Detailed: light compression
            compressed.extend(compress_moment(moment, moment_events, keep_every_nth=2))
    
    # Social posts are NEVER dropped (handled inside compress_moment)
    return compressed
```

### 3.6 Summary Markers

When plays are compressed, a summary marker may be inserted:

```json
{
    "event_type": "summary",
    "phase": "q2",
    "summary_type": "routine",
    "plays_compressed": 8,
    "duration_seconds": 145,
    "description": "Back-and-forth possession play"
}
```

---

## API Endpoints

### Full Timeline
```
GET /api/games/{game_id}/timeline
```
Returns the complete stored timeline artifact with all events.

### Compact Timeline
```
GET /api/games/{game_id}/timeline/compact?level=2
```
Returns semantically compressed timeline.
- `level=1`: Highlights only (~15-20% PBP)
- `level=2`: Standard (~40-50% PBP)
- `level=3`: Detailed (~70-80% PBP)

### Generate Timeline
```
POST /api/games/{game_id}/timeline/generate
```
Generates and stores a new timeline artifact. Only works for final NBA games.

### Timeline Diagnostic
```
GET /api/games/{game_id}/timeline/diagnostic
```
Debug endpoint showing event counts, phases, and sample events.

---

## Data Flow Summary

```
1. SCRAPE
   Sports Reference HTML → NormalizedPlay → SportsGamePlay (DB)

2. GENERATE (triggered manually or after game final)
   SportsGamePlay + GameSocialPost
   → _build_pbp_events (add phases)                      [deterministic]
   → _build_social_events_async (add phases + AI roles)  [AI: cached]
   → _merge_timeline_events (phase-first sort)           [deterministic]
   → build_nba_game_analysis_async (segments + AI labels)[AI: cached]
   → build_summary_from_timeline_async (AI reading guide)[AI: cached]
   → validate_and_log (quality gate)                     [deterministic]
   → SportsGameTimelineArtifact (DB)

3. SERVE (no AI calls - all pre-baked)
   SportsGameTimelineArtifact
   → Full timeline (as-is)
   → Compact timeline (semantic compression)
   → Moment summaries (template-based)
```

**AI is only used during GENERATE, never during SERVE.**

---

## AI Caching Strategy

All OpenAI outputs are idempotent, cacheable, and regenerable only on version bump.

| Item | Cache Key | TTL |
|------|-----------|-----|
| Social role | `hash(text + phase)` | 30 days |
| Segment labels | `game_id + segment_id` | Permanent |
| Summary | `game_id + timeline_version` | Permanent |

**Key Guarantees:**
- No AI calls on read paths (all cached at generation time)
- No polling, retries, or async UX issues
- iOS app consumes fully baked artifacts
- Costs stay extremely low (AI only on ambiguous cases)

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | _(required)_ | OpenAI API key |
| `OPENAI_MODEL_CLASSIFICATION` | `gpt-4o-mini` | Model for role/segment classification |
| `OPENAI_MODEL_SUMMARY` | `gpt-4o` | Model for summary generation |
| `ENABLE_AI_SOCIAL_ROLES` | `true` | Enable AI role classification |

---

## Key Files

| File | Purpose |
|------|---------|
| `scraper/bets_scraper/scrapers/nba_sportsref.py` | PBP scraping |
| `scraper/bets_scraper/persistence/plays.py` | PBP persistence |
| `api/app/services/timeline_generator.py` | Timeline assembly |
| `api/app/services/moments/` | Lead Ladder-based moment detection |
| `api/app/services/game_analysis.py` | Segment/highlight detection |
| `api/app/services/ai_client.py` | OpenAI integration + caching |
| `api/app/services/compact_mode.py` | Semantic compression |
| `api/app/services/timeline_validation.py` | Quality validation |
| `api/app/routers/game_snapshots.py` | Timeline API endpoints |

---

## One-Line Mental Model

> **Code decides what happened. AI explains why it mattered.**

---

## Changelog

| Date | Change |
|------|--------|
| 2026-01-14 | Initial documentation |
| 2026-01-14 | Added OpenAI integration for roles, segments, summaries |
