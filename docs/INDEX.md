# Documentation Index

## Getting Started

| Guide | Description |
|-------|-------------|
| [Local Development](LOCAL_DEVELOPMENT.md) | **Start here:** Run locally with Docker or manual setup |
| [Coding Standards](../CLAUDE.md) | Development principles and coding standards |
| [AI Agent Context](../AGENTS.md) | Quick context for AI assistants |
| [Architecture](ARCHITECTURE.md) | System components, data flow, database schema |
| [API Reference](API.md) | FastAPI endpoints and usage |

## External App Integration

| Guide | Description |
|-------|-------------|
| [API Integration Guide](API.md#external-app-integration-guide) | **For app developers:** How to consume game data across all sports |

## Development

| Guide | Description |
|-------|-------------|
| [Adding New Sports](ADDING_NEW_SPORTS.md) | How to enable a new league |
| [NHL Implementation Guide](NHL_IMPLEMENTATION_GUIDE.md) | NHL parity reference |
| [Database Integration](DATABASE_INTEGRATION.md) | Querying the sports database |

## Story Generation

| Guide | Description |
|-------|-------------|
| [Story Contract](STORY_CONTRACT.md) | **Authoritative:** Block-based narrative model (4-7 blocks per game) |
| [Story Pipeline](STORY_PIPELINE.md) | 8-stage pipeline from PBP to narratives |
| [PBP Story Assumptions](PBP_STORY_ASSUMPTIONS.md) | Technical assumptions about PBP data |

## Timeline System

| Guide | Description |
|-------|-------------|
| [Narrative Time Model](NARRATIVE_TIME_MODEL.md) | How timeline ordering works |
| [Timeline Assembly](TIMELINE_ASSEMBLY.md) | Timeline generation from PBP and social |
| [Timeline Validation](TIMELINE_VALIDATION.md) | Validation rules and sanity checks |
| [PBP Timestamp Usage](PBP_TIMESTAMP_USAGE.md) | How PBP timestamps are used |
| [Social Event Roles](SOCIAL_EVENT_ROLES.md) | Narrative roles for social posts |

## Data Ingestion

| Guide | Description |
|-------|-------------|
| [Data Sources](DATA_SOURCES.md) | **Start here:** Where data comes from |
| [X Integration](X_INTEGRATION.md) | X/Twitter social scraping |

## Sport-Specific Implementation

### Play-by-Play

| Guide | Description |
|-------|-------------|
| [NBA PBP Review](PBP_NBA_REVIEW.md) | NBA PBP implementation |
| [NCAAB PBP](PBP_NCAAB_SPORTS_REFERENCE.md) | NCAAB PBP via Sports Reference |

> **Note:** NHL PBP uses the official NHL API (`api-web.nhle.com`). See [Data Sources](DATA_SOURCES.md).

### Odds

| Guide | Description |
|-------|-------------|
| [NBA/NCAAB Odds](ODDS_NBA_NCAAB_REVIEW.md) | NBA/NCAAB odds implementation |
| [NHL Odds Validation](ODDS_NHL_VALIDATION.md) | NHL odds validation checklist |

### Social

| Guide | Description |
|-------|-------------|
| [NBA Social](SOCIAL_NBA_REVIEW.md) | NBA social implementation |
| [NHL Social](SOCIAL_NHL.md) | NHL team X handles and validation |

## Operations

| Guide | Description |
|-------|-------------|
| [Operator Runbook](OPERATOR_RUNBOOK.md) | Production operations and monitoring |
| [Deployment](DEPLOYMENT.md) | Server setup, deploy flow, edge routing, rollbacks |
| [Infrastructure](INFRA.md) | Docker configuration and profiles |
| [Changelog](CHANGELOG.md) | Recent changes and releases |
