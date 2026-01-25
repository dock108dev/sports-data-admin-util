# Documentation Index

## Getting Started

| Guide | Description |
|-------|-------------|
| [Local Development](LOCAL_DEVELOPMENT.md) | **Start here:** Run locally with Docker or manual setup |
| [Coding Standards](../CLAUDE.md) | Development principles and coding standards |
| [Architecture](ARCHITECTURE.md) | System components, data flow, database schema |
| [API Reference](API.md) | FastAPI endpoints and usage |

## Development

| Guide | Description |
|-------|-------------|
| [Adding New Sports](ADDING_NEW_SPORTS.md) | How to enable a new league |
| [NHL Implementation Guide](NHL_IMPLEMENTATION_GUIDE.md) | **Comprehensive NHL parity reference** |
| [Database Integration](DATABASE_INTEGRATION.md) | Querying the sports database |

## Story Generation System

The core product: turning play-by-play into narrative chapters and stories.

| Guide | Description |
|-------|-------------|
| [Book + Chapters Model](BOOK_CHAPTERS_MODEL.md) | **Start here:** Core architecture — chapters, sections, rendering |
| [Technical Flow](TECHNICAL_FLOW.md) | Complete pipeline from PBP to story |
| [Story Rendering](SUMMARY_GENERATION.md) | Single AI call architecture, prompt rules, validation |
| [AI Signals (NBA v1)](AI_SIGNALS_NBA_V1.md) | Exact signals exposed to AI |
| [NBA v1 Boundary Rules](NBA_V1_BOUNDARY_RULES.md) | Chapter boundary rules for NBA |
| [Admin UI Guide](ADMIN_UI_STORY_GENERATOR.md) | Story Generator admin interface |
| [Narrative Time Model](NARRATIVE_TIME_MODEL.md) | How timeline ordering works (narrative vs wall-clock) |
| [Timeline Assembly](TIMELINE_ASSEMBLY.md) | Timeline generation details |
| [Timeline Validation](TIMELINE_VALIDATION.md) | Validation rules and sanity checks |
| [PBP Timestamp Usage](PBP_TIMESTAMP_USAGE.md) | How PBP timestamps are used |
| [Social Event Roles](SOCIAL_EVENT_ROLES.md) | Narrative roles for social posts |

## Data Ingestion

| Guide | Description |
|-------|-------------|
| [Data Sources](DATA_SOURCES.md) | **Start here:** Where data comes from |
| [X Integration](X_INTEGRATION.md) | X/Twitter social scraping |

## Sport-Specific Implementation

Technical references for sport-specific parsing and validation.

### Play-by-Play

| Guide | Description |
|-------|-------------|
| [NBA PBP Review](pbp-nba-review.md) | NBA PBP implementation and parity patterns |
| [NHL PBP](pbp-nhl-hockey-reference.md) | NHL PBP via Hockey Reference |
| [NCAAB PBP](pbp-ncaab-sports-reference.md) | NCAAB PBP via Sports Reference |

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
| [Operator Runbook](OPERATOR_RUNBOOK.md) | Production operations and monitoring |
| [Deployment](DEPLOYMENT.md) | Server setup, deploy flow, rollbacks |
| [Infrastructure](INFRA.md) | Docker configuration and profiles |
| [Edge Proxy](EDGE_PROXY.md) | Caddy/Nginx routing configuration |
| [Changelog](CHANGELOG.md) | Recent changes and releases |
