# sports-data-admin

Backend infrastructure for Scroll Down Sports: API, data scraper, and admin UI.

## Purpose

This repo provides the admin-side pipeline that normalizes sports data, persists
it in predictable schemas, and surfaces it to downstream apps and the admin UI.

## What this repo is

This repository hosts the FastAPI admin API, scraper workers, and the React admin UI used to manage sports data ingestion for Scroll Down Sports.

## Run locally

Use Docker for the full stack, or run services individually. See [docs/LOCAL_DEVELOPMENT.md](docs/LOCAL_DEVELOPMENT.md) for full instructions.

## Deployment basics

Docker compose configurations live in [`infra/`](infra/). Start from `infra/.env.example` and deploy via the infra README or runbook guidance in [docs/INFRA.md](docs/INFRA.md).

## More documentation

Start with [docs/INDEX.md](docs/INDEX.md) for detailed guides, runbooks, and integration notes.
See [Scoring Logic & Scraper Integration](docs/SCORE_LOGIC_AND_SCRAPERS.md) for score handling, stubbing expectations, and adding new scrapers.
