"""Run manager that orchestrates scraper + odds execution."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Dict, List, Tuple

from sqlalchemy import exists, func, not_
from sqlalchemy.orm import Session

from ..config import settings
from ..db import db_models, get_session
from ..logging import logger
from ..models import IngestionConfig
from ..odds.synchronizer import OddsSynchronizer
from ..persistence import persist_game_payload, upsert_player_boxscores, upsert_plays
from ..scrapers import get_all_scrapers
from ..social import XPostCollector
from ..utils.datetime_utils import utcnow


class ScrapeRunManager:
    def __init__(self) -> None:
        self.scrapers = get_all_scrapers()
        self.odds_sync = OddsSynchronizer()
        self.social_collector = XPostCollector()

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

    def _get_games_for_boxscores(
        self,
        session: Session,
        league_code: str,
        start_date: date,
        end_date: date,
        only_missing: bool = False,
        updated_before: datetime | None = None,
    ) -> List[Tuple[int, str, date]]:
        """Get games for boxscore scraping with filters."""
        league = session.query(db_models.SportsLeague).filter(
            db_models.SportsLeague.code == league_code
        ).first()
        if not league:
            return []

        query = session.query(
            db_models.SportsGame.id,
            db_models.SportsGame.source_game_key,
            db_models.SportsGame.game_date,
        ).filter(
            db_models.SportsGame.league_id == league.id,
            db_models.SportsGame.game_date >= datetime.combine(start_date, datetime.min.time()),
            db_models.SportsGame.game_date <= datetime.combine(end_date, datetime.max.time()),
            db_models.SportsGame.source_game_key.isnot(None),
        )

        if only_missing:
            has_boxscores = exists().where(
                db_models.SportsTeamBoxscore.game_id == db_models.SportsGame.id
            )
            query = query.filter(not_(has_boxscores))

        if updated_before:
            query = query.filter(db_models.SportsGame.updated_at < updated_before)

        results = query.all()
        return [(r.id, r.source_game_key, r.game_date.date() if r.game_date else None) for r in results]

    def _get_games_for_odds(
        self,
        session: Session,
        league_code: str,
        start_date: date,
        end_date: date,
        only_missing: bool = False,
        updated_before: datetime | None = None,
    ) -> List[date]:
        """Get unique dates needing odds fetch."""
        league = session.query(db_models.SportsLeague).filter(
            db_models.SportsLeague.code == league_code
        ).first()
        if not league:
            return []

        query = session.query(
            func.date(db_models.SportsGame.game_date).label("game_day")
        ).filter(
            db_models.SportsGame.league_id == league.id,
            db_models.SportsGame.game_date >= datetime.combine(start_date, datetime.min.time()),
            db_models.SportsGame.game_date <= datetime.combine(end_date, datetime.max.time()),
        ).distinct()

        if only_missing:
            # Games with no odds
            has_odds = exists().where(
                db_models.SportsGameOdds.game_id == db_models.SportsGame.id
            )
            query = query.filter(not_(has_odds))

        # For updated_before on odds, we'd need to track per-game odds updated_at
        # For now, just return all dates in range if not only_missing

        results = query.all()
        return [r.game_day for r in results if r.game_day]

    def _get_games_for_social(
        self,
        session: Session,
        league_code: str,
        start_date: date,
        end_date: date,
        only_missing: bool = False,
        updated_before: datetime | None = None,
    ) -> List[int]:
        """Get game IDs for social scraping with filters."""
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
            has_posts = exists().where(
                db_models.GameSocialPost.game_id == db_models.SportsGame.id
            )
            query = query.filter(not_(has_posts))

        if updated_before:
            # Include games where ALL posts are older than cutoff
            has_fresh = exists().where(
                db_models.GameSocialPost.game_id == db_models.SportsGame.id,
                db_models.GameSocialPost.updated_at >= updated_before,
            )
            query = query.filter(not_(has_fresh))

        return [r[0] for r in query.all()]

    def _get_games_for_pbp(
        self,
        session: Session,
        league_code: str,
        start_date: date,
        end_date: date,
        only_missing: bool = False,
        updated_before: datetime | None = None,
    ) -> List[Tuple[int, str, date]]:
        """Get games for play-by-play scraping with filters."""
        league = session.query(db_models.SportsLeague).filter(
            db_models.SportsLeague.code == league_code
        ).first()
        if not league:
            return []

        query = session.query(
            db_models.SportsGame.id,
            db_models.SportsGame.source_game_key,
            db_models.SportsGame.game_date,
        ).filter(
            db_models.SportsGame.league_id == league.id,
            db_models.SportsGame.game_date >= datetime.combine(start_date, datetime.min.time()),
            db_models.SportsGame.game_date <= datetime.combine(end_date, datetime.max.time()),
            db_models.SportsGame.source_game_key.isnot(None),
        )

        if only_missing:
            has_pbp = exists().where(
                db_models.SportsGamePlay.game_id == db_models.SportsGame.id
            )
            query = query.filter(not_(has_pbp))

        if updated_before:
            # Include games where ALL plays are older than cutoff
            has_fresh = exists().where(
                db_models.SportsGamePlay.game_id == db_models.SportsGame.id,
                db_models.SportsGamePlay.updated_at >= updated_before,
            )
            query = query.filter(not_(has_fresh))

        results = query.all()
        return [(r.id, r.source_game_key, r.game_date.date() if r.game_date else None) for r in results]

    def run(self, run_id: int, config: IngestionConfig) -> dict:
        summary: Dict[str, int | str] = {
            "games": 0,
            "games_created": 0,
            "games_updated": 0,
            "odds": 0,
            "social_posts": 0,
            "pbp_games": 0,
        }
        start = config.start_date or date.today()
        end = config.end_date or start
        scraper = self.scrapers.get(config.league_code)

        # Convert updated_before date to datetime if provided
        updated_before_dt = (
            datetime.combine(config.updated_before, datetime.min.time()).replace(tzinfo=timezone.utc)
            if config.updated_before
            else None
        )

        logger.info(
            "scrape_run_config",
            run_id=run_id,
            league=config.league_code,
            boxscores=config.boxscores,
            odds=config.odds,
            social=config.social,
            pbp=config.pbp,
            only_missing=config.only_missing,
            updated_before=str(config.updated_before) if config.updated_before else None,
            start_date=str(start),
            end_date=str(end),
        )

        if not scraper and (config.boxscores or config.pbp):
            raise RuntimeError(f"No scraper implemented for {config.league_code}")

        self._update_run(run_id, status="running", started_at=utcnow())

        try:
            # Boxscore scraping
            if config.boxscores and scraper:
                logger.info(
                    "boxscore_scraping_start",
                    run_id=run_id,
                    league=config.league_code,
                    start_date=str(start),
                    end_date=str(end),
                    only_missing=config.only_missing,
                )

                if config.only_missing or updated_before_dt:
                    # Filter games by criteria
                    with get_session() as session:
                        games_to_scrape = self._get_games_for_boxscores(
                            session, config.league_code, start, end,
                            only_missing=config.only_missing,
                            updated_before=updated_before_dt,
                        )
                    logger.info("found_games_for_boxscores", count=len(games_to_scrape), run_id=run_id)

                    for game_id, source_key, game_date in games_to_scrape:
                        if not source_key or not game_date:
                            continue
                        try:
                            game_payload = scraper.fetch_single_boxscore(source_key, game_date)
                            if game_payload:
                                with get_session() as session:
                                    result = persist_game_payload(session, game_payload)
                                    session.commit()
                                    if result.created:
                                        summary["games_created"] += 1
                                    else:
                                        summary["games_updated"] += 1
                                    summary["games"] += 1
                        except Exception as exc:
                            logger.warning("boxscore_scrape_failed", game_id=game_id, error=str(exc))
                else:
                    # Scrape all games in date range
                    for game_payload in scraper.fetch_date_range(start, end):
                        try:
                            if not game_payload.identity.source_game_key:
                                logger.warning(
                                    "game_normalization_missing_external_id",
                                    league=config.league_code,
                                    game_date=str(game_payload.identity.game_date),
                                )
                                continue
                            with get_session() as session:
                                result = persist_game_payload(session, game_payload)
                                session.commit()
                                if result.created:
                                    summary["games_created"] += 1
                                else:
                                    summary["games_updated"] += 1
                                summary["games"] += 1
                        except Exception as exc:
                            logger.exception("game_persist_failed", error=str(exc), run_id=run_id)

                logger.info(
                    "boxscores_complete",
                    count=summary["games"],
                    created=summary["games_created"],
                    updated=summary["games_updated"],
                    run_id=run_id,
                )

            # Odds scraping
            if config.odds:
                logger.info(
                    "odds_scraping_start",
                    run_id=run_id,
                    league=config.league_code,
                    start_date=str(start),
                    end_date=str(end),
                    only_missing=config.only_missing,
                )

                if config.only_missing:
                    with get_session() as session:
                        dates_to_fetch = self._get_games_for_odds(
                            session, config.league_code, start, end,
                            only_missing=True,
                        )
                    for fetch_date in dates_to_fetch:
                        try:
                            odds_count = self.odds_sync.sync_single_date(config.league_code, fetch_date)
                            summary["odds"] += odds_count
                        except Exception as e:
                            logger.warning("odds_fetch_failed", date=str(fetch_date), error=str(e))
                else:
                    summary["odds"] = self.odds_sync.sync(config)

                logger.info("odds_complete", count=summary["odds"], run_id=run_id)

            # Social scraping
            if config.social:
                logger.info(
                    "social_scraping_start",
                    run_id=run_id,
                    league=config.league_code,
                    start_date=str(start),
                    end_date=str(end),
                    only_missing=config.only_missing,
                    updated_before=str(updated_before_dt) if updated_before_dt else None,
                )

                with get_session() as session:
                    game_ids = self._get_games_for_social(
                        session, config.league_code, start, end,
                        only_missing=config.only_missing,
                        updated_before=updated_before_dt,
                    )
                logger.info("found_games_for_social", count=len(game_ids), run_id=run_id)

                for game_id in game_ids:
                    try:
                        with get_session() as session:
                            results = self.social_collector.collect_for_game(session, game_id)
                            for result in results:
                                summary["social_posts"] += result.posts_saved
                    except Exception as e:
                        logger.warning("social_collection_failed", game_id=game_id, error=str(e))

                logger.info("social_complete", count=summary["social_posts"], run_id=run_id)

            # Play-by-play scraping
            if config.pbp and scraper:
                logger.info(
                    "pbp_scraping_start",
                    run_id=run_id,
                    league=config.league_code,
                    start_date=str(start),
                    end_date=str(end),
                    only_missing=config.only_missing,
                )

                with get_session() as session:
                    games_for_pbp = self._get_games_for_pbp(
                        session, config.league_code, start, end,
                        only_missing=config.only_missing,
                        updated_before=updated_before_dt,
                    )
                logger.info("found_games_for_pbp", count=len(games_for_pbp), run_id=run_id)

                for game_id, source_key, game_date in games_for_pbp:
                    if not source_key or not game_date:
                        continue
                    try:
                        pbp_payload = scraper.fetch_play_by_play(source_key, game_date)
                        if pbp_payload and pbp_payload.plays:
                            with get_session() as session:
                                upsert_plays(session, game_id, pbp_payload.plays)
                                session.commit()
                                summary["pbp_games"] += 1
                    except Exception as e:
                        logger.warning("pbp_scrape_failed", game_id=game_id, error=str(e))

                logger.info("pbp_complete", count=summary["pbp_games"], run_id=run_id)

            # Build summary string
            summary_parts = []
            if summary["games"]:
                summary_parts.append(
                    f'Games: {summary["games"]} (created {summary["games_created"]}, updated {summary["games_updated"]})'
                )
            if summary["odds"]:
                summary_parts.append(f'Odds: {summary["odds"]}')
            if summary["social_posts"]:
                summary_parts.append(f'Social: {summary["social_posts"]}')
            if summary["pbp_games"]:
                summary_parts.append(f'PBP: {summary["pbp_games"]}')

            self._update_run(
                run_id,
                status="success",
                finished_at=utcnow(),
                summary=", ".join(summary_parts) or "No data processed",
            )
            logger.info("scrape_run_complete", run_id=run_id, summary=summary)

        except Exception as exc:
            logger.exception("scrape_run_failed", run_id=run_id, error=str(exc))
            self._update_run(
                run_id,
                status="error",
                finished_at=utcnow(),
                error_details=str(exc),
            )
            raise

        return summary
