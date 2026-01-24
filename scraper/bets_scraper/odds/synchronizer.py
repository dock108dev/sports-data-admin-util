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
from ..utils.datetime_utils import today_utc
from .client import OddsAPIClient


class OddsSynchronizer:
    def __init__(self) -> None:
        self.client = OddsAPIClient()

    def sync(self, config: IngestionConfig) -> int:
        """Sync odds for the configured date range.

        Automatically uses historical API for past dates and live API for today/future.
        """
        if not config.odds:
            logger.debug("odds_sync_skipped", league=config.league_code, reason="odds_disabled")
            return 0

        start = config.start_date or today_utc()
        end = config.end_date or start
        today = today_utc()

        logger.info(
            "odds_sync_start",
            league=config.league_code,
            start_date=str(start),
            end_date=str(end),
            today=str(today),
            days_in_range=(end - start).days + 1,
        )

        # Determine which API to use based on date range
        if end < today:
            # All dates are historical - use historical endpoint
            logger.info(
                "odds_endpoint_routing",
                league=config.league_code,
                endpoint="historical_only",
                reason="all_dates_in_past",
            )
            return self._sync_historical(config.league_code, start, end, config.include_books)
        elif start >= today:
            # All dates are current/future - use live endpoint
            logger.info(
                "odds_endpoint_routing",
                league=config.league_code,
                endpoint="live_only",
                reason="all_dates_today_or_future",
            )
            return self._sync_live(config.league_code, start, end, config.include_books)
        else:
            # Mixed range - split between historical and live
            logger.info(
                "odds_endpoint_routing",
                league=config.league_code,
                endpoint="mixed",
                reason="date_range_spans_past_and_future",
                historical_range=f"{start} to {today - timedelta(days=1)}",
                live_range=f"{today} to {end}",
            )
            historical_count = self._sync_historical(
                config.league_code, start, today - timedelta(days=1), config.include_books
            )
            live_count = self._sync_live(
                config.league_code, today, end, config.include_books
            )
            total = historical_count + live_count
            logger.info(
                "odds_sync_complete_mixed",
                league=config.league_code,
                historical_inserted=historical_count,
                live_inserted=live_count,
                total_inserted=total,
            )
            return total

    def _sync_live(
        self,
        league_code: str,
        start: date,
        end: date,
        books: list[str] | None,
    ) -> int:
        """Sync odds using the live API endpoint (for today/future games)."""
        logger.info(
            "live_odds_fetch_start",
            league=league_code,
            endpoint="/sports/{sport}/odds",
            start=str(start),
            end=str(end),
        )
        snapshots = self.client.fetch_mainlines(league_code, start, end, books)
        logger.info(
            "live_odds_fetched",
            league=league_code,
            snapshots_count=len(snapshots),
            start=str(start),
            end=str(end),
        )

        if not snapshots:
            logger.info(
                "no_live_odds",
                league=league_code,
                start=str(start),
                end=str(end),
                message="No upcoming games found in date range",
            )
            return 0

        inserted = self._persist_snapshots(snapshots, league_code)
        logger.info(
            "live_odds_sync_complete",
            league=league_code,
            snapshots_fetched=len(snapshots),
            odds_persisted=inserted,
        )
        return inserted

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
        today = today_utc()
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
        games_created = 0

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
                        league=league_code,
                        error=str(exc),
                        game_date=str(snapshot.game_date),
                        home_team=snapshot.home_team.name,
                        away_team=snapshot.away_team.name,
                        exc_info=True,
                    )
                    skipped += 1
            session.commit()

        logger.info(
            "odds_persist_summary",
            league=league_code,
            total_snapshots=len(snapshots),
            odds_inserted=inserted,
            odds_skipped=skipped,
            success_rate=f"{inserted}/{len(snapshots)}" if snapshots else "N/A",
        )

        if skipped > 0:
            logger.warning(
                "odds_persist_had_skips",
                league=league_code,
                inserted=inserted,
                skipped=skipped,
                message="Some odds could not be matched to games",
            )

        return inserted


