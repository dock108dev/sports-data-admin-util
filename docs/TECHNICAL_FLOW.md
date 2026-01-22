# Technical Flow: Play-by-Play to Game Story

> **Audience:** Developers working on the sports data pipeline  
> **Last Updated:** 2026-01-22  
> **Status:** Authoritative

---

## Overview

This document traces a game's journey from raw play-by-play data to the final narrative story served to apps.

The system operates in three distinct phases:
1. **Ingestion** — Scrape and normalize data
2. **Structure** — Generate deterministic chapters
3. **Narrative** — AI-powered story generation

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
│  [SportsGamePlay]  ──ChapterizerV1──▶  [Chapters with Reason Codes]        │
│                            │                                                │
│                            ▼                                                │
│  [Chapters]  ──StoryState Builder──▶  [Running Context]                    │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           NARRATIVE PHASE (AI)                               │
│                                                                             │
│  [Chapters + StoryState]  ──AI Sequential──▶  [Chapter Summaries]          │
│                                    │                                        │
│                                    ▼                                        │
│  [Summaries]  ──AI Independent──▶  [Chapter Titles]                        │
│                                    │                                        │
│                                    ▼                                        │
│  [Summaries]  ──AI Synthesis──▶  [Compact Story]                           │
│                                    │                                        │
│                                    ▼                                        │
│  [GameStory] ──persist──▶ [Admin UI / Apps]                                │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Phase 1: Ingestion

### 1.1 PBP Scraping

**Source:** `scraper/bets_scraper/scrapers/`

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

**Source:** `scraper/bets_scraper/persistence/plays.py`

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

Chapters are deterministic structural boundaries based on NBA v1 rules.

**Input:** Ordered list of plays  
**Output:** List of chapters with reason codes  
**AI:** None  
**Deterministic:** Yes

```python
from app.services.chapters import build_chapters

# Build chapters from plays
game_story = build_chapters(
    timeline=plays,
    game_id=game_id,
    sport="NBA",
)

# Result: GameStory with chapters
# Each chapter has:
# - chapter_id (unique)
# - play_start_idx, play_end_idx (contiguous range)
# - plays (raw play data)
# - reason_codes (why boundary exists)
# - period, time_range (metadata)
```

**Boundary Rules (NBA v1):**

**Hard Boundaries (Always Break):**
- Period start/end
- Overtime start
- Game end

**Scene Reset Boundaries:**
- Team timeout
- Official timeout
- Coach's challenge
- Instant replay review

**Momentum Boundaries (Minimal v1):**
- Crunch time start (Q4 <5min + close game)

See [NBA_V1_BOUNDARY_RULES.md](NBA_V1_BOUNDARY_RULES.md) for complete rules.

### 2.2 Story State Builder

**Source:** `api/app/services/chapters/story_state.py`

Story State is deterministic context derived from prior chapters only.

**Input:** Chapters 0..N-1  
**Output:** StoryState  
**AI:** None  
**Deterministic:** Yes

```python
from app.services.chapters import derive_story_state_from_chapters

# Build story state from prior chapters
story_state = derive_story_state_from_chapters(
    chapters=prior_chapters,
    sport="NBA",
)

# Result: StoryState with:
# - players (top 6 by points_so_far)
# - teams (score_so_far, momentum_hint)
# - theme_tags (bounded list, max 8)
# - constraints (no_future_knowledge: true)
```

**Derivation Rules:**
- Points accumulated from made shots/FTs
- Notable actions from play text tags (dunk, block, steal, 3PT, etc.)
- Momentum hints from chapter reason codes
- Theme tags from play patterns

**Bounded Lists:**
- Top 6 players by points
- Max 5 notable actions per player
- Max 8 theme tags

See [AI_CONTEXT_POLICY.md](AI_CONTEXT_POLICY.md) for complete rules.

---

## Phase 3: Narrative (AI)

### 3.1 Chapter Summary Generation (Sequential)

**Source:** `api/app/services/chapters/summary_generator.py`

Generate narrative summaries for each chapter sequentially.

**Input:** Current chapter + prior summaries + story state  
**Output:** Chapter summary (1-3 sentences)  
**AI:** Yes (OpenAI)  
**Sequential:** Yes (one chapter at a time)

