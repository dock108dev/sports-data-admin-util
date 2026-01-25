"""Shared ingestion entry points for manual and scheduled scraping runs."""

from __future__ import annotations

from ..models import IngestionConfig
from ..services.run_manager import ScrapeRunManager


def run_ingestion(run_id: int, config_payload: dict) -> dict:
    """Single ingestion entry point shared by UI-triggered and scheduled runs."""
    config = IngestionConfig(**config_payload)
    manager = ScrapeRunManager()
    # All ingestion paths (manual + scheduler) flow through this call for idempotent upserts.
    return manager.run(run_id, config)
