"""Run manager that orchestrates scraper + odds execution."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Dict

from ..config import settings
from ..db import db_models, get_session
from ..logging import logger
from ..models import IngestionConfig
from ..live import LiveFeedManager
from ..odds.synchronizer import OddsSynchronizer
from ..persistence import persist_game_payload, upsert_player_season_stats, upsert_team_season_stats
from ..season_stats import NHLHockeyReferenceSeasonStatsScraper
from ..scrapers import get_all_scrapers
from ..social import XPostCollector
from ..utils.date_utils import season_from_date
from ..utils.datetime_utils import now_utc
from .diagnostics import detect_external_id_conflicts, detect_missing_pbp
from .job_runs import complete_job_run, start_job_run
from .run_manager_helpers import (
    ingest_pbp_via_sportsref,
    select_games_for_boxscores,
    select_games_for_odds,
    select_games_for_social,
)


class ScrapeRunManager:
    def __init__(self) -> None:
        self.scrapers = get_all_scrapers()
        self.odds_sync = OddsSynchronizer()
        self.social_collector = XPostCollector()
        self.live_feed_manager = LiveFeedManager()

        # Feature support varies by league. When a toggle is enabled for an unsupported
        # league, we must NOT fail the run; we log and continue.
        self._supported_social_leagues = ("NBA", "NHL")
        self._supported_live_pbp_leagues = ("NBA", "NHL")

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

    def run(self, run_id: int, config: IngestionConfig) -> dict:
        summary: Dict[str, int | str] = {
            "games": 0,
            "games_created": 0,
            "games_updated": 0,
            "odds": 0,
            "social_posts": 0,
            "pbp_games": 0,
            "team_stats": 0,
            "player_stats": 0,
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

        if not scraper and config.boxscores:
            raise RuntimeError(f"No scraper implemented for {config.league_code}")

        self._update_run(run_id, status="running", started_at=now_utc())

        ingest_run_id: int | None = None
        ingest_run_completed = False
        try:
            if config.boxscores or config.odds:
                ingest_run_id = start_job_run("ingest", [config.league_code])

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
                        games_to_scrape = select_games_for_boxscores(
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

            if config.team_stats or config.player_stats:
                if config.league_code != "NHL":
                    logger.info(
                        "season_stats_not_supported",
                        run_id=run_id,
                        league=config.league_code,
                        message="Season stats scraping is only implemented for NHL.",
                    )
                else:
                    season = config.season or season_from_date(start, config.league_code)
                    stats_scraper = NHLHockeyReferenceSeasonStatsScraper()
                    logger.info(
                        "season_stats_scraping_start",
                        run_id=run_id,
                        league=config.league_code,
                        season=season,
                        team_stats=config.team_stats,
                        player_stats=config.player_stats,
                    )
                    if config.team_stats:
                        team_payloads = stats_scraper.fetch_team_stats(season)
                        with get_session() as session:
                            summary["team_stats"] += upsert_team_season_stats(session, team_payloads)
                    if config.player_stats:
                        player_payloads = stats_scraper.fetch_player_stats(season)
                        with get_session() as session:
                            summary["player_stats"] += upsert_player_season_stats(session, player_payloads)

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
                        dates_to_fetch = select_games_for_odds(
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
            if ingest_run_id is not None:
                complete_job_run(ingest_run_id, "success")
                ingest_run_completed = True

            # Play-by-play scraping
            if config.pbp:
                pbp_run_id = start_job_run("pbp", [config.league_code])
                logger.info(
                    "pbp_scraping_start",
                    run_id=run_id,
                    league=config.league_code,
                    start_date=str(start),
                    end_date=str(end),
                    only_missing=config.only_missing,
                    live=config.live,
                )
                if config.live:
                    # Live-feed PBP (explicit opt-in only).
                    if config.league_code not in self._supported_live_pbp_leagues:
                        logger.info(
                            "pbp_not_implemented",
                            run_id=run_id,
                            league=config.league_code,
                            message="Live play-by-play is not implemented for this league; skipping.",
                        )
                        complete_job_run(pbp_run_id, "success", "pbp_not_implemented")
                    else:
                        try:
                            with get_session() as session:
                                live_summary = self.live_feed_manager.ingest_live_data(
                                    session,
                                    config=config,
                                    updated_before=updated_before_dt,
                                )
                                session.commit()
                            summary["pbp_games"] += live_summary.pbp_games
                            complete_job_run(pbp_run_id, "success")
                        except Exception as exc:
                            logger.exception(
                                "pbp_live_feed_failed",
                                run_id=run_id,
                                league=config.league_code,
                                error=str(exc),
                            )
                            complete_job_run(pbp_run_id, "error", str(exc))
                else:
                    # DEPRECATED (for current testing): do not call live endpoints unless live=true.
                    pbp_events = 0
                    try:
                        with get_session() as session:
                            pbp_games, pbp_events = ingest_pbp_via_sportsref(
                                session,
                                run_id=run_id,
                                league_code=config.league_code,
                                scraper=self.scrapers.get(config.league_code),
                                start_date=start,
                                end_date=end,
                                only_missing=config.only_missing,
                                updated_before=updated_before_dt,
                            )
                            session.commit()
                        summary["pbp_games"] += pbp_games
                        complete_job_run(pbp_run_id, "success")
                    except Exception as exc:
                        logger.exception(
                            "pbp_sportsref_failed",
                            run_id=run_id,
                            league=config.league_code,
                            error=str(exc),
                        )
                        complete_job_run(pbp_run_id, "error", str(exc))

                logger.info("pbp_complete", count=summary["pbp_games"], run_id=run_id)

            # Social scraping (runs after PBP ingestion to ensure timestamps are available)
            if config.social:
                social_run_id = start_job_run("social", [config.league_code])
                if config.league_code not in self._supported_social_leagues:
                    logger.info(
                        "x_social_not_implemented",
                        run_id=run_id,
                        league=config.league_code,
                        message="X/social scraping is not yet implemented for this league; skipping.",
                    )
                    complete_job_run(social_run_id, "success", "x_social_not_implemented")
                else:
                    logger.info(
                        "social_scraping_start",
                        run_id=run_id,
                        league=config.league_code,
                        start_date=str(start),
                        end_date=str(end),
                        only_missing=config.only_missing,
                        updated_before=str(updated_before_dt) if updated_before_dt else None,
                    )

                    # Detect if this is a backfill operation. If the end date is older
                    # than the recent_game_window, we're doing historical backfill and should
                    # skip the recency filter.
                    now = now_utc()
                    recent_window = timedelta(hours=settings.social_config.recent_game_window_hours)
                    end_dt = datetime.combine(end, datetime.max.time()).replace(tzinfo=timezone.utc)
                    is_backfill = (now - end_dt) > recent_window
                    
                    if is_backfill:
                        logger.info(
                            "social_backfill_mode",
                            run_id=run_id,
                            league=config.league_code,
                            reason="end_date is older than recent_game_window",
                        )
                    
                    with get_session() as session:
                        game_ids = select_games_for_social(
                            session, config.league_code, start, end,
                            only_missing=config.only_missing,
                            updated_before=updated_before_dt,
                            is_backfill=is_backfill,
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
                    complete_job_run(social_run_id, "success")

            with get_session() as session:
                detect_missing_pbp(session, league_code=config.league_code)
                detect_external_id_conflicts(session, league_code=config.league_code, source="live_feed")

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
            if summary["team_stats"]:
                summary_parts.append(f'Team stats: {summary["team_stats"]}')
            if summary["player_stats"]:
                summary_parts.append(f'Player stats: {summary["player_stats"]}')

            self._update_run(
                run_id,
                status="success",
                finished_at=now_utc(),
                summary=", ".join(summary_parts) or "No data processed",
            )
            logger.info("scrape_run_complete", run_id=run_id, summary=summary)

        except Exception as exc:
            if ingest_run_id is not None and not ingest_run_completed:
                complete_job_run(ingest_run_id, "error", str(exc))
            logger.exception("scrape_run_failed", run_id=run_id, error=str(exc))
            self._update_run(
                run_id,
                status="error",
                finished_at=now_utc(),
                error_details=str(exc),
            )
            raise

        return summary
