# Technical Flow: Play-by-Play to Game Story

> **Audience:** Developers working on the sports data pipeline
> **Last Updated:** 2026-01-24
> **Status:** Authoritative

---

## Overview

This document traces a game's journey from raw play-by-play data to the final narrative story served to apps.

The system operates in three distinct phases:
1. **Ingestion** — Scrape and normalize data
2. **Structure** — Generate deterministic chapters and sections
3. **Narrative** — Single AI call renders the complete story

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           INGESTION PHASE                                    │
│                                                                             │
│  [External Sources]  ──scrape──▶  [Scraper]  ──persist──▶  [PostgreSQL]    │
│                                                                             │
│  Raw HTML ────────────────────▶ NormalizedPlay ─────────▶ SportsGamePlay   │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           STRUCTURE PHASE (Deterministic)                    │
│                                                                             │
│  [SportsGamePlay]  ──Chapterizer──▶  [Chapters with Reason Codes]          │
│                            │                                                │
│                            ▼                                                │
│  [Chapters]  ──Section Builder──▶  [StorySections with Stats/Headers]      │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           NARRATIVE PHASE (Single AI Call)                   │
│                                                                             │
│  [StorySections + Headers]  ──Story Renderer──▶  [Compact Story]           │
│                                                                             │
│  One AI call renders the entire story from the structured outline.         │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Phase 1: Ingestion

### 1.1 PBP Scraping

**Source:** `scraper/sports_scraper/scrapers/`

The scraper fetches play-by-play data from external sources after a game is marked `final`.

**Sources by Sport:**
- **NBA:** Sports Reference (sportsreference.com)
- **NHL:** Hockey Reference (hockey-reference.com)
- **NCAAB:** Sports Reference (sports-reference.com)

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

**Source:** `scraper/sports_scraper/persistence/plays.py`

Normalized plays are persisted to PostgreSQL:

```python
# Upsert plays (idempotent)
for play in normalized_plays:
    session.merge(SportsGamePlay(
        game_id=game_id,
        play_index=play.play_index,
        quarter=play.quarter,
        game_clock=play.game_clock,
        play_type=play.play_type,
        description=play.description,
        team_id=play.team_id,
        home_score=play.home_score,
        away_score=play.away_score,
        raw_data=play.raw_data,
    ))
```

**Key Properties:**
- Idempotent (can re-scrape safely)
- Preserves raw data
- Indexed by `(game_id, play_index)`

---

## Phase 2: Structure (Deterministic)

### 2.1 Chapter Generation

**Source:** `api/app/services/chapters/chapterizer.py`

Chapters are deterministic structural boundaries based on NBA rules.

**Input:** Ordered list of plays
**Output:** List of chapters with reason codes
**AI:** None
**Deterministic:** Yes

**Boundary Rules (NBA):**

**Hard Boundaries (Always Break):**
- Period start/end
- Overtime start
- Game end

**Scene Reset Boundaries:**
- Team timeout
- Official timeout
- Coach's challenge
- Instant replay review

**Momentum Boundaries:**
- Crunch time start (Q4 <5min + close game)

See [NBA_BOUNDARY_RULES.md](NBA_BOUNDARY_RULES.md) for complete rules.

### 2.2 Section Building

**Source:** `api/app/services/chapters/story_section.py`

Sections transform chapters into AI-ready input with stats and context.

**Input:** Chapters
**Output:** StorySections with beat types, stats, and notes
**AI:** None
**Deterministic:** Yes

```python
@dataclass
class StorySection:
    section_index: int
    beat_type: BeatType  # FAST_START, RUN, RESPONSE, STALL, etc.
    team_stat_deltas: dict[str, TeamStatDelta]
    player_stat_deltas: dict[str, PlayerStatDelta]
    notes: list[str]  # Machine-generated observations
    start_score: dict[str, int]
    end_score: dict[str, int]
    start_period: int | None
    end_period: int | None
    start_time_remaining: int | None  # Seconds
    end_time_remaining: int | None
```

**Beat Types:**
- `FAST_START` — High-scoring opening
- `BACK_AND_FORTH` — Neither team separating
- `EARLY_CONTROL` — One team establishing lead
- `RUN` — 8+ unanswered points
- `RESPONSE` — Comeback after a run
- `STALL` — Scoring drought
- `CRUNCH_SETUP` — Late tight game
- `CLOSING_SEQUENCE` — Final minutes
- `OVERTIME` — Extra period

