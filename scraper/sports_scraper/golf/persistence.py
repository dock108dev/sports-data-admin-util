"""Golf persistence layer.

Upsert functions for all golf tables using raw SQL with
``sqlalchemy.text()`` and ON CONFLICT DO UPDATE, following the
pattern established in ``odds/fairbet.py``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from ..logging import logger

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


# ---------------------------------------------------------------------------
# Players
# ---------------------------------------------------------------------------

def upsert_players(session: Session, players: list[dict[str, Any]]) -> int:
    """Upsert rows into ``golf_players`` keyed by ``dg_id``.

    Returns the number of rows upserted.
    """
    if not players:
        return 0

    sql = text("""
        INSERT INTO golf_players (dg_id, player_name, country, country_code, amateur, dk_id, fd_id, yahoo_id, updated_at)
        VALUES (:dg_id, :player_name, :country, :country_code, :amateur, :dk_id, :fd_id, :yahoo_id, NOW())
        ON CONFLICT (dg_id) DO UPDATE SET
            player_name  = EXCLUDED.player_name,
            country      = EXCLUDED.country,
            country_code = EXCLUDED.country_code,
            amateur      = EXCLUDED.amateur,
            dk_id        = EXCLUDED.dk_id,
            fd_id        = EXCLUDED.fd_id,
            yahoo_id     = EXCLUDED.yahoo_id,
            updated_at   = NOW()
    """)

    count = 0
    for p in players:
        session.execute(sql, {
            "dg_id": p.get("dg_id"),
            "player_name": p.get("player_name"),
            "country": p.get("country"),
            "country_code": p.get("country_code"),
            "amateur": p.get("amateur", False),
            "dk_id": p.get("dk_id"),
            "fd_id": p.get("fd_id"),
            "yahoo_id": p.get("yahoo_id"),
        })
        count += 1

    logger.debug("golf_upsert_players", count=count)
    return count


# ---------------------------------------------------------------------------
# Tournaments
# ---------------------------------------------------------------------------

def upsert_tournament(session: Session, tournament: dict[str, Any]) -> int:
    """Upsert a single row into ``golf_tournaments`` keyed by (event_id, tour).

    Returns the tournament ``id`` (auto-generated PK).
    """
    sql = text("""
        INSERT INTO golf_tournaments
            (event_id, tour, event_name, course, course_key, start_date, end_date,
             season, purse, currency, country, latitude, longitude, status, updated_at)
        VALUES
            (:event_id, :tour, :event_name, :course, :course_key, :start_date, :end_date,
             :season, :purse, :currency, :country, :latitude, :longitude, :status, NOW())
        ON CONFLICT ON CONSTRAINT uq_golf_tournament_event_tour DO UPDATE SET
            event_name  = EXCLUDED.event_name,
            course      = EXCLUDED.course,
            course_key  = EXCLUDED.course_key,
            start_date  = EXCLUDED.start_date,
            end_date    = EXCLUDED.end_date,
            season      = EXCLUDED.season,
            purse       = EXCLUDED.purse,
            currency    = EXCLUDED.currency,
            country     = EXCLUDED.country,
            latitude    = EXCLUDED.latitude,
            longitude   = EXCLUDED.longitude,
            status      = EXCLUDED.status,
            updated_at  = NOW()
        RETURNING id
    """)

    result = session.execute(sql, {
        "event_id": tournament.get("event_id"),
        "tour": tournament.get("tour"),
        "event_name": tournament.get("event_name"),
        "course": tournament.get("course"),
        "course_key": tournament.get("course_key"),
        "start_date": tournament.get("start_date"),
        "end_date": tournament.get("end_date"),
        "season": tournament.get("season"),
        "purse": tournament.get("purse"),
        "currency": tournament.get("currency", "USD"),
        "country": tournament.get("country"),
        "latitude": tournament.get("latitude"),
        "longitude": tournament.get("longitude"),
        "status": tournament.get("status", "scheduled"),
    })
    row = result.fetchone()
    tournament_id = row[0] if row else 0
    logger.debug("golf_upsert_tournament", tournament_id=tournament_id, event_id=tournament.get("event_id"))
    return tournament_id


# ---------------------------------------------------------------------------
# Tournament field
# ---------------------------------------------------------------------------

def upsert_field(session: Session, tournament_id: int, entries: list[dict[str, Any]]) -> int:
    """Upsert rows into ``golf_tournament_fields`` keyed by (tournament_id, dg_id).

    Returns the number of rows upserted.
    """
    if not entries:
        return 0

    sql = text("""
        INSERT INTO golf_tournament_fields
            (tournament_id, dg_id, player_name, status, tee_time_r1, tee_time_r2,
             early_late, course, dk_salary, fd_salary, updated_at)
        VALUES
            (:tournament_id, :dg_id, :player_name, :status, :tee_time_r1, :tee_time_r2,
             :early_late, :course, :dk_salary, :fd_salary, NOW())
        ON CONFLICT ON CONSTRAINT uq_golf_field_entry DO UPDATE SET
            player_name  = EXCLUDED.player_name,
            status       = EXCLUDED.status,
            tee_time_r1  = EXCLUDED.tee_time_r1,
            tee_time_r2  = EXCLUDED.tee_time_r2,
            early_late   = EXCLUDED.early_late,
            course       = EXCLUDED.course,
            dk_salary    = EXCLUDED.dk_salary,
            fd_salary    = EXCLUDED.fd_salary,
            updated_at   = NOW()
    """)

    count = 0
    for entry in entries:
        session.execute(sql, {
            "tournament_id": tournament_id,
            "dg_id": entry.get("dg_id"),
            "player_name": entry.get("player_name"),
            "status": entry.get("status", "active"),
            "tee_time_r1": entry.get("tee_time_r1") or entry.get("tee_time"),
            "tee_time_r2": entry.get("tee_time_r2"),
            "early_late": entry.get("early_late"),
            "course": entry.get("course"),
            "dk_salary": entry.get("dk_salary"),
            "fd_salary": entry.get("fd_salary"),
        })
        count += 1

    logger.debug("golf_upsert_field", tournament_id=tournament_id, count=count)
    return count


# ---------------------------------------------------------------------------
# Leaderboard
# ---------------------------------------------------------------------------

def upsert_leaderboard(session: Session, tournament_id: int, entries: list[dict[str, Any]]) -> int:
    """Upsert rows into ``golf_leaderboard`` keyed by (tournament_id, dg_id).

    Returns the number of rows upserted.
    """
    if not entries:
        return 0

    sql = text("""
        INSERT INTO golf_leaderboard
            (tournament_id, dg_id, player_name, position, total_score, today_score,
             thru, total_strokes, r1, r2, r3, r4, status,
             sg_total, sg_ott, sg_app, sg_arg, sg_putt,
             win_prob, top_5_prob, top_10_prob, make_cut_prob, updated_at)
        VALUES
            (:tournament_id, :dg_id, :player_name, :position, :total_score, :today_score,
             :thru, :total_strokes, :r1, :r2, :r3, :r4, :status,
             :sg_total, :sg_ott, :sg_app, :sg_arg, :sg_putt,
             :win_prob, :top_5_prob, :top_10_prob, :make_cut_prob, NOW())
        ON CONFLICT ON CONSTRAINT uq_golf_leaderboard_entry DO UPDATE SET
            player_name   = EXCLUDED.player_name,
            position      = EXCLUDED.position,
            total_score   = EXCLUDED.total_score,
            today_score   = EXCLUDED.today_score,
            thru          = EXCLUDED.thru,
            total_strokes = EXCLUDED.total_strokes,
            r1            = EXCLUDED.r1,
            r2            = EXCLUDED.r2,
            r3            = EXCLUDED.r3,
            r4            = EXCLUDED.r4,
            status        = EXCLUDED.status,
            sg_total      = EXCLUDED.sg_total,
            sg_ott        = EXCLUDED.sg_ott,
            sg_app        = EXCLUDED.sg_app,
            sg_arg        = EXCLUDED.sg_arg,
            sg_putt       = EXCLUDED.sg_putt,
            win_prob      = EXCLUDED.win_prob,
            top_5_prob    = EXCLUDED.top_5_prob,
            top_10_prob   = EXCLUDED.top_10_prob,
            make_cut_prob = EXCLUDED.make_cut_prob,
            updated_at    = NOW()
    """)

    count = 0
    for entry in entries:
        session.execute(sql, {
            "tournament_id": tournament_id,
            "dg_id": entry.get("dg_id"),
            "player_name": entry.get("player_name"),
            "position": entry.get("position"),
            "total_score": entry.get("total_score"),
            "today_score": entry.get("today_score"),
            "thru": entry.get("thru"),
            "total_strokes": entry.get("total_strokes"),
            "r1": entry.get("r1"),
            "r2": entry.get("r2"),
            "r3": entry.get("r3"),
            "r4": entry.get("r4"),
            "status": entry.get("status", "active"),
            "sg_total": entry.get("sg_total"),
            "sg_ott": entry.get("sg_ott"),
            "sg_app": entry.get("sg_app"),
            "sg_arg": entry.get("sg_arg"),
            "sg_putt": entry.get("sg_putt"),
            "win_prob": entry.get("win_prob"),
            "top_5_prob": entry.get("top_5_prob"),
            "top_10_prob": entry.get("top_10_prob"),
            "make_cut_prob": entry.get("make_cut_prob"),
        })
        count += 1

    logger.debug("golf_upsert_leaderboard", tournament_id=tournament_id, count=count)
    return count


# ---------------------------------------------------------------------------
# Rounds
# ---------------------------------------------------------------------------

def upsert_rounds(session: Session, tournament_id: int, rounds: list[dict[str, Any]]) -> int:
    """Upsert rows into ``golf_rounds`` keyed by (tournament_id, dg_id, round_num).

    Returns the number of rows upserted.
    """
    if not rounds:
        return 0

    sql = text("""
        INSERT INTO golf_rounds
            (tournament_id, dg_id, round_num, score, strokes,
             sg_total, sg_ott, sg_app, sg_arg, sg_putt,
             driving_dist, driving_acc, gir, scrambling, prox, putts_per_round, updated_at)
        VALUES
            (:tournament_id, :dg_id, :round_num, :score, :strokes,
             :sg_total, :sg_ott, :sg_app, :sg_arg, :sg_putt,
             :driving_dist, :driving_acc, :gir, :scrambling, :prox, :putts_per_round, NOW())
        ON CONFLICT ON CONSTRAINT uq_golf_round DO UPDATE SET
            score          = EXCLUDED.score,
            strokes        = EXCLUDED.strokes,
            sg_total       = EXCLUDED.sg_total,
            sg_ott         = EXCLUDED.sg_ott,
            sg_app         = EXCLUDED.sg_app,
            sg_arg         = EXCLUDED.sg_arg,
            sg_putt        = EXCLUDED.sg_putt,
            driving_dist   = EXCLUDED.driving_dist,
            driving_acc    = EXCLUDED.driving_acc,
            gir            = EXCLUDED.gir,
            scrambling     = EXCLUDED.scrambling,
            prox           = EXCLUDED.prox,
            putts_per_round = EXCLUDED.putts_per_round,
            updated_at     = NOW()
    """)

    count = 0
    for r in rounds:
        session.execute(sql, {
            "tournament_id": tournament_id,
            "dg_id": r.get("dg_id"),
            "round_num": r.get("round_num"),
            "score": r.get("score"),
            "strokes": r.get("strokes"),
            "sg_total": r.get("sg_total"),
            "sg_ott": r.get("sg_ott"),
            "sg_app": r.get("sg_app"),
            "sg_arg": r.get("sg_arg"),
            "sg_putt": r.get("sg_putt"),
            "driving_dist": r.get("driving_dist"),
            "driving_acc": r.get("driving_acc"),
            "gir": r.get("gir"),
            "scrambling": r.get("scrambling"),
            "prox": r.get("prox"),
            "putts_per_round": r.get("putts_per_round"),
        })
        count += 1

    logger.debug("golf_upsert_rounds", tournament_id=tournament_id, count=count)
    return count


# ---------------------------------------------------------------------------
# Player stats (skill ratings)
# ---------------------------------------------------------------------------

def upsert_player_stats(session: Session, stats: list[dict[str, Any]]) -> int:
    """Upsert rows into ``golf_player_stats`` keyed by (dg_id, period).

    Returns the number of rows upserted.
    """
    if not stats:
        return 0

    sql = text("""
        INSERT INTO golf_player_stats
            (dg_id, period, sg_total, sg_ott, sg_app, sg_arg, sg_putt,
             driving_dist, driving_acc, dg_rank, owgr, sample_size, updated_at)
        VALUES
            (:dg_id, :period, :sg_total, :sg_ott, :sg_app, :sg_arg, :sg_putt,
             :driving_dist, :driving_acc, :dg_rank, :owgr, :sample_size, NOW())
        ON CONFLICT ON CONSTRAINT uq_golf_player_stats DO UPDATE SET
            sg_total     = EXCLUDED.sg_total,
            sg_ott       = EXCLUDED.sg_ott,
            sg_app       = EXCLUDED.sg_app,
            sg_arg       = EXCLUDED.sg_arg,
            sg_putt      = EXCLUDED.sg_putt,
            driving_dist = EXCLUDED.driving_dist,
            driving_acc  = EXCLUDED.driving_acc,
            dg_rank      = EXCLUDED.dg_rank,
            owgr         = EXCLUDED.owgr,
            sample_size  = EXCLUDED.sample_size,
            updated_at   = NOW()
    """)

    count = 0
    for s in stats:
        session.execute(sql, {
            "dg_id": s.get("dg_id"),
            "period": s.get("period", "current"),
            "sg_total": s.get("sg_total"),
            "sg_ott": s.get("sg_ott"),
            "sg_app": s.get("sg_app"),
            "sg_arg": s.get("sg_arg"),
            "sg_putt": s.get("sg_putt"),
            "driving_dist": s.get("driving_dist"),
            "driving_acc": s.get("driving_acc"),
            "dg_rank": s.get("dg_rank"),
            "owgr": s.get("owgr"),
            "sample_size": s.get("sample_size"),
        })
        count += 1

    logger.debug("golf_upsert_player_stats", count=count)
    return count


# ---------------------------------------------------------------------------
# Tournament odds
# ---------------------------------------------------------------------------

def upsert_odds(session: Session, tournament_id: int, odds: list[dict[str, Any]]) -> int:
    """Upsert rows into ``golf_tournament_odds`` keyed by (tournament_id, dg_id, book, market).

    Returns the number of rows upserted.
    """
    if not odds:
        return 0

    sql = text("""
        INSERT INTO golf_tournament_odds
            (tournament_id, dg_id, player_name, book, market, odds, implied_prob,
             dg_prob, observed_at, updated_at)
        VALUES
            (:tournament_id, :dg_id, :player_name, :book, :market, :odds, :implied_prob,
             :dg_prob, NOW(), NOW())
        ON CONFLICT ON CONSTRAINT uq_golf_odds DO UPDATE SET
            player_name  = EXCLUDED.player_name,
            odds         = EXCLUDED.odds,
            implied_prob = EXCLUDED.implied_prob,
            dg_prob      = EXCLUDED.dg_prob,
            observed_at  = NOW(),
            updated_at   = NOW()
    """)

    count = 0
    for o in odds:
        session.execute(sql, {
            "tournament_id": tournament_id,
            "dg_id": o.get("dg_id"),
            "player_name": o.get("player_name"),
            "book": o.get("book"),
            "market": o.get("market"),
            "odds": o.get("odds"),
            "implied_prob": o.get("implied_prob"),
            "dg_prob": o.get("dg_prob"),
        })
        count += 1

    logger.debug("golf_upsert_odds", tournament_id=tournament_id, count=count)
    return count


# ---------------------------------------------------------------------------
# DFS projections
# ---------------------------------------------------------------------------

def upsert_dfs_projections(session: Session, tournament_id: int, projections: list[dict[str, Any]]) -> int:
    """Upsert rows into ``golf_dfs_projections`` keyed by (tournament_id, dg_id, site).

    Returns the number of rows upserted.
    """
    if not projections:
        return 0

    sql = text("""
        INSERT INTO golf_dfs_projections
            (tournament_id, dg_id, player_name, site, salary,
             projected_points, projected_ownership, updated_at)
        VALUES
            (:tournament_id, :dg_id, :player_name, :site, :salary,
             :projected_points, :projected_ownership, NOW())
        ON CONFLICT ON CONSTRAINT uq_golf_dfs_projection DO UPDATE SET
            player_name        = EXCLUDED.player_name,
            salary             = EXCLUDED.salary,
            projected_points   = EXCLUDED.projected_points,
            projected_ownership = EXCLUDED.projected_ownership,
            updated_at         = NOW()
    """)

    count = 0
    for proj in projections:
        session.execute(sql, {
            "tournament_id": tournament_id,
            "dg_id": proj.get("dg_id"),
            "player_name": proj.get("player_name"),
            "site": proj.get("site"),
            "salary": proj.get("salary"),
            "projected_points": proj.get("projected_points"),
            "projected_ownership": proj.get("projected_ownership"),
        })
        count += 1

    logger.debug("golf_upsert_dfs_projections", tournament_id=tournament_id, count=count)
    return count
