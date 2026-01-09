"""Odds synchronization utilities.

Supports both live odds (upcoming games) and historical odds (past games).
Automatically routes to the appropriate API endpoint based on date range.
"""

from __future__ import annotations

import time
from datetime import date, timedelta

from ..db import get_session
from ..logging import logger
from ..models import IngestionConfig
from ..persistence import upsert_odds
from .client import OddsAPIClient


class OddsSynchronizer:
    def __init__(self) -> None:
        self.client = OddsAPIClient()

    def sync(self, config: IngestionConfig) -> int:
        """Sync odds for the configured date range.
        
        Automatically uses historical API for past dates and live API for today/future.
        """
        # Beta config uses boolean toggles (odds/boxscores/social/pbp). Older code
        # referenced include_odds; keep this strict and explicit.
        if not config.odds:
            return 0
            
        start = config.start_date or date.today()
        end = config.end_date or start
        today = date.today()

        # Determine which API to use based on date range
        if end < today:
            # All dates are historical - use historical endpoint
            return self._sync_historical(config.league_code, start, end, config.include_books)
        elif start >= today:
            # All dates are current/future - use live endpoint
            return self._sync_live(config.league_code, start, end, config.include_books)
        else:
            # Mixed range - split between historical and live
            historical_count = self._sync_historical(
                config.league_code, start, today - timedelta(days=1), config.include_books
            )
            live_count = self._sync_live(
                config.league_code, today, end, config.include_books
            )
            return historical_count + live_count

    def _sync_live(
        self,
        league_code: str,
        start: date,
        end: date,
        books: list[str] | None,
    ) -> int:
        """Sync odds using the live API endpoint (for today/future games)."""
        snapshots = self.client.fetch_mainlines(league_code, start, end, books)
        logger.info("live_odds_fetched", league=league_code, count=len(snapshots))
        
        if not snapshots:
            logger.info("no_live_odds", league=league_code, start=str(start), end=str(end))
            return 0

        return self._persist_snapshots(snapshots, league_code)

    def _sync_historical(
        self,
        league_code: str,
        start: date,
        end: date,
        books: list[str] | None,
    ) -> int:
        """Sync odds using the historical API endpoint (for past games).
        
        Iterates day by day to fetch historical snapshots.
        Cost: ~30 credits per day (3 markets x 1 region).
        """
        total_inserted = 0
        current = start
        days_processed = 0
        
        logger.info(
            "starting_historical_odds_sync",
            league=league_code,
            start=str(start),
            end=str(end),
            total_days=(end - start).days + 1,
        )

        while current <= end:
            snapshots = self.client.fetch_historical_odds(league_code, current, books)
            
            if snapshots:
                inserted = self._persist_snapshots(snapshots, league_code)
                total_inserted += inserted
                logger.info(
                    "historical_day_complete",
                    league=league_code,
                    date=str(current),
                    inserted=inserted,
                )
            
            current += timedelta(days=1)
            days_processed += 1
            
            # Small delay between API calls to avoid rate limiting (every 5 days)
            if days_processed % 5 == 0 and current <= end:
                time.sleep(1)

        logger.info(
            "historical_odds_sync_complete",
            league=league_code,
            days_processed=days_processed,
            total_inserted=total_inserted,
        )
        return total_inserted

    def sync_single_date(
        self,
        league_code: str,
        game_date: date,
        books: list[str] | None = None,
    ) -> int:
        """Sync odds for a single date. Used for backfilling missing odds.
        
        Automatically chooses historical vs live API based on whether date is past or present.
        """
        today = date.today()
        logger.info("sync_single_date_start", league=league_code, date=str(game_date))

        if game_date < today:
            # Historical date
            snapshots = self.client.fetch_historical_odds(league_code, game_date, books)
        else:
            # Today or future
            snapshots = self.client.fetch_mainlines(league_code, game_date, game_date, books)

        if not snapshots:
            logger.info("no_odds_for_single_date", league=league_code, date=str(game_date))
            return 0

        inserted = self._persist_snapshots(snapshots, league_code)
        logger.info(
            "sync_single_date_complete",
            league=league_code,
            date=str(game_date),
            inserted=inserted,
        )
        return inserted

    def _persist_snapshots(
        self,
        snapshots: list,
        league_code: str,
    ) -> int:
        """Persist odds snapshots to database."""
        inserted = 0
        skipped = 0
        
        with get_session() as session:
            for snapshot in snapshots:
                try:
                    if upsert_odds(session, snapshot):
                        inserted += 1
                    else:
                        skipped += 1
                except Exception as exc:
                    session.rollback()
                    logger.warning(
                        "odds_upsert_failed",
                        error=str(exc),
                        game_date=str(snapshot.game_date),
                        exc_info=True,
                    )
                    skipped += 1
            session.commit()

        if skipped > 0:
            logger.warning(
                "odds_persist_skipped",
                league=league_code,
                inserted=inserted,
                skipped=skipped,
            )
        
        return inserted


