# Documentation Index

## Getting Started

| Guide | Description |
|-------|-------------|
| [Platform Overview](PLATFORM_OVERVIEW.md) | What this platform does, key features, API endpoints |
| [Local Development](LOCAL_DEVELOPMENT.md) | How to run the stack locally |
| [Infrastructure](INFRA.md) | Docker configuration, deployment, profiles |

## Timeline System

| Guide | Description |
|-------|-------------|
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
| [Database Integration](DATABASE_INTEGRATION.md) | How to query the sports database |
| [Scoring Logic & Scrapers](SCORE_LOGIC_AND_SCRAPERS.md) | How data ingestion works |
| [X Integration](X_INTEGRATION.md) | Social media scraping from X/Twitter |
| [API Reference](API.md) | FastAPI endpoints and usage |

## Sport-Specific References

| Guide | Description |
|-------|-------------|
| [PBP: NBA Patterns](pbp-nba-patterns.md) | NBA play-by-play parsing patterns |
| [PBP: NBA Review](pbp-nba-review.md) | NBA PBP data audit |
| [PBP: NHL Hockey Reference](pbp-nhl-hockey-reference.md) | NHL PBP source details |
| [PBP: NCAAB Sports Reference](pbp-ncaab-sports-reference.md) | NCAAB PBP source details |
| [NHL Overview](nhl-hockey-reference-overview.md) | NHL data source overview |
| [Odds: NBA/NCAAB Review](odds-nba-ncaab-review.md) | Odds data validation for NBA/NCAAB |
| [Odds: NHL Validation](odds-nhl-validation.md) | NHL odds validation |
| [Social: NBA Review](social-nba-review.md) | NBA X/Twitter social audit |
| [Social: NHL](social-nhl.md) | NHL social account scope |

## Operations

| Guide | Description |
|-------|-------------|
| [Operator Runbook](OPERATOR_RUNBOOK.md) | Production operations, backups, monitoring |
| [Deployment](DEPLOYMENT.md) | Production deploy flow, environment variables, rollbacks |
| [Deployment Setup](DEPLOYMENT_SETUP.md) | Initial server setup checklist |
| [Edge Proxy](EDGE_PROXY.md) | Route `/api/*` to FastAPI and `/` to Next.js |
| [Feature Flags](feature-flags.md) | Environment toggles and behavior switches |
| [Changelog](CHANGELOG.md) | Recent changes and releases |

## Development

| Guide | Description |
|-------|-------------|
| [Development History](DEVELOPMENT_HISTORY.md) | Summary of beta phases 0-5 |
| [Codex Task Rules](CODEX_TASK_RULES.md) | How to define tasks for AI agents |
