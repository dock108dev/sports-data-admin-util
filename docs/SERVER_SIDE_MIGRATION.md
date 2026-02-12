# Server-Side Migration — Architecture Reference

> Client-side computation moved to the admin backend so consumer apps become thin display layers.

**Status:** All 6 phases are **implemented and production-ready**.

---

## Motivation

The Swift app (`scroll-down-app`) performed ~2,000 lines of deterministic computation on every render that belongs server-side: odds math, tier classification, color mapping, period labels, and timeline merging. This caused duplicated logic across consumers, wasted bandwidth, inconsistency risk, and no central source of truth for team colors.

**Result:** The admin backend is now the single source of truth for all derived data. Consumer apps read pre-computed values from the API.

---

## Architecture Overview

```
                    ┌─────────────────────────────────┐
                    │       sports-data-admin          │
                    │                                  │
                    │  ┌──────────┐  ┌──────────────┐  │
  Raw Data ──────►  │  │ Scraper  │  │  PostgreSQL   │  │
  (APIs, sites)     │  │ (Celery) │──│  (source of   │  │
                    │  └──────────┘  │   truth)      │  │
                    │                └──────┬───────┘  │
                    │                       │          │
                    │  ┌────────────────────▼───────┐  │
                    │  │      FastAPI Backend        │  │
                    │  │                             │  │
                    │  │  team_colors.py             │  │
                    │  │  derived_metrics.py         │  │
                    │  │  period_labels.py           │  │
                    │  │  play_tiers.py              │  │
                    │  │  odds_events.py             │  │
                    │  │  timeline_generator.py      │  │
                    │  └─────────┬───────────────────┘  │
                    │            │                      │
                    │  ┌─────────▼───────────────────┐  │
                    │  │   Admin UI (Next.js)         │  │
                    │  │   Verification dashboard     │  │
                    │  └─────────────────────────────┘  │
                    └────────────┬──────────────────────┘
                                 │
                    ┌────────────▼──────────────────────┐
                    │     Consumer Apps                  │
                    │     (scroll-down-app, etc.)        │
                    │     Read pre-computed values only   │
                    └───────────────────────────────────┘
```

---

## Phases Summary

| Phase | Name | What It Does | Status |
|-------|------|-------------|--------|
| 1 | **Team Colors** | DB-stored team colors with clash detection, replacing 742 lines of hardcoded Swift color dictionaries | Complete |
| 2 | **Derived Metrics** | 40+ pre-computed odds metrics (spread, total, moneyline, outcomes, labels) served via API | Complete |
| 3 | **Period Labels** | Sport-aware period labels (Q1-Q4, H1-H2, P1-P3, OT, SO) computed server-side | Complete |
| 4 | **Play Tiers** | Tier 1/2/3 classification with grouped Tier-3 collapsing for UI | Complete |
| 5 | **Admin UI** | Verification dashboards for all computed values (colors, metrics, tiers, flows) | Complete |
| 6 | **Timeline Merging** | PBP + social + odds merged into a unified chronological timeline | Complete |

---

## API Reference

All endpoints use base path `/api/admin/sports`. All responses use **camelCase** field names.

| Method | Path | Phase | Description |
|--------|------|-------|-------------|
| `GET` | `/teams` | 1 | Team list with `colorLightHex`, `colorDarkHex` |
| `GET` | `/teams/{id}` | 1 | Team detail with colors |
| `PATCH` | `/teams/{id}/colors` | 1 | Update team colors |
| `GET` | `/games` | 2 | Game list with `derivedMetrics` on each game |
| `GET` | `/games/{id}` | 2,3,4 | Game detail with `derivedMetrics`, plays with `periodLabel`, `timeLabel`, `tier`, and `groupedPlays` |
| `GET` | `/games/{id}/timeline` | 6 | Retrieve persisted timeline artifact |
| `POST` | `/games/{id}/timeline/generate` | 6 | Generate/regenerate timeline |
| `GET` | `/games/{id}/flow` | — | Game flow narratives (pre-existing) |

---

## Key Files

| File | Purpose |
|------|---------|
| `api/app/services/team_colors.py` | Color clash detection utilities |
| `api/app/services/derived_metrics.py` | 40+ odds-derived metrics computation |
| `api/app/services/period_labels.py` | Sport-aware period/time labels |
| `api/app/services/play_tiers.py` | Tier classification and Tier-3 grouping |
| `api/app/services/odds_events.py` | Book selection, line movement detection |
| `api/app/services/timeline_generator.py` | Timeline artifact orchestration |
| `api/app/services/timeline_events.py` | PBP + social + odds merge |
| `api/app/services/timeline_validation.py` | Timeline validation rules |
| `api/app/routers/sports/games.py` | Game endpoints with derived data |
| `api/app/routers/sports/game_timeline.py` | Timeline and flow endpoints |
| `api/app/routers/sports/teams.py` | Team endpoints with colors |
