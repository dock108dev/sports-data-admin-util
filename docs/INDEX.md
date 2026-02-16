# Documentation Index

## Getting Started

| Guide | Description |
|-------|-------------|
| [Local Development](LOCAL_DEVELOPMENT.md) | **Start here:** Run locally with Docker or manual setup |
| [Project Rules](../CLAUDE.md) | Development principles, coding standards, and AI agent context |
| [Architecture](ARCHITECTURE.md) | System components, data flow, database schema |
| [API Reference](API.md) | FastAPI endpoints and usage |

## External App Integration

| Guide | Description |
|-------|-------------|
| [Game Flow Guide](GAME_FLOW_GUIDE.md) | **Start here:** Compact timeline with blocks and mini box scores |
| [API Reference](API.md) | Full API reference for consuming game data |

## Development

| Guide | Description |
|-------|-------------|
| [Adding New Sports](ADDING_NEW_SPORTS.md) | How to enable a new league |
| [Database Integration](DATABASE_INTEGRATION.md) | Querying the sports database |

## Game Flow Generation

| Guide | Description |
|-------|-------------|
| [Game Flow Contract](GAMEFLOW_CONTRACT.md) | **Authoritative:** Block-based narrative model (4-7 blocks per game) |
| [Game Flow Pipeline](GAMEFLOW_PIPELINE.md) | 8-stage pipeline from PBP to narratives |
| [PBP Game Flow Assumptions](PBP_GAMEFLOW_ASSUMPTIONS.md) | Technical assumptions about PBP data |

## Timeline System

| Guide | Description |
|-------|-------------|
| [Timeline Assembly](TIMELINE_ASSEMBLY.md) | Assembly recipe: PBP + social + odds merged by phase |
| [Timeline Validation](TIMELINE_VALIDATION.md) | Validation rules (C1-C6 critical, W1-W4 warnings) |

## FairBet & EV

| Guide | Description |
|-------|-------------|
| [EV Lifecycle](EV_LIFECYCLE.md) | End-to-end EV computation: ingestion → grouping → eligibility → devig → annotation |
| [EV Infrastructure Review](EV_INFRASTRUCTURE_REVIEW.md) | Codebase review: assumptions, gaps, open questions |

## Data Ingestion

| Guide | Description |
|-------|-------------|
| [Data Sources](DATA_SOURCES.md) | **Start here:** Where data comes from |
| [X Integration](X_INTEGRATION.md) | X/Twitter social scraping |

## Operations

| Guide | Description |
|-------|-------------|
| [Operator Runbook](OPERATOR_RUNBOOK.md) | Production operations and monitoring |
| [Deployment](DEPLOYMENT.md) | Server setup, deploy flow, edge routing, rollbacks |
| [Infrastructure](INFRA.md) | Docker configuration and profiles |
| [Changelog](CHANGELOG.md) | Recent changes and releases |