### 2.3 Header Generation

**Source:** `api/app/services/chapters/header_reset.py`

Deterministic one-sentence orientation anchors for each section.

**Input:** StorySections
**Output:** Headers (one per section)
**AI:** None
**Deterministic:** Yes

Headers tell the reader WHERE we are, not WHAT happened. They are:
- Orientation resets for the reader
- Structural guides for AI rendering
- NOT narrative or storytelling

**Example Headers:**
- "The floor was alive from the opening tip." (FAST_START)
- "One side started pulling away." (RUN)
- "The trailing team clawed back into it." (RESPONSE)
- "Scoring dried up on both ends." (STALL)

---

## Phase 3: Narrative (Single AI Call)

### 3.1 Story Rendering

**Source:** `api/app/services/chapters/story_renderer.py`

**THE ONLY PLACE AI GENERATES NARRATIVE TEXT.**

The story renderer takes the fully-constructed outline (sections + headers) and renders it into a cohesive prose story in a single AI call.

**Input:**
- StorySections with stats and notes
- Deterministic headers
- Team names and final score
- Target word count

**Output:**
- Compact story (prose narrative)
- Word count

**AI Role (Strictly Limited):**
- Turn outline into prose
- Use provided headers verbatim
- Match target word count approximately
- Add language polish WITHOUT adding logic

**AI Is NOT Allowed To:**
- Plan or restructure
- Infer importance
- Invent context
- Decide what matters
- Add drama not supported by input

### 3.2 Rendering Input Structure

```python
@dataclass
class SectionRenderInput:
    header: str  # Deterministic (use verbatim)
    beat_type: BeatType
    team_stat_deltas: list[dict]
    player_stat_deltas: list[dict]  # Top 1-3 per team
    notes: list[str]
    start_score: dict[str, int]
    end_score: dict[str, int]
    start_period: int | None
    end_period: int | None
    start_time_remaining: int | None
    end_time_remaining: int | None

@dataclass
class StoryRenderInput:
    sport: str
    home_team_name: str
    away_team_name: str
    target_word_count: int
    sections: list[SectionRenderInput]
    closing: ClosingContext
```

### 3.3 Prompt Rules

The AI prompt includes comprehensive rules for:

- **Opening Paragraph:** Establish texture, not summary. Create curiosity.
- **Story Shape:** Build→Swing→Resolve, Early Break→Control→Fade, etc.
- **Narrative Flow:** Paragraphs build on each other, carry tension forward.
- **Layer Responsibility:** Overview layer (compact story) vs. detail layer (expanded sections).
- **Game Time Rules:** Anchor moments in quarters and clock time.
- **Run Presentation:** Runs are events, not calculations.
- **Stat Usage:** 0-2 specific stats per section, attached to moments.
- **Closing Paragraph:** Resolution matching the story's shape.

See `story_renderer.py` for the complete prompt.

---

## API Endpoints

### Story Generation

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/admin/sports/games/{id}/story` | GET | Fetch complete game story |
| `/api/admin/sports/games/{id}/story/regenerate-all` | POST | Full pipeline regeneration |
| `/api/admin/sports/games/bulk-generate` | POST | Bulk generation for date range |

### Game Data

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/admin/sports/games` | GET | List games |
| `/api/admin/sports/games/{id}` | GET | Game details |
| `/api/admin/sports/games/{id}/preview-score` | GET | Preview score |

### Scraper Management

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/admin/sports/scraper/runs` | GET | List scraper runs |
| `/api/admin/sports/scraper/runs` | POST | Start scraper |
| `/api/admin/sports/scraper/runs/{id}` | GET | Get run details |
| `/api/admin/sports/scraper/runs/{id}/cancel` | POST | Cancel run |

See [API.md](API.md) for complete reference.

---

## Data Flow Example

### Example: Generate Story for a Game

**Step 1: Fetch PBP**
```sql
SELECT * FROM sports_game_plays
WHERE game_id = 110536
ORDER BY play_index;
-- Returns ~400-500 plays
```

**Step 2: Generate Chapters (Deterministic)**
```python
chapters = build_chapters(timeline=plays, game_id=game_id, sport="NBA")
# Result: ~15-20 chapters with reason codes
```

**Step 3: Build Sections (Deterministic)**
```python
sections = build_story_sections(chapters, sport="NBA")
# Result: StorySections with beat types, stats, notes
```

**Step 4: Generate Headers (Deterministic)**
```python
headers = generate_all_headers(sections)
# Result: One deterministic header per section
```

**Step 5: Render Story (Single AI Call)**
```python
render_input = build_story_render_input(
    sections=sections,
    headers=headers,
    sport="NBA",
    home_team_name="Lakers",
    away_team_name="Celtics",
    target_word_count=compute_target_word_count(len(sections)),
    decisive_factors=["12-0 run in Q3", "Late free throws"],
)

