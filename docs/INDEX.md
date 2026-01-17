# Documentation Index

## Getting Started

| Guide | Description |
|-------|-------------|
| [Quick Start](QUICK_START.md) | **Start here:** Run locally in 2 minutes |
| [Platform Overview](PLATFORM_OVERVIEW.md) | What this platform does and key features |
| [Architecture](ARCHITECTURE.md) | System components, data flow, database schema |
| [API Reference](API.md) | FastAPI endpoints and usage |

## Development

| Guide | Description |
|-------|-------------|
| [Local Development](LOCAL_DEVELOPMENT.md) | Detailed local setup and troubleshooting |
| [Adding New Sports](ADDING_NEW_SPORTS.md) | How to enable a new league |
| [Database Integration](DATABASE_INTEGRATION.md) | Querying the sports database |

## Timeline System

The core product: turning play-by-play and social data into a narrative timeline.

| Guide | Description |
|-------|-------------|
| [Moment System Contract](MOMENT_SYSTEM_CONTRACT.md) | **Start here:** The contract for moment detection |
| [Technical Flow](TECHNICAL_FLOW.md) | Complete pipeline from PBP to compact timeline |
| [Narrative Time Model](NARRATIVE_TIME_MODEL.md) | Phase-based ordering (narrative vs wall-clock time) |
| [Timeline Assembly](TIMELINE_ASSEMBLY.md) | Step-by-step timeline generation |
| [Timeline Validation](TIMELINE_VALIDATION.md) | Validation rules and sanity checks |
| [Compact Mode](COMPACT_MODE.md) | Timeline compression for mobile |
| [Summary Generation](SUMMARY_GENERATION.md) | AI-generated reading guides |
| [PBP Timestamp Usage](PBP_TIMESTAMP_USAGE.md) | How PBP timestamps are used |
| [Social Event Roles](SOCIAL_EVENT_ROLES.md) | Narrative roles for social posts |

## Data Ingestion

| Guide | Description |
|-------|-------------|
| [Data Sources](DATA_SOURCES.md) | **Start here:** Where data comes from |
| [Scoring Logic & Scrapers](SCORE_LOGIC_AND_SCRAPERS.md) | Scraper architecture |
| [X Integration](X_INTEGRATION.md) | X/Twitter social scraping |

## Sport-Specific Implementation

Technical references for sport-specific parsing and validation.

### Play-by-Play
| Guide | Description |
|-------|-------------|
| [NBA PBP Patterns](pbp-nba-patterns.md) | NBA parsing patterns for NHL parity |
| [NBA PBP Review](pbp-nba-review.md) | NBA PBP implementation details |
| [NHL PBP](pbp-nhl-hockey-reference.md) | NHL PBP via Hockey Reference |
| [NCAAB PBP](pbp-ncaab-sports-reference.md) | NCAAB PBP via Sports Reference |
| [NHL Overview](nhl-hockey-reference-overview.md) | NHL data source overview |

### Odds
| Guide | Description |
|-------|-------------|
| [NBA/NCAAB Odds](odds-nba-ncaab-review.md) | NBA/NCAAB odds implementation |
| [NHL Odds Validation](odds-nhl-validation.md) | NHL odds validation checklist |

### Social
| Guide | Description |
|-------|-------------|
| [NBA Social](social-nba-review.md) | NBA social implementation |
| [NHL Social](social-nhl.md) | NHL team X handles and validation |

## Operations

| Guide | Description |
|-------|-------------|
| [Operator Runbook](OPERATOR_RUNBOOK.md) | Production operations, backups, monitoring |
| [Deployment](DEPLOYMENT.md) | Server setup, deploy flow, rollbacks |
| [Infrastructure](INFRA.md) | Docker configuration and profiles |
| [Edge Proxy](EDGE_PROXY.md) | Caddy/Nginx routing configuration |
| [Changelog](CHANGELOG.md) | Recent changes and releases |
