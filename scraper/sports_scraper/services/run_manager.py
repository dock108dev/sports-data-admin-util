"""Run manager that orchestrates scraper + odds execution."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict

from ..config import settings
from ..db import db_models, get_session
from ..logging import logger
from ..models import IngestionConfig
from ..live import LiveFeedManager
from ..persistence import persist_game_payload
from ..scrapers import get_all_scrapers
from ..celery_app import SOCIAL_QUEUE
from ..utils.datetime_utils import now_utc, sports_today_et, today_et
from .diagnostics import detect_external_id_conflicts, detect_missing_pbp
from .job_runs import complete_job_run, start_job_run
from .game_selection import select_games_for_boxscores
from .pbp_ingestion import (
    ingest_pbp_via_nba_api,
    ingest_pbp_via_ncaab_api,
    ingest_pbp_via_nhl_api,
    ingest_pbp_via_sportsref,
)


class ScrapeRunManager:
    def __init__(self) -> None:
        self.scrapers = get_all_scrapers()
        self.live_feed_manager = LiveFeedManager()

        # Feature support varies by league. When a toggle is enabled for an unsupported
        # league, we must NOT fail the run; we log and continue.
        self._supported_social_leagues = ("NBA", "NHL", "NCAAB")
        self._supported_live_pbp_leagues = ("NBA", "NHL", "NCAAB")

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
            "games_enriched": 0,  # Games enriched with boxscore data
            "games_with_stats": 0,  # Games that had player stats upserted
            "social_posts": 0,
            "pbp_games": 0,
        }
        start = config.start_date or today_et()
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
            social=config.social,
            pbp=config.pbp,
            only_missing=config.only_missing,
            updated_before=str(config.updated_before) if config.updated_before else None,
            start_date=str(start),
            end_date=str(end),
        )

        # NHL, NBA, and NCAAB use official APIs for boxscores, so scraper is not required
        if not scraper and config.boxscores and config.league_code not in ("NHL", "NBA", "NCAAB"):
            raise RuntimeError(f"No scraper implemented for {config.league_code}")

        self._update_run(run_id, status="running", started_at=now_utc())

        ingest_run_id: int | None = None
        ingest_run_completed = False
        try:
            if config.boxscores:
                ingest_run_id = start_job_run("ingest", [config.league_code])

            # Boxscore scraping (enrichment only - does NOT create games)
            # Boxscores enrich existing games created by Odds API
            # IMPORTANT: Only scrape boxscores for completed games (yesterday and earlier)
            if config.boxscores:
                yesterday = sports_today_et() - timedelta(days=1)
                boxscore_end = min(end, yesterday)
                games_skipped = 0

                if start > yesterday:
                    logger.info(
                        "boxscore_scraping_skipped_future_dates",
                        run_id=run_id,
                        league=config.league_code,
                        start_date=str(start),
                        end_date=str(end),
                        reason="All dates are today or in the future - no completed games to scrape",
                    )
                elif config.league_code == "NHL":
                    # NHL: Use official NHL API for boxscores (faster and more reliable than web scraping)
                    from .nhl_boxscore_ingestion import ingest_boxscores_via_nhl_api

                    logger.info(
                        "boxscore_scraping_start",
                        run_id=run_id,
                        league=config.league_code,
                        start_date=str(start),
                        end_date=str(boxscore_end),
                        original_end_date=str(end) if end != boxscore_end else None,
                        only_missing=config.only_missing,
                        stage="2_boxscore_enrichment",
                        source="nhl_api",
                    )

                    try:
                        with get_session() as session:
                            games, enriched, with_stats = ingest_boxscores_via_nhl_api(
                                session,
                                run_id=run_id,
                                start_date=start,
                                end_date=boxscore_end,
                                only_missing=config.only_missing,
                                updated_before=updated_before_dt,
                            )
                            session.commit()
                        summary["games"] = games
                        summary["games_enriched"] = enriched
                        summary["games_with_stats"] = with_stats
                    except Exception as exc:
                        logger.exception(
                            "nhl_boxscore_ingestion_failed",
                            run_id=run_id,
                            league=config.league_code,
                            error=str(exc),
                        )
                elif config.league_code == "NCAAB":
                    # NCAAB: Use College Basketball Data API for boxscores
                    from .ncaab_boxscore_ingestion import ingest_boxscores_via_ncaab_api

                    logger.info(
                        "boxscore_scraping_start",
                        run_id=run_id,
                        league=config.league_code,
                        start_date=str(start),
                        end_date=str(boxscore_end),
                        original_end_date=str(end) if end != boxscore_end else None,
                        only_missing=config.only_missing,
                        stage="2_boxscore_enrichment",
                        source="cbb_api",
                    )

                    try:
                        with get_session() as session:
                            games, enriched, with_stats = ingest_boxscores_via_ncaab_api(
                                session,
                                run_id=run_id,
                                start_date=start,
                                end_date=boxscore_end,
                                only_missing=config.only_missing,
                                updated_before=updated_before_dt,
                            )
                            session.commit()
                        summary["games"] = games
                        summary["games_enriched"] = enriched
                        summary["games_with_stats"] = with_stats
                    except Exception as exc:
                        logger.exception(
                            "ncaab_boxscore_ingestion_failed",
                            run_id=run_id,
                            league=config.league_code,
                            error=str(exc),
                        )
                elif config.league_code == "NBA":
                    # NBA: Use NBA CDN API for boxscores (faster and more reliable than BR scraping)
                    from .nba_boxscore_ingestion import ingest_boxscores_via_nba_api

                    logger.info(
                        "boxscore_scraping_start",
                        run_id=run_id,
                        league=config.league_code,
                        start_date=str(start),
                        end_date=str(boxscore_end),
                        original_end_date=str(end) if end != boxscore_end else None,
                        only_missing=config.only_missing,
                        stage="2_boxscore_enrichment",
                        source="nba_api",
                    )

                    try:
                        with get_session() as session:
                            games, enriched, with_stats = ingest_boxscores_via_nba_api(
                                session,
                                run_id=run_id,
                                start_date=start,
                                end_date=boxscore_end,
                                only_missing=config.only_missing,
                                updated_before=updated_before_dt,
                            )
                            session.commit()
                        summary["games"] = games
                        summary["games_enriched"] = enriched
                        summary["games_with_stats"] = with_stats
                    except Exception as exc:
                        logger.exception(
                            "nba_boxscore_ingestion_failed",
                            run_id=run_id,
                            league=config.league_code,
                            error=str(exc),
                        )
                elif scraper:
                    # Other leagues: Continue using Sports Reference scraper
                    logger.info(
                        "boxscore_scraping_start",
                        run_id=run_id,
                        league=config.league_code,
                        start_date=str(start),
                        end_date=str(boxscore_end),
                        original_end_date=str(end) if end != boxscore_end else None,
                        only_missing=config.only_missing,
                        stage="2_boxscore_enrichment",
                        source="sports_reference",
                    )

                    if config.only_missing or updated_before_dt:
                        # Filter games by criteria
                        with get_session() as session:
                            games_to_scrape = select_games_for_boxscores(
                                session, config.league_code, start, boxscore_end,
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
                                        if result.game_id is not None:
                                            summary["games"] += 1
                                            if result.enriched:
                                                summary["games_enriched"] += 1
                                            if result.has_player_stats:
                                                summary["games_with_stats"] += 1
                                        else:
                                            games_skipped += 1
                            except Exception as exc:
                                logger.warning("boxscore_scrape_failed", game_id=game_id, error=str(exc))
                    else:
                        # Scrape all games in date range from Sports Reference
                        for game_payload in scraper.fetch_date_range(start, boxscore_end):
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
                                    if result.game_id is not None:
                                        summary["games"] += 1
                                        if result.enriched:
                                            summary["games_enriched"] += 1
                                        if result.has_player_stats:
                                            summary["games_with_stats"] += 1
                                    else:
                                        # Game not found - this is normal for games not in Odds API
                                        games_skipped += 1
                            except Exception as exc:
                                logger.exception("game_persist_failed", error=str(exc), run_id=run_id)
                else:
                    logger.warning(
                        "boxscore_scraping_skipped_no_source",
                        run_id=run_id,
                        league=config.league_code,
                        reason="No scraper available for this league",
                    )

                logger.info(
                    "boxscores_complete",
                    count=summary["games"],
                    enriched=summary["games_enriched"],
                    with_stats=summary["games_with_stats"],
                    skipped=games_skipped,
                    run_id=run_id,
                )

                # Gap detection: compare DB games for the date range vs enriched count
                try:
                    yesterday = sports_today_et() - timedelta(days=1)
                    bs_end = min(end, yesterday)
                    window_start = datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc)
                    window_end = datetime.combine(bs_end, datetime.max.time(), tzinfo=timezone.utc)
                    with get_session() as session:
                        total_final_games = (
                            session.query(db_models.SportsGame)
                            .join(db_models.SportsLeague, db_models.SportsGame.league_id == db_models.SportsLeague.id)
                            .filter(
                                db_models.SportsLeague.code == config.league_code,
                                db_models.SportsGame.status == db_models.GameStatus.final.value,
                                db_models.SportsGame.game_date >= window_start,
                                db_models.SportsGame.game_date <= window_end,
                            )
                            .count()
                        )
                        if total_final_games > summary["games_enriched"]:
                            gap = total_final_games - summary["games_enriched"]
                            logger.warning(
                                "boxscore_gap_detected",
                                run_id=run_id,
                                league=config.league_code,
                                total_final_games=total_final_games,
                                games_enriched=summary["games_enriched"],
                                gap=gap,
                                start_date=str(start),
                                end_date=str(bs_end),
                            )
                except Exception as exc:
                    logger.warning("boxscore_gap_check_failed", run_id=run_id, error=str(exc))

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
                    # Non-live PBP scraping
                    # Only scrape PBP for completed games (yesterday and earlier)
                    pbp_yesterday = sports_today_et() - timedelta(days=1)
                    pbp_end = min(end, pbp_yesterday)
                    pbp_events = 0

                    if start > pbp_yesterday:
                        logger.info(
                            "pbp_skipped_future_dates",
                            run_id=run_id,
                            league=config.league_code,
                            reason="All dates are today or in the future - no completed games for PBP",
                        )
                        complete_job_run(pbp_run_id, "success", "skipped_future_dates")
                    elif config.league_code == "NHL":
                        # NHL: Use official NHL API for PBP (Sports Reference doesn't have NHL PBP)
                        try:
                            with get_session() as session:
                                pbp_games, pbp_events = ingest_pbp_via_nhl_api(
                                    session,
                                    run_id=run_id,
                                    start_date=start,
                                    end_date=pbp_end,
                                    only_missing=config.only_missing,
                                    updated_before=updated_before_dt,
                                )
                                session.commit()
                            summary["pbp_games"] += pbp_games
                            complete_job_run(pbp_run_id, "success")
                        except Exception as exc:
                            logger.exception(
                                "pbp_nhl_api_failed",
                                run_id=run_id,
                                league=config.league_code,
                                error=str(exc),
                            )
                            complete_job_run(pbp_run_id, "error", str(exc))
                    elif config.league_code == "NCAAB":
                        # NCAAB: Use College Basketball Data API for PBP
                        try:
                            with get_session() as session:
                                pbp_games, pbp_events = ingest_pbp_via_ncaab_api(
                                    session,
                                    run_id=run_id,
                                    start_date=start,
                                    end_date=pbp_end,
                                    only_missing=config.only_missing,
                                    updated_before=updated_before_dt,
                                )
                                session.commit()
                            summary["pbp_games"] += pbp_games
                            complete_job_run(pbp_run_id, "success")
                        except Exception as exc:
                            logger.exception(
                                "pbp_ncaab_api_failed",
                                run_id=run_id,
                                league=config.league_code,
                                error=str(exc),
                            )
                            complete_job_run(pbp_run_id, "error", str(exc))
                    elif config.league_code == "NBA":
                        # NBA: Use official NBA API for PBP
                        try:
                            with get_session() as session:
                                pbp_games, pbp_events = ingest_pbp_via_nba_api(
                                    session,
                                    run_id=run_id,
                                    start_date=start,
                                    end_date=pbp_end,
                                    only_missing=config.only_missing,
                                    updated_before=updated_before_dt,
                                )
                                session.commit()
                            summary["pbp_games"] += pbp_games
                            complete_job_run(pbp_run_id, "success")
                        except Exception as exc:
                            logger.exception(
                                "pbp_nba_api_failed",
                                run_id=run_id,
                                league=config.league_code,
                                error=str(exc),
                            )
                            complete_job_run(pbp_run_id, "error", str(exc))
                    else:
                        # Other leagues: Use Sports Reference for PBP
                        try:
                            with get_session() as session:
                                pbp_games, pbp_events = ingest_pbp_via_sportsref(
                                    session,
                                    run_id=run_id,
                                    league_code=config.league_code,
                                    scraper=self.scrapers.get(config.league_code),
                                    start_date=start,
                                    end_date=pbp_end,
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

            # Social scraping — dispatched to the dedicated social-scraper worker.
            # The social-scraper has X auth tokens and concurrency=1 for rate limiting.
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
                    from ..jobs.social_tasks import collect_team_social, handle_social_task_failure

                    logger.info(
                        "social_dispatched_to_worker",
                        run_id=run_id,
                        league=config.league_code,
                        start_date=str(start),
                        end_date=str(end),
                    )
                    # collect_team_social maps tweets to games internally after collection.
                    # The social task will finalize the SportsJobRun and update the
                    # SportsScrapeRun summary on completion (or via link_error on failure).
                    collect_team_social.apply_async(
                        args=[config.league_code, str(start), str(end)],
                        kwargs={"scrape_run_id": run_id, "social_job_run_id": social_run_id},
                        queue=SOCIAL_QUEUE,
                        link_error=handle_social_task_failure.s(run_id, social_run_id),
                    )
                    summary["social_posts"] = "dispatched"

            with get_session() as session:
                detect_missing_pbp(session, league_code=config.league_code)
                detect_external_id_conflicts(session, league_code=config.league_code, source="live_feed")

            # Build summary string
            summary_parts = []
            if summary["games"]:
                summary_parts.append(
                    f'Games: {summary["games"]} ({summary["games_enriched"]} enriched, {summary["games_with_stats"]} with stats)'
                )
            if summary["social_posts"]:
                social_val = summary["social_posts"]
                if social_val == "dispatched":
                    summary_parts.append("Social: dispatched to worker")
                else:
                    summary_parts.append(f'Social: {social_val}')
            if summary["pbp_games"]:
                summary_parts.append(f'PBP: {summary["pbp_games"]}')

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
