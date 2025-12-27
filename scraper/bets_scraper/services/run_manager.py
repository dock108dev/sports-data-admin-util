"""Run manager that orchestrates scraper + odds execution."""

from __future__ import annotations

from datetime import date, datetime
from typing import Dict, List, Tuple

from sqlalchemy import exists, not_, or_
from sqlalchemy.orm import Session

from ..config import settings
from ..db import db_models, get_session
from ..logging import logger
from ..models import IngestionConfig
from ..odds.synchronizer import OddsSynchronizer
from ..persistence import persist_game_payload, upsert_player_boxscores
from ..scrapers import get_all_scrapers
from ..social import XPostCollector
from ..utils.datetime_utils import utcnow


class ScrapeRunManager:
    def __init__(self) -> None:
        # Use scraper registry instead of hardcoding all imports
        self.scrapers = get_all_scrapers()
        self.odds_sync = OddsSynchronizer()
        self.social_collector = XPostCollector()

    def _get_incomplete_games(
        self,
        session: Session,
        league_code: str,
        start_date: date,
        end_date: date,
        missing_players: bool = False,
        missing_odds: bool = False,
    ) -> List[Tuple[int, str, date]]:
        """Return list of (game_id, source_game_key, game_date) for incomplete games.
        
        Finds games that are missing player boxscores and/or odds data.
        """
        # Get league ID
        league = session.query(db_models.SportsLeague).filter(
            db_models.SportsLeague.code == league_code
        ).first()
        if not league:
            logger.warning("league_not_found_for_backfill", league=league_code)
            return []

        # Build base query
        query = session.query(
            db_models.SportsGame.id,
            db_models.SportsGame.source_game_key,
            db_models.SportsGame.game_date,
        ).filter(
            db_models.SportsGame.league_id == league.id,
            db_models.SportsGame.game_date >= datetime.combine(start_date, datetime.min.time()),
            db_models.SportsGame.game_date <= datetime.combine(end_date, datetime.max.time()),
            db_models.SportsGame.source_game_key.isnot(None),  # Need source key for re-scraping
        )

        # Build filter conditions
        conditions = []
        if missing_players:
            has_players = exists().where(
                db_models.SportsPlayerBoxscore.game_id == db_models.SportsGame.id
            )
            conditions.append(not_(has_players))
        if missing_odds:
            has_odds = exists().where(
                db_models.SportsGameOdds.game_id == db_models.SportsGame.id
            )
            conditions.append(not_(has_odds))

        if conditions:
            query = query.filter(or_(*conditions))

        results = query.all()
        logger.info(
            "incomplete_games_query",
            league=league_code,
            start=str(start_date),
            end=str(end_date),
            missing_players=missing_players,
            missing_odds=missing_odds,
            found_count=len(results),
        )
        return [(r.id, r.source_game_key, r.game_date.date() if r.game_date else None) for r in results]

    def _update_run(self, run_id: int, **updates) -> None:
        try:
            with get_session() as session:
                run = session.query(db_models.SportsScrapeRun).filter(db_models.SportsScrapeRun.id == run_id).first()
                if not run:
                    all_runs = session.query(db_models.SportsScrapeRun.id, db_models.SportsScrapeRun.status).limit(5).all()
                    logger.error(
                        "scrape_run_not_found",
                        run_id=run_id,
                        database_url=settings.database_url[:50] + "...",
                        existing_runs=[r.id for r in all_runs]
                    )
                    return
                for key, value in updates.items():
                    setattr(run, key, value)
                session.flush()
                session.commit()
                logger.info("scrape_run_updated", run_id=run_id, updates=list(updates.keys()), new_status=updates.get("status"))
        except Exception as exc:
            logger.exception("failed_to_update_run", run_id=run_id, error=str(exc), exc_info=True)
            raise

    def _get_games_for_social(
        self,
        session: Session,
        league_code: str,
        start_date: date,
        end_date: date,
        only_missing: bool = False,
    ) -> List[int]:
        """Get game IDs for social scraping."""
        league = session.query(db_models.SportsLeague).filter(
            db_models.SportsLeague.code == league_code
        ).first()
        if not league:
            return []

        query = session.query(db_models.SportsGame.id).filter(
            db_models.SportsGame.league_id == league.id,
            db_models.SportsGame.game_date >= datetime.combine(start_date, datetime.min.time()),
            db_models.SportsGame.game_date <= datetime.combine(end_date, datetime.max.time()),
        )

        if only_missing:
            # Only games without any social posts
            has_posts = exists().where(
                db_models.GameSocialPost.game_id == db_models.SportsGame.id
            )
            query = query.filter(not_(has_posts))

        return [r[0] for r in query.all()]

    def run(self, run_id: int, config: IngestionConfig) -> dict:
        summary: Dict[str, int | str] = {
            "games": 0,
            "odds": 0,
            "backfilled_players": 0,
            "backfilled_odds": 0,
            "social_posts": 0,
        }
        start = config.start_date or date.today()
        end = config.end_date or start
        scraper = self.scrapers.get(config.league_code)
        
        # Log configuration for debugging
        logger.info(
            "scrape_run_config",
            run_id=run_id,
            league=config.league_code,
            include_boxscores=config.include_boxscores,
            include_odds=config.include_odds,
            scraper_found=scraper is not None,
            start_date=str(start),
            end_date=str(end),
        )
        
        if not scraper and (config.include_boxscores or config.backfill_player_stats):
            raise RuntimeError(f"No scraper implemented for {config.league_code}")

        self._update_run(run_id, status="running", started_at=utcnow())

        try:
            # Standard boxscore scraping
            if config.include_boxscores and scraper:
                logger.info(
                    "boxscore_scraping_start",
                    run_id=run_id,
                    league=config.league_code,
                    start_date=str(start),
                    end_date=str(end),
                )
                game_count = 0
                for game_payload in scraper.fetch_date_range(start, end):
                    try:
                        with get_session() as session:
                            persist_game_payload(session, game_payload)
                            session.commit()
                            game_count += 1
                            summary["games"] += 1
                    except Exception as exc:
                        logger.exception("game_persist_failed", error=str(exc), game_date=game_payload.identity.game_date, run_id=run_id)
                        continue
                logger.info("games_persisted", count=game_count, run_id=run_id, league=config.league_code)
            elif config.include_boxscores and not scraper:
                logger.warning("boxscore_scraping_skipped_no_scraper", run_id=run_id, league=config.league_code)

            # Standard odds scraping
            if config.include_odds:
                summary["odds"] = self.odds_sync.sync(config)

            # Backfill player stats for games missing them
            if config.backfill_player_stats and scraper:
                logger.info("starting_player_backfill", run_id=run_id, league=config.league_code, start=str(start), end=str(end))
                with get_session() as session:
                    incomplete = self._get_incomplete_games(
                        session, config.league_code, start, end,
                        missing_players=True, missing_odds=False
                    )
                logger.info("found_games_missing_players", count=len(incomplete), run_id=run_id)

                for game_id, source_key, game_date in incomplete:
                    if not source_key or not game_date:
                        logger.debug("skipping_game_no_source_key", game_id=game_id)
                        continue
                    logger.debug("backfilling_player_stats", game_id=game_id, source_key=source_key, game_date=str(game_date))
                    try:
                        game_payload = scraper.fetch_single_boxscore(source_key, game_date)
                        if game_payload and game_payload.player_boxscores:
                            with get_session() as session:
                                upsert_player_boxscores(session, game_id, game_payload.player_boxscores)
                                session.commit()
                                summary["backfilled_players"] += len(game_payload.player_boxscores)
                                logger.info(
                                    "player_backfill_success",
                                    game_id=game_id,
                                    source_key=source_key,
                                    players=len(game_payload.player_boxscores),
                                )
                        else:
                            logger.warning("player_backfill_no_data", game_id=game_id, source_key=source_key)
                    except Exception as e:
                        logger.warning("player_backfill_failed", game_id=game_id, source_key=source_key, error=str(e))

            # Backfill odds for games missing them
            if config.backfill_odds:
                logger.info("starting_odds_backfill", run_id=run_id, league=config.league_code, start=str(start), end=str(end))
                with get_session() as session:
                    incomplete = self._get_incomplete_games(
                        session, config.league_code, start, end,
                        missing_players=False, missing_odds=True
                    )
                logger.info("found_games_missing_odds", count=len(incomplete), run_id=run_id)

                # Group by date to minimize API calls
                dates_to_fetch = sorted(set(g[2] for g in incomplete if g[2]))
                for fetch_date in dates_to_fetch:
                    logger.debug("backfilling_odds_for_date", date=str(fetch_date), league=config.league_code)
                    try:
                        odds_count = self.odds_sync.sync_single_date(config.league_code, fetch_date)
                        summary["backfilled_odds"] += odds_count
                        logger.info("odds_backfill_date_complete", date=str(fetch_date), odds_inserted=odds_count)
                    except Exception as e:
                        logger.warning("odds_backfill_date_failed", date=str(fetch_date), error=str(e))

            # Social post scraping
            if config.include_social or config.backfill_social:
                logger.info(
                    "starting_social_scraping",
                    run_id=run_id,
                    league=config.league_code,
                    start=str(start),
                    end=str(end),
                    skip_existing=True,  # Always skip games with existing posts
                )
                with get_session() as session:
                    # Always skip games that already have social posts
                    # (no need to re-scrape - social posts don't change)
                    game_ids = self._get_games_for_social(
                        session,
                        config.league_code,
                        start,
                        end,
                        only_missing=True,  # Always skip games with existing posts
                    )
                logger.info("found_games_for_social", count=len(game_ids), run_id=run_id)

                for game_id in game_ids:
                    try:
                        with get_session() as session:
                            results = self.social_collector.collect_for_game(
                                session,
                                game_id,
                            )
                            # Note: commits happen inside run_job for each team
                            # so posts are persisted immediately after collection
                            for result in results:
                                summary["social_posts"] += result.posts_saved
                    except Exception as e:
                        logger.warning(
                            "social_collection_failed",
                            game_id=game_id,
                            error=str(e),
                        )

            # Build summary string
            summary_parts = [f'Games: {summary["games"]}', f'Odds: {summary["odds"]}']
            if summary["backfilled_players"]:
                summary_parts.append(f'Backfilled players: {summary["backfilled_players"]}')
            if summary["backfilled_odds"]:
                summary_parts.append(f'Backfilled odds: {summary["backfilled_odds"]}')
            if summary["social_posts"]:
                summary_parts.append(f'Social posts: {summary["social_posts"]}')

            self._update_run(
                run_id,
                status="success",
                finished_at=utcnow(),
                summary=", ".join(summary_parts),
            )
            logger.info("scrape_run_complete", run_id=run_id, summary=summary)
        except Exception as exc:  # pragma: no cover
            logger.exception("scrape_run_failed", run_id=run_id, error=str(exc))
            self._update_run(
                run_id,
                status="error",
                finished_at=utcnow(),
                error_details=str(exc),
            )
            raise

        return summary