result = render_story(render_input, ai_client=openai_client)
# Takes ~5-15 seconds
# Result: Complete prose story
```

**Total Time:** ~5-20 seconds for complete story generation

---

## AI Usage Principle

> **OpenAI is used only for narrative rendering — never for structure, ordering, or boundaries.**

**What AI Does:**
- ✅ Render sections into prose
- ✅ Use headers verbatim
- ✅ Follow prompt rules for tone, flow, shape
- ✅ Polish language

**What AI Does NOT Do:**
- ❌ Define section boundaries
- ❌ Decide structure
- ❌ Compute importance
- ❌ Order events
- ❌ Filter content
- ❌ Generate chapter summaries or titles (legacy)

**Principle:** Code decides structure. AI renders it.

---

## Key Modules

| Module | Purpose | AI | Deterministic |
|--------|---------|----|--------------|
| `scraper/` | Data ingestion | No | Yes |
| `api/app/services/chapters/chapterizer.py` | Chapter boundaries | No | Yes |
| `api/app/services/chapters/story_section.py` | Section building | No | Yes |
| `api/app/services/chapters/beat_classifier.py` | Beat type classification | No | Yes |
| `api/app/services/chapters/header_reset.py` | Deterministic headers | No | Yes |
| `api/app/services/chapters/story_renderer.py` | Story rendering | Yes | No |
| `api/app/services/openai_client.py` | OpenAI integration | Yes | No |
| `api/app/routers/sports/story.py` | Story API endpoints | Mixed | Mixed |

---

## Configuration

### Environment Variables

**Required:**
- `DATABASE_URL` — PostgreSQL connection string
- `REDIS_URL` — Redis connection string (for Celery)

**Optional (AI Features):**
- `OPENAI_API_KEY` — Enable AI narrative rendering

**Without OpenAI API Key:**
- Chapters and sections generate normally (deterministic)
- AI endpoints return "API key not configured" error
- System remains functional for structure inspection

---

## Performance Characteristics

### Deterministic Operations (Instant)
- Chapter generation: <1 second for 500 plays
- Section building: <1 second
- Header generation: <1 second
- Bulk chapter generation: ~22 games/second

### AI Operations (Single Call)
- Story rendering: ~5-15 seconds per game

**Example:** Full game story = ~5-20 seconds total (mostly AI time)

---

## Testing

### Unit Tests

**Deterministic Components:**
```bash
cd api
pytest tests/test_chapterizer.py
pytest tests/test_story_section.py
pytest tests/test_story_renderer.py
```

### Integration Tests

```bash
# Full story generation
pytest tests/test_story_api.py
```

---

## Deployment

**Infrastructure:** Docker Compose
**Services:** API, Web, Scraper, PostgreSQL, Redis

```bash
cd infra
docker compose --profile dev up -d --build
```

**URLs:**
- Admin UI: http://localhost:3000
- API Docs: http://localhost:8000/docs
- Health: http://localhost:8000/healthz

See [DEPLOYMENT.md](DEPLOYMENT.md) for production setup.

---

## Related Documentation

**Core Concepts:**
- [Book + Chapters Model](BOOK_CHAPTERS_MODEL.md)
- [NBA Boundary Rules](NBA_BOUNDARY_RULES.md)

**Implementation:**
- [Admin UI Guide](ADMIN_UI_STORY_GENERATOR.md)
- [API Reference](API.md)

**Operations:**
- [Local Development](LOCAL_DEVELOPMENT.md)
- [Deployment](DEPLOYMENT.md)
- [Operator Runbook](OPERATOR_RUNBOOK.md)

---

## Summary

**Pipeline:** PBP → Chapters → Sections → Headers → Single AI Call → Compact Story

**Key Principle:** Structure is deterministic. AI renders it into prose.

**Performance:** Structure generates instantly. AI rendering takes ~5-15 seconds per game.

**Status:** Production-ready for NBA.