```python
from app.services.chapters import generate_summaries_sequentially
from app.services.openai_client import get_openai_client

# Get AI client
ai_client = get_openai_client()

# Generate summaries sequentially
summary_results = generate_summaries_sequentially(
    chapters=game_story.chapters,
    sport="NBA",
    ai_client=ai_client,
)

# Result: List of ChapterSummaryResult
# Each contains:
# - chapter_summary (1-3 sentences)
# - spoiler_warnings (if any)
# - prompt_used (for debugging)
```

**Context Rules:**
- ✅ Prior chapter summaries (0..N-1)
- ✅ Story state from prior chapters
- ✅ Current chapter plays
- ❌ No future chapters
- ❌ No full game stats
- ❌ No box score

**Validation:**
- Spoiler detection (banned phrases)
- Future knowledge detection
- Sentence count (1-3)
- No bullet points

See [AI_CONTEXT_POLICY.md](AI_CONTEXT_POLICY.md) for complete policy.

### 3.2 Chapter Title Generation (Independent)

**Source:** `api/app/services/chapters/title_generator.py`

Generate titles from existing summaries only.

**Input:** Chapter summary only  
**Output:** Chapter title (3-8 words)  
**AI:** Yes (OpenAI)  
**Sequential:** No (independent per chapter)

```python
from app.services.chapters import generate_titles_for_chapters

# Generate titles from summaries
title_results = generate_titles_for_chapters(
    chapters=game_story.chapters,
    summaries=[ch.summary for ch in game_story.chapters],
    ai_client=ai_client,
)

# Result: List of ChapterTitleResult
# Each contains:
# - chapter_title (3-8 words)
# - validation_result (pass/fail)
```

**Context Rules:**
- ✅ Chapter summary only
- ✅ Optional metadata (period, time_range)
- ❌ No plays
- ❌ No story state
- ❌ No other summaries

**Validation:**
- Length (3-8 words)
- No numbers
- No punctuation (except apostrophes)
- Spoiler detection

### 3.3 Compact Story Generation (Full Arc)

**Source:** `api/app/services/chapters/compact_story_generator.py`

Generate full game recap from chapter summaries.

**Input:** All chapter summaries (ordered)  
**Output:** Compact story (4-12 min read)  
**AI:** Yes (OpenAI)  
**Hindsight:** Allowed

```python
from app.services.chapters import generate_compact_story

# Generate compact story from summaries
compact_result = generate_compact_story(
    chapter_summaries=[ch.summary for ch in game_story.chapters],
    chapter_titles=[ch.title for ch in game_story.chapters],
    sport="NBA",
    ai_client=ai_client,
)

# Result: CompactStoryResult
# Contains:
# - compact_story (full game recap)
# - reading_time_minutes (estimated)
# - word_count
```

**Context Rules:**
- ✅ All chapter summaries
- ✅ Optional chapter titles
- ✅ Hindsight language allowed
- ❌ No raw plays
- ❌ No story state
- ❌ No box score

**Validation:**
- Non-empty
- Paragraph-based (no bullets)
- No play-by-play listing
- No new entities (not in summaries)

---

## API Endpoints

