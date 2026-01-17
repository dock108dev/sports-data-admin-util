# Documentation Index

## Getting Started

| Guide | Description |
|-------|-------------|
| [Quick Start](QUICK_START.md) | **Start here:** Run locally in 2 minutes |
| [Platform Overview](PLATFORM_OVERVIEW.md) | What this platform does, key features, API endpoints |
| [Architecture](ARCHITECTURE.md) | System components, data flow, database schema |
| [Local Development](LOCAL_DEVELOPMENT.md) | Detailed development setup |
| [Infrastructure](INFRA.md) | Docker configuration, deployment, profiles |

## Timeline System

| Guide | Description |
|-------|-------------|
| [Technical Flow](TECHNICAL_FLOW.md) | **Start here:** Complete flow from PBP to compact timeline |
| [Narrative Time Model](NARRATIVE_TIME_MODEL.md) | Core ordering model: narrative time vs wall-clock time |
| [Timeline Assembly](TIMELINE_ASSEMBLY.md) | Step-by-step timeline generation recipe |
| [PBP Timestamp Usage](PBP_TIMESTAMP_USAGE.md) | How PBP timestamps are used (and not used) |
| [Social Event Roles](SOCIAL_EVENT_ROLES.md) | Narrative roles for social posts (hype, reaction, etc.) |
| [Compact Mode](COMPACT_MODE.md) | Timeline compression strategy |
| [Summary Generation](SUMMARY_GENERATION.md) | How summaries are derived from timelines |
| [Timeline Validation](TIMELINE_VALIDATION.md) | Validation rules and sanity checks |

## Data & Integration

| Guide | Description |
|-------|-------------|
| [Data Sources](DATA_SOURCES.md) | **Start here:** Where data comes from and how it's ingested |
| [Database Integration](DATABASE_INTEGRATION.md) | How to query the sports database |
| [Scoring Logic & Scrapers](SCORE_LOGIC_AND_SCRAPERS.md) | Scraper architecture and execution |
| [X Integration](X_INTEGRATION.md) | Social media scraping from X/Twitter |
| [API Reference](API.md) | FastAPI endpoints and usage |

## Implementation References

Sport-specific implementation details for developers:

| Guide | Description |
|-------|-------------|
| [PBP: NBA Patterns](pbp-nba-patterns.md) | NBA play-by-play parsing patterns |
| [PBP: NBA Review](pbp-nba-review.md) | NBA PBP implementation details |
| [PBP: NHL Hockey Reference](pbp-nhl-hockey-reference.md) | NHL PBP source and parsing |
| [PBP: NCAAB Sports Reference](pbp-ncaab-sports-reference.md) | NCAAB PBP source and parsing |
| [NHL Overview](nhl-hockey-reference-overview.md) | NHL data source overview |
| [Odds: NBA/NCAAB Review](odds-nba-ncaab-review.md) | NBA/NCAAB odds implementation |
| [Odds: NHL Validation](odds-nhl-validation.md) | NHL odds validation |
| [Social: NBA Review](social-nba-review.md) | NBA social implementation |
| [Social: NHL](social-nhl.md) | NHL social accounts |

## Operations

| Guide | Description |
|-------|-------------|
| [Operator Runbook](OPERATOR_RUNBOOK.md) | Production operations, backups, monitoring |
| [Deployment](DEPLOYMENT.md) | Server setup, deploy flow, rollbacks, troubleshooting |
| [Edge Proxy](EDGE_PROXY.md) | Route `/api/*` to FastAPI and `/` to Next.js |
| [Changelog](CHANGELOG.md) | Recent changes and releases |

## Development

| Guide | Description |
|-------|-------------|
| [Adding New Sports](ADDING_NEW_SPORTS.md) | How to enable a new league (SSOT config) |
