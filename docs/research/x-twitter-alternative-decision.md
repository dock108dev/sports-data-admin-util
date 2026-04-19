# ADR: X/Twitter Data Alternative — Decision

**Status**: Accepted  
**Date**: 2026-04-18  
**Supersedes**: `docs/research/x-twitter-data-alternatives.md` (evaluation only)

---

## Context

The current social scraping path uses Playwright to scrape X/Twitter directly. This is fragile: it breaks on DOM changes, requires rotating auth cookies, and has a ~70% uptime profile (see research doc). ISSUE-025 requires evaluating at least two alternatives and prototyping one.

The full cost/rate-limit analysis for X API v2, Apify, Bright Data, Nitter, and hybrid approaches is in `docs/research/x-twitter-data-alternatives.md`. This ADR focuses the decision on two alternatives that offer **free or low-cost access without violating ToS** and then records which one we prototype.

---

## Alternatives Evaluated

### Option A: Official RSS / Atom Feeds (Team Websites and League Portals)

**What it provides:**  
Many teams publish press-release RSS feeds (`/rss`, `/feed`, `/news.rss`). The NFL, NBA, MLB, and NHL all expose league-level RSS feeds for injury reports, roster moves, and official news. These are stable, first-party, require no authentication, and are not rate-limited in practice.

| Dimension | Assessment |
|-----------|------------|
| Cost | Free |
| Data quality | High for official announcements (injuries, signings, trades); zero for real-time game energy / fan reaction |
| Rate limits | No enforced limits — polite 5-min polling is safe |
| Latency | 5–30 min from publish to feed availability |
| Coverage | Structured announcements only. No replies, no media embeds, no casual posts |
| Reliability | Very high — RSS is a 25-year-old standard; team sites rarely restructure feed URLs |

**Tradeoffs:**  
Good for factual events (roster moves, injury designations) but completely misses the social texture needed for embedded narrative posts. The `TeamSocialPost` model expects posts that can be embedded in game flow blocks — official press releases are the wrong register. Also, many teams that have active social presences do not publish RSS at all (e.g., X-only teams with no website feed).

**Verdict:** Viable as a secondary enrichment layer for structured announcements, not as a primary social content source.

---

### Option B: Bluesky AT Protocol API

**What it provides:**  
Bluesky is a federated social network built on the AT Protocol. It has a fully public, unauthenticated REST API (`https://public.api.bsky.app/xrpc`). A growing number of sports journalists, beat writers, and official team accounts have Bluesky presence. The API returns posts with text, timestamps, image/video embeds, like/repost counts, and cursor-based pagination — a clean structural match to `CollectedPost`.

| Dimension | Assessment |
|-----------|------------|
| Cost | Free — public API with no credit system |
| Data quality | Medium-high for accounts that are active; account coverage is lower than X today |
| Rate limits | Undocumented but generous in practice; `app.bsky.feed.getAuthorFeed` supports 25–100 posts per page; unauthenticated callers share a generous global pool |
| Latency | Near-realtime (seconds after post) |
| Coverage | ~20–30% of team accounts have Bluesky presence as of early 2026; growing |
| Reliability | High — official open API, stable lexicon versioning |

**Tradeoffs:**  
Account coverage is the primary limitation: not every team is on Bluesky, and those that are may post less frequently than on X. However, the API is stable, free, and requires no scraping infrastructure. It produces records structurally identical to what the current pipeline ingests. As a **parallel collector** it adds genuine signal without replacing Playwright.

**Verdict:** Best prototype candidate — low cost, high reliability, clean API, and structurally compatible with existing pipeline.

---

## Decision

**Prototype Bluesky (Option B).**

Reasons:
1. Free, unauthenticated, stable public API.
2. JSON response maps directly to `CollectedPost` without transformation gymnastics.
3. Can run alongside Playwright with no changes to tweet_mapper, persistence, or game-phase assignment.
4. Account coverage gap is acceptable for a prototype; it can be backfilled as Bluesky adoption grows.

RSS (Option A) is useful for a different problem (structured announcements) and should be reconsidered as an independent ingestion path in Phase 3 when injury/roster data enrichment is prioritized.

---

## Implementation

**Module:** `scraper/sports_scraper/social/bluesky_collector.py`  
**Class:** `BlueSkyCollector`  
**Feature flag:** `ENABLE_BLUESKY_SOCIAL=true` (env var, defaults to `false`)  
**Gating:** `settings.bluesky_enabled` in `scraper/sports_scraper/config.py`

The collector:
- Calls `GET /xrpc/app.bsky.feed.getAuthorFeed?actor=<handle>&filter=posts_no_replies`
- Paginates via cursor until all posts in `[window_start, window_end]` are collected
- Skips reposts (items with `reason` key)
- Produces `CollectedPost` records with `platform="bluesky"`
- Stops paginating early once posts fall before `window_start`

The module is **not wired into any Celery task** yet. To activate it in production, a task must:
1. Check `settings.bluesky_enabled` before constructing a `BlueSkyCollector`
2. Persist returned `CollectedPost` records via the existing `team_collector` persistence path
3. Map the posts via `map_unmapped_tweets` — no changes needed there

---

## Remaining Risks

- Bluesky rate limits are undocumented for unauthenticated access; we should add per-handle backoff if we hit HTTP 429.
- CDN URLs for images (`cdn.bsky.app`) are reference-based and may require authenticated access for some content.
- Platform field `"bluesky"` will need to be added to any `platform` enum / column check constraints in the API layer before persistence is wired up.