### Story Generation

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/admin/sports/games/{id}/story` | GET | Fetch complete game story |
| `/api/admin/sports/games/{id}/story-state` | GET | Fetch story state before chapter N |
| `/api/admin/sports/games/{id}/story/regenerate-chapters` | POST | Regenerate chapters |
| `/api/admin/sports/games/{id}/story/regenerate-summaries` | POST | Generate AI summaries |
| `/api/admin/sports/games/{id}/story/regenerate-titles` | POST | Generate AI titles |
| `/api/admin/sports/games/{id}/story/regenerate-compact` | POST | Generate compact story |
| `/api/admin/sports/games/{id}/story/regenerate-all` | POST | Full pipeline |
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

### Example: Generate Story for Game 110536

**Step 1: Fetch PBP**
```sql
SELECT * FROM sports_game_plays 
WHERE game_id = 110536 
ORDER BY play_index;
-- Returns 477 plays
```

**Step 2: Generate Chapters (Deterministic)**
```python
game_story = build_chapters(timeline=plays, game_id=110536, sport="NBA")
# Result: 18 chapters with reason codes
```

**Step 3: Generate Summaries (Sequential AI)**
```python
summary_results = generate_summaries_sequentially(
    chapters=game_story.chapters,
    sport="NBA",
    ai_client=openai_client,
)
# Takes ~30-60 seconds (sequential)
# Result: 18 chapter summaries
```

**Step 4: Generate Titles (Independent AI)**
```python
title_results = generate_titles_for_chapters(
    chapters=game_story.chapters,
    summaries=[r.chapter_summary for r in summary_results],
    ai_client=openai_client,
)
# Takes ~10-20 seconds
# Result: 18 chapter titles
```

**Step 5: Generate Compact Story (Full Arc AI)**
```python
compact_result = generate_compact_story(
    chapter_summaries=[r.chapter_summary for r in summary_results],
    chapter_titles=[r.chapter_title for r in title_results],
    sport="NBA",
    ai_client=openai_client,
)
# Takes ~5-10 seconds
# Result: Full game recap
```

**Total Time:** ~45-90 seconds for complete story generation

---

## AI Usage Principle

> **OpenAI is used only for narrative generation — never for structure, ordering, or boundaries.**

**What AI Does:**
- ✅ Generate chapter summaries
- ✅ Generate chapter titles
- ✅ Generate compact story
- ✅ Interpret plays with sportscaster voice

**What AI Does NOT Do:**
- ❌ Define chapter boundaries
- ❌ Decide structure
- ❌ Compute importance
- ❌ Order events
- ❌ Filter plays

**Principle:** Code decides structure. AI adds meaning.

---

## Key Modules

| Module | Purpose | AI | Deterministic |
|--------|---------|----|--------------| 
| `scraper/` | Data ingestion | No | Yes |
| `api/app/services/chapters/chapterizer.py` | Chapter boundaries | No | Yes |
| `api/app/services/chapters/story_state.py` | Running context | No | Yes |
| `api/app/services/chapters/summary_generator.py` | Chapter summaries | Yes | No |
| `api/app/services/chapters/title_generator.py` | Chapter titles | Yes | No |
| `api/app/services/chapters/compact_story_generator.py` | Compact story | Yes | No |
| `api/app/services/openai_client.py` | OpenAI integration | Yes | No |
| `api/app/routers/sports/story.py` | Story API endpoints | Mixed | Mixed |

---

## Configuration

### Environment Variables

**Required:**
- `DATABASE_URL` — PostgreSQL connection string
- `REDIS_URL` — Redis connection string (for Celery)

**Optional (AI Features):**
- `OPENAI_API_KEY` — Enable AI narrative generation
- `OPENAI_MODEL_CLASSIFICATION` — Model for classification (default: gpt-4o-mini)

**Without OpenAI API Key:**
- Chapters generate normally (deterministic)
- AI endpoints return "API key not configured" error
- System remains fully functional for structure inspection

---

## Performance Characteristics

### Deterministic Operations (Instant)
- Chapter generation: <1 second for 500 plays
- Story state derivation: <1 second
- Bulk chapter generation: ~22 games/second

### AI Operations (Sequential)
- Chapter summaries: ~2-3 seconds per chapter
- Chapter titles: ~1-2 seconds per chapter
- Compact story: ~5-10 seconds

**Example:** 18-chapter game = ~60-90 seconds total

---

## Testing

### Unit Tests

**Deterministic Components:**
```bash
cd api
pytest tests/test_chapterizer.py
pytest tests/test_story_state.py
pytest tests/test_coverage_validator.py
```

**AI Components (with mocks):**
```bash
pytest tests/test_summary_generator.py
pytest tests/test_title_generator.py
pytest tests/test_compact_story_generator.py
pytest tests/test_narrative_validator.py
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
- [NBA v1 Boundary Rules](NBA_V1_BOUNDARY_RULES.md)
- [AI Context Policy](AI_CONTEXT_POLICY.md)

**Implementation:**
- [AI Signals (NBA v1)](AI_SIGNALS_NBA_V1.md)
- [Admin UI Guide](ADMIN_UI_STORY_GENERATOR.md)
- [API Reference](API.md)

**Operations:**
- [Local Development](LOCAL_DEVELOPMENT.md)
- [Deployment](DEPLOYMENT.md)
- [Operator Runbook](OPERATOR_RUNBOOK.md)

---

## Summary

**Pipeline:** PBP → Chapters (deterministic) → StoryState (deterministic) → AI (narrative) → GameStory

**Key Principle:** Structure is deterministic. AI adds meaning to existing structure.

**Performance:** Chapters generate instantly. AI narrative takes ~60-90 seconds for full game.

**Status:** Production-ready for NBA v1.
