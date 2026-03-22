"""Ingestion service for NBA advanced stats.

Fetches advanced boxscore, hustle, and tracking data from stats.nba.com
endpoints, aggregates into team-level and player-level stats, and upserts
into the nba_game_advanced_stats and nba_player_advanced_stats tables.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from ..db import db_models
from ..logging import logger


def _safe_float(val: object) -> float | None:
    """Coerce a value to float, returning None on failure."""
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _safe_int(val: object) -> int | None:
    """Coerce a value to int, returning None on failure."""
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def _parse_minutes(val: object) -> float | None:
    """Parse NBA minutes string (e.g. 'PT36M12.00S' or '36:12') to float minutes."""
    if val is None:
        return None
    s = str(val)
    # Handle ISO duration: PT36M12.00S
    if s.startswith("PT"):
        import re
        m = re.match(r"PT(?:(\d+)M)?(?:([\d.]+)S)?", s)
        if m:
            mins = int(m.group(1) or 0)
            secs = float(m.group(2) or 0)
            return round(mins + secs / 60.0, 2)
    # Handle MM:SS format
    if ":" in s:
        parts = s.split(":")
        try:
            return round(int(parts[0]) + int(parts[1]) / 60.0, 2)
        except (ValueError, IndexError):
            pass
    # Try raw float
    return _safe_float(val)


def ingest_advanced_stats_for_game(session: Session, game_id: int) -> dict:
    """Ingest advanced stats from stats.nba.com for a single NBA game.

    Steps:
    1. Validate game exists, status=final, league=NBA, has nba_game_id
    2. Fetch boxscoreadvancedv3, boxscorehustlev2, boxscoreplayertrackingv3
    3. Parse team-level stats from advanced boxscore
    4. Parse player-level stats from all 3 endpoints
    5. Upsert team rows (2) into nba_game_advanced_stats
    6. Upsert player rows into nba_player_advanced_stats
    7. Set game.last_advanced_stats_at = now()

    Returns:
        Dict with ingestion result status.
    """
    game = session.query(db_models.SportsGame).get(game_id)
    if not game:
        logger.warning("nba_adv_stats_game_not_found", game_id=game_id)
        return {"game_id": game_id, "status": "not_found"}

    if game.status != db_models.GameStatus.final.value:
        logger.info("nba_adv_stats_skip_not_final", game_id=game_id, status=game.status)
        return {"game_id": game_id, "status": "skipped", "reason": "not_final"}

    league = session.query(db_models.SportsLeague).get(game.league_id)
    if not league or league.code != "NBA":
        logger.info("nba_adv_stats_skip_not_nba", game_id=game_id)
        return {"game_id": game_id, "status": "skipped", "reason": "not_nba"}

    external_ids = game.external_ids or {}
    nba_game_id = external_ids.get("nba_game_id")
    if not nba_game_id:
        logger.warning("nba_adv_stats_no_game_id", game_id=game_id)
        return {"game_id": game_id, "status": "skipped", "reason": "no_nba_game_id"}

    # Fetch data from stats.nba.com
    from ..live.nba_advanced import (
        NBAAdvancedStatsFetcher,
        parse_advanced_boxscore,
        parse_hustle_stats,
        parse_tracking_stats,
    )

    fetcher = NBAAdvancedStatsFetcher()

    adv_data = fetcher.fetch_advanced_boxscore(nba_game_id)
    hustle_data = fetcher.fetch_hustle_stats(nba_game_id)
    tracking_data = fetcher.fetch_tracking_stats(nba_game_id)

    if adv_data is None:
        logger.warning("nba_adv_stats_no_advanced_data", game_id=game_id, nba_game_id=nba_game_id)
        return {"game_id": game_id, "status": "error", "reason": "no_advanced_data"}

    # Parse responses
    team_rows_raw, player_rows_raw = parse_advanced_boxscore(adv_data)

    hustle_rows: list[dict] = []
    if hustle_data:
        hustle_rows = parse_hustle_stats(hustle_data)

    tracking_rows: list[dict] = []
    if tracking_data:
        tracking_rows = parse_tracking_stats(tracking_data)

    # Build lookup maps for hustle and tracking by (team_id, player_id)
    hustle_by_player: dict[tuple, dict] = {}
    for hr in hustle_rows:
        key = (str(hr.get("TEAM_ID")), str(hr.get("PLAYER_ID")))
        hustle_by_player[key] = hr

    tracking_by_player: dict[tuple, dict] = {}
    for tr in tracking_rows:
        key = (str(tr.get("TEAM_ID")), str(tr.get("PLAYER_ID")))
        tracking_by_player[key] = tr

    # Resolve team IDs from our database
    team_map = {
        True: {"team_id": game.home_team_id, "is_home": True},
        False: {"team_id": game.away_team_id, "is_home": False},
    }

    # ------------------------------------------------------------------
    # Upsert team-level stats
    # ------------------------------------------------------------------
    upserted = 0
    for tr in team_rows_raw:
        is_home = tr.get("is_home")
        if is_home is None:
            # Determine side from TEAM_ID matching
            nba_team_id = str(tr.get("TEAM_ID", ""))
            # Try to match by checking home/away team external refs
            # Default: first row is home, second is away (NBA convention)
            is_home = upserted == 0

        meta = team_map.get(is_home, team_map[True])

        # Aggregate hustle stats per team
        team_hustle = _aggregate_team_hustle(
            hustle_rows, str(tr.get("TEAM_ID", ""))
        )

        row = {
            "game_id": game_id,
            "team_id": meta["team_id"],
            "is_home": meta["is_home"],
            # Efficiency
            "off_rating": _safe_float(tr.get("OFF_RATING")),
            "def_rating": _safe_float(tr.get("DEF_RATING")),
            "net_rating": _safe_float(tr.get("NET_RATING")),
            "pace": _safe_float(tr.get("PACE")),
            "pie": _safe_float(tr.get("PIE")),
            # Shooting
            "efg_pct": _safe_float(tr.get("EFG_PCT")),
            "ts_pct": _safe_float(tr.get("TS_PCT")),
            "fg_pct": _safe_float(tr.get("FG_PCT")),
            "fg3_pct": _safe_float(tr.get("FG3_PCT")),
            "ft_pct": _safe_float(tr.get("FT_PCT")),
            # Rebounding
            "orb_pct": _safe_float(tr.get("OREB_PCT")),
            "drb_pct": _safe_float(tr.get("DREB_PCT")),
            "reb_pct": _safe_float(tr.get("REB_PCT")),
            # Playmaking
            "ast_pct": _safe_float(tr.get("AST_PCT")),
            "ast_ratio": _safe_float(tr.get("AST_RATIO")),
            "ast_tov_ratio": _safe_float(tr.get("AST_TOV")),
            # Ball security
            "tov_pct": _safe_float(tr.get("TM_TOV_PCT")),
            # Free throws
            "ft_rate": _safe_float(tr.get("FTA_RATE")),
            # Hustle (aggregated from player-level)
            "contested_shots": team_hustle.get("contested_shots"),
            "deflections": team_hustle.get("deflections"),
            "charges_drawn": team_hustle.get("charges_drawn"),
            "loose_balls_recovered": team_hustle.get("loose_balls_recovered"),
            # Paint / transition (from team stats if available)
            "paint_points": _safe_int(tr.get("PTS_PAINT")),
            "fastbreak_points": _safe_int(tr.get("PTS_FB")),
            "second_chance_points": _safe_int(tr.get("PTS_2ND_CHANCE")),
            "points_off_turnovers": _safe_int(tr.get("PTS_OFF_TOV")),
            "bench_points": _safe_int(tr.get("PTS_BENCH")),
            "source": "stats_nba_com",
            "updated_at": datetime.now(UTC),
        }

        stmt = pg_insert(db_models.NBAGameAdvancedStats).values(**row)
        update_cols = {col: stmt.excluded[col] for col in row if col not in ("game_id", "team_id")}
        stmt = stmt.on_conflict_do_update(
            constraint="uq_nba_advanced_game_team",
            set_=update_cols,
        )
        session.execute(stmt)
        upserted += 1

    # ------------------------------------------------------------------
    # Upsert player-level stats
    # ------------------------------------------------------------------
    player_upserted = 0
    for pr in player_rows_raw:
        is_home = pr.get("is_home")
        if is_home is None:
            is_home = True  # fallback

        meta = team_map.get(is_home, team_map[True])
        player_id = str(pr.get("PLAYER_ID", ""))
        team_id_str = str(pr.get("TEAM_ID", ""))

        if not player_id or player_id == "0":
            continue

        # Look up hustle and tracking data for this player
        hustle = hustle_by_player.get((team_id_str, player_id), {})
        tracking = tracking_by_player.get((team_id_str, player_id), {})

        player_name = pr.get("PLAYER_NAME") or pr.get("PLAYER") or "Unknown"

        row = {
            "game_id": game_id,
            "team_id": meta["team_id"],
            "is_home": meta["is_home"],
            "player_external_ref": player_id,
            "player_name": player_name,
            # Minutes
            "minutes": _parse_minutes(pr.get("MIN")),
            # Efficiency
            "off_rating": _safe_float(pr.get("OFF_RATING")),
            "def_rating": _safe_float(pr.get("DEF_RATING")),
            "net_rating": _safe_float(pr.get("NET_RATING")),
            "usg_pct": _safe_float(pr.get("USG_PCT")),
            "pie": _safe_float(pr.get("PIE")),
            # Shooting efficiency
            "ts_pct": _safe_float(pr.get("TS_PCT")),
            "efg_pct": _safe_float(pr.get("EFG_PCT")),
            # Shooting context (from tracking)
            "contested_2pt_fga": _safe_int(tracking.get("CONT_2PT_FGA")),
            "contested_2pt_fgm": _safe_int(tracking.get("CONT_2PT_FGM")),
            "uncontested_2pt_fga": _safe_int(tracking.get("UCONT_2PT_FGA")),
            "uncontested_2pt_fgm": _safe_int(tracking.get("UCONT_2PT_FGM")),
            "contested_3pt_fga": _safe_int(tracking.get("CONT_3PT_FGA")),
            "contested_3pt_fgm": _safe_int(tracking.get("CONT_3PT_FGM")),
            "uncontested_3pt_fga": _safe_int(tracking.get("UCONT_3PT_FGA")),
            "uncontested_3pt_fgm": _safe_int(tracking.get("UCONT_3PT_FGM")),
            # Pull-up / catch-and-shoot (from tracking)
            "pull_up_fga": _safe_int(tracking.get("PULL_UP_FGA")),
            "pull_up_fgm": _safe_int(tracking.get("PULL_UP_FGM")),
            "catch_shoot_fga": _safe_int(tracking.get("CATCH_SHOOT_FGA")),
            "catch_shoot_fgm": _safe_int(tracking.get("CATCH_SHOOT_FGM")),
            # Tracking
            "speed": _safe_float(tracking.get("SPD")),
            "distance": _safe_float(tracking.get("DIST")),
            "touches": _safe_float(tracking.get("TCHS")),
            "time_of_possession": _safe_float(tracking.get("TIME_OF_POSS")),
            # Hustle
            "contested_shots": _safe_int(hustle.get("CONTESTED_SHOTS")),
            "deflections": _safe_int(hustle.get("DEFLECTIONS")),
            "charges_drawn": _safe_int(hustle.get("CHARGES_DRAWN")),
            "loose_balls_recovered": _safe_int(hustle.get("LOOSE_BALLS_RECOVERED")),
            "screen_assists": _safe_int(hustle.get("SCREEN_ASSISTS")),
            "source": "stats_nba_com",
            "updated_at": datetime.now(UTC),
        }

        stmt = pg_insert(db_models.NBAPlayerAdvancedStats).values(**row)
        update_cols = {
            col: stmt.excluded[col]
            for col in row
            if col not in ("game_id", "team_id", "player_external_ref")
        }
        stmt = stmt.on_conflict_do_update(
            constraint="uq_nba_player_advanced_game_team_player",
            set_=update_cols,
        )
        session.execute(stmt)
        player_upserted += 1

    # Mark game as processed
    game.last_advanced_stats_at = datetime.now(UTC)
    session.flush()

    logger.info(
        "nba_adv_stats_ingested",
        game_id=game_id,
        nba_game_id=nba_game_id,
        team_rows_upserted=upserted,
        player_rows_upserted=player_upserted,
    )

    return {
        "game_id": game_id,
        "status": "success",
        "rows_upserted": upserted,
        "player_rows_upserted": player_upserted,
    }


def _aggregate_team_hustle(hustle_rows: list[dict], team_id_str: str) -> dict:
    """Sum all player hustle stats for a given team.

    Returns dict with contested_shots, deflections, charges_drawn,
    loose_balls_recovered as ints or None if no data.
    """
    contested = 0
    deflections = 0
    charges = 0
    loose_balls = 0
    found = False

    for hr in hustle_rows:
        if str(hr.get("TEAM_ID", "")) != team_id_str:
            continue
        found = True
        contested += _safe_int(hr.get("CONTESTED_SHOTS")) or 0
        deflections += _safe_int(hr.get("DEFLECTIONS")) or 0
        charges += _safe_int(hr.get("CHARGES_DRAWN")) or 0
        loose_balls += _safe_int(hr.get("LOOSE_BALLS_RECOVERED")) or 0

    if not found:
        return {
            "contested_shots": None,
            "deflections": None,
            "charges_drawn": None,
            "loose_balls_recovered": None,
        }

    return {
        "contested_shots": contested,
        "deflections": deflections,
        "charges_drawn": charges,
        "loose_balls_recovered": loose_balls,
    }
