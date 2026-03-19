"""Golf pool endpoints — public and admin."""

from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from typing import Any

from fastapi import Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import delete, func as sa_func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.db.golf import GolfTournament, GolfTournamentField
from app.db.golf_pools import (
    GolfPool,
    GolfPoolBucket,
    GolfPoolBucketPlayer,
    GolfPoolEntry,
    GolfPoolEntryPick,
    GolfPoolEntryScore,
    GolfPoolEntryScorePlayer,
)
from app.services.golf_pool_scoring import Pick, rules_from_json, validate_picks

from . import router


# ---------------------------------------------------------------------------
# Pydantic request/response models
# ---------------------------------------------------------------------------


class PickRequest(BaseModel):
    dg_id: int
    pick_slot: int
    bucket_number: int | None = None


class EntrySubmitRequest(BaseModel):
    email: str = Field(..., description="Entrant email address")
    entry_name: str | None = Field(None, description="Display name for the entry")
    picks: list[PickRequest] = Field(..., description="List of golfer picks")


class PoolCreateRequest(BaseModel):
    code: str = Field(..., description="Unique pool code within tournament")
    name: str = Field(..., description="Display name")
    club_code: str = Field(..., description="Club identifier (e.g. rvcc, crestmont)")
    tournament_id: int = Field(..., description="FK to golf_tournaments.id")
    rules_json: dict[str, Any] | None = Field(None, description="Pool rules as JSON")
    entry_deadline: str | None = Field(None, description="ISO datetime for entry cutoff")
    entry_open_at: str | None = Field(None, description="ISO datetime when entries open")
    status: str = Field("draft", description="Pool status")
    max_entries_per_email: int | None = None
    scoring_enabled: bool = False
    require_upload: bool = False
    allow_self_service_entry: bool = True
    notes: str | None = None


class PoolUpdateRequest(BaseModel):
    name: str | None = None
    status: str | None = None
    rules_json: dict[str, Any] | None = None
    entry_deadline: str | None = None
    entry_open_at: str | None = None
    max_entries_per_email: int | None = None
    scoring_enabled: bool | None = None
    require_upload: bool | None = None
    allow_self_service_entry: bool | None = None
    notes: str | None = None


class BucketPlayerItem(BaseModel):
    dg_id: int
    player_name: str


class BucketItem(BaseModel):
    bucket_number: int
    label: str | None = None
    players: list[BucketPlayerItem]


class BucketCreateRequest(BaseModel):
    buckets: list[BucketItem] = Field(..., description="Bucket definitions with players")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _serialize_pool(p: GolfPool) -> dict[str, Any]:
    return {
        "id": p.id,
        "code": p.code,
        "name": p.name,
        "club_code": p.club_code,
        "tournament_id": p.tournament_id,
        "status": p.status,
        "rules_json": p.rules_json,
        "entry_open_at": p.entry_open_at.isoformat() if p.entry_open_at else None,
        "entry_deadline": p.entry_deadline.isoformat() if p.entry_deadline else None,
        "scoring_enabled": p.scoring_enabled,
        "max_entries_per_email": p.max_entries_per_email,
        "require_upload": p.require_upload,
        "allow_self_service_entry": p.allow_self_service_entry,
        "notes": p.notes,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


def _serialize_entry(e: GolfPoolEntry) -> dict[str, Any]:
    return {
        "id": e.id,
        "pool_id": e.pool_id,
        "email": e.email,
        "entry_name": e.entry_name,
        "entry_number": e.entry_number,
        "status": e.status,
        "source": e.source,
        "submitted_at": e.submitted_at.isoformat() if e.submitted_at else None,
        "created_at": e.created_at.isoformat() if e.created_at else None,
    }


def _serialize_pick(pk: GolfPoolEntryPick) -> dict[str, Any]:
    return {
        "id": pk.id,
        "dg_id": pk.dg_id,
        "player_name": pk.player_name_snapshot,
        "pick_slot": pk.pick_slot,
        "bucket_number": pk.bucket_number,
    }


async def _get_pool_or_404(pool_id: int, db: AsyncSession) -> GolfPool:
    pool = await db.get(GolfPool, pool_id)
    if pool is None:
        raise HTTPException(status_code=404, detail="Pool not found")
    return pool


async def _get_player_names(dg_ids: list[int], db: AsyncSession) -> dict[int, str]:
    """Resolve dg_ids to player names from the tournament field."""
    if not dg_ids:
        return {}
    result = await db.execute(
        select(GolfTournamentField.dg_id, GolfTournamentField.player_name).where(
            GolfTournamentField.dg_id.in_(dg_ids)
        )
    )
    return {row.dg_id: row.player_name or f"Player {row.dg_id}" for row in result}


async def _get_bucket_players(pool_id: int, db: AsyncSession) -> dict[int, set[int]]:
    """Return {bucket_number: {dg_id, ...}} for a pool."""
    result = await db.execute(
        select(GolfPoolBucket.bucket_number, GolfPoolBucketPlayer.dg_id)
        .join(GolfPoolBucketPlayer, GolfPoolBucketPlayer.bucket_id == GolfPoolBucket.id)
        .where(GolfPoolBucket.pool_id == pool_id)
    )
    mapping: dict[int, set[int]] = {}
    for row in result:
        mapping.setdefault(row.bucket_number, set()).add(row.dg_id)
    return mapping


async def _count_entries_for_email(pool_id: int, email: str, db: AsyncSession) -> int:
    result = await db.execute(
        select(sa_func.count(GolfPoolEntry.id)).where(
            GolfPoolEntry.pool_id == pool_id,
            GolfPoolEntry.email == email.lower(),
        )
    )
    return result.scalar() or 0


async def _next_entry_number(pool_id: int, email: str, db: AsyncSession) -> int:
    result = await db.execute(
        select(sa_func.coalesce(sa_func.max(GolfPoolEntry.entry_number), 0)).where(
            GolfPoolEntry.pool_id == pool_id,
            GolfPoolEntry.email == email.lower(),
        )
    )
    return (result.scalar() or 0) + 1


async def _create_entry_and_picks(
    pool: GolfPool,
    email: str,
    entry_name: str | None,
    picks: list[PickRequest],
    player_names: dict[int, str],
    db: AsyncSession,
    *,
    source: str = "self_service",
    upload_filename: str | None = None,
) -> GolfPoolEntry:
    """Create a GolfPoolEntry + GolfPoolEntryPick rows atomically."""
    entry_number = await _next_entry_number(pool.id, email, db)
    entry = GolfPoolEntry(
        pool_id=pool.id,
        email=email.lower(),
        entry_name=entry_name,
        entry_number=entry_number,
        status="submitted",
        source=source,
        upload_filename=upload_filename,
        submitted_at=datetime.now(timezone.utc),
    )
    db.add(entry)
    await db.flush()
    await db.refresh(entry)

    for pk in picks:
        db.add(
            GolfPoolEntryPick(
                entry_id=entry.id,
                dg_id=pk.dg_id,
                player_name_snapshot=player_names.get(pk.dg_id, f"Player {pk.dg_id}"),
                pick_slot=pk.pick_slot,
                bucket_number=pk.bucket_number,
            )
        )
    await db.flush()
    return entry


async def _validate_entry_picks(
    pool: GolfPool,
    picks: list[PickRequest],
    player_names: dict[int, str],
    db: AsyncSession,
) -> list[str]:
    """Validate picks against pool rules.  Returns list of error strings."""
    rules_json = pool.rules_json or {}
    if not rules_json.get("variant"):
        return ["Pool has no rules configured"]

    rules = rules_from_json(rules_json)
    scoring_picks = [
        Pick(
            dg_id=pk.dg_id,
            player_name=player_names.get(pk.dg_id, f"Player {pk.dg_id}"),
            pick_slot=pk.pick_slot,
            bucket_number=pk.bucket_number,
        )
        for pk in picks
    ]

    # Build valid player set from tournament field
    field_result = await db.execute(
        select(GolfTournamentField.dg_id).where(
            GolfTournamentField.tournament_id == pool.tournament_id
        )
    )
    valid_dg_ids = {row.dg_id for row in field_result}

    bucket_players = None
    if rules.uses_buckets:
        bucket_players = await _get_bucket_players(pool.id, db)

    return validate_picks(scoring_picks, rules, valid_dg_ids, bucket_players)


# ---------------------------------------------------------------------------
# Public endpoints
# ---------------------------------------------------------------------------


@router.get("/pools")
async def list_pools(
    club_code: str | None = Query(None, description="Filter by club code"),
    tournament_id: int | None = Query(None, description="Filter by tournament"),
    status: str | None = Query(None, description="Filter by status"),
    active_only: bool = Query(False, description="Only open/live pools"),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """List golf pools with optional filters."""
    stmt = select(GolfPool).order_by(GolfPool.created_at.desc()).limit(limit)

    if club_code:
        stmt = stmt.where(GolfPool.club_code == club_code)
    if tournament_id is not None:
        stmt = stmt.where(GolfPool.tournament_id == tournament_id)
    if status:
        stmt = stmt.where(GolfPool.status == status)
    if active_only:
        stmt = stmt.where(GolfPool.status.in_(["open", "live"]))

    result = await db.execute(stmt)
    rows = result.scalars().all()
    return {
        "pools": [_serialize_pool(p) for p in rows],
        "count": len(rows),
    }


@router.get("/pools/{pool_id}")
async def get_pool(
    pool_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get pool detail with rules and tournament info."""
    pool = await _get_pool_or_404(pool_id, db)

    # Fetch tournament name for convenience
    t_result = await db.execute(
        select(GolfTournament.event_name, GolfTournament.event_id).where(
            GolfTournament.id == pool.tournament_id
        )
    )
    tournament = t_result.one_or_none()

    data = _serialize_pool(pool)
    data["tournament"] = {
        "event_name": tournament.event_name if tournament else None,
        "event_id": tournament.event_id if tournament else None,
    }
    return data


@router.get("/pools/{pool_id}/field")
async def get_pool_field(
    pool_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get the player field for a pool.

    For bucketed pools (Crestmont), returns players grouped by bucket.
    For flat pools (RVCC), returns a flat list.
    """
    pool = await _get_pool_or_404(pool_id, db)
    rules_json = pool.rules_json or {}
    uses_buckets = rules_json.get("uses_buckets", False)

    if uses_buckets:
        # Bucketed field
        bucket_result = await db.execute(
            select(GolfPoolBucket).where(GolfPoolBucket.pool_id == pool_id).order_by(
                GolfPoolBucket.bucket_number
            )
        )
        buckets = bucket_result.scalars().all()

        bucket_data = []
        for b in buckets:
            player_result = await db.execute(
                select(GolfPoolBucketPlayer).where(
                    GolfPoolBucketPlayer.bucket_id == b.id
                )
            )
            players = player_result.scalars().all()
            bucket_data.append({
                "bucket_number": b.bucket_number,
                "label": b.label,
                "players": [
                    {"dg_id": pl.dg_id, "player_name": pl.player_name_snapshot}
                    for pl in players
                ],
            })

        return {
            "pool_id": pool_id,
            "format": "bucketed",
            "buckets": bucket_data,
        }

    # Flat field from tournament
    stmt = select(GolfTournamentField).where(
        GolfTournamentField.tournament_id == pool.tournament_id
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return {
        "pool_id": pool_id,
        "format": "flat",
        "field": [
            {
                "dg_id": f.dg_id,
                "player_name": f.player_name,
                "status": f.status,
            }
            for f in rows
        ],
        "count": len(rows),
    }


@router.post("/pools/{pool_id}/entries")
async def submit_entry(
    pool_id: int,
    req: EntrySubmitRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Submit a pool entry with picks."""
    pool = await _get_pool_or_404(pool_id, db)

    # Check pool is accepting entries
    if pool.status not in ("open", "draft"):
        raise HTTPException(status_code=400, detail="Pool is not accepting entries")

    # Check deadline
    if pool.entry_deadline:
        now = datetime.now(timezone.utc)
        if now > pool.entry_deadline:
            raise HTTPException(status_code=400, detail="Entry deadline has passed")

    # Check max entries per email
    if pool.max_entries_per_email:
        count = await _count_entries_for_email(pool_id, req.email, db)
        if count >= pool.max_entries_per_email:
            raise HTTPException(
                status_code=400,
                detail=f"Maximum {pool.max_entries_per_email} entries per email reached",
            )

    # Resolve player names
    dg_ids = [pk.dg_id for pk in req.picks]
    player_names = await _get_player_names(dg_ids, db)

    # Validate picks
    errors = await _validate_entry_picks(pool, req.picks, player_names, db)
    if errors:
        raise HTTPException(status_code=422, detail={"validation_errors": errors})

    entry = await _create_entry_and_picks(pool, req.email, req.entry_name, req.picks, player_names, db)

    return {"status": "submitted", "entry": _serialize_entry(entry)}


@router.get("/pools/{pool_id}/entries/by-email")
async def get_entries_by_email(
    pool_id: int,
    email: str = Query(..., description="Email to look up"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get all entries for an email address in a pool."""
    await _get_pool_or_404(pool_id, db)

    stmt = select(GolfPoolEntry).where(
        GolfPoolEntry.pool_id == pool_id,
        GolfPoolEntry.email == email.lower(),
    ).order_by(GolfPoolEntry.entry_number)
    result = await db.execute(stmt)
    entries = result.scalars().all()

    entries_data = []
    for entry in entries:
        picks_result = await db.execute(
            select(GolfPoolEntryPick).where(GolfPoolEntryPick.entry_id == entry.id).order_by(
                GolfPoolEntryPick.pick_slot
            )
        )
        picks = picks_result.scalars().all()
        entry_dict = _serialize_entry(entry)
        entry_dict["picks"] = [_serialize_pick(pk) for pk in picks]
        entries_data.append(entry_dict)

    return {"entries": entries_data, "count": len(entries_data)}


@router.get("/pools/{pool_id}/leaderboard")
async def get_pool_leaderboard(
    pool_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get the materialized leaderboard for a pool."""
    await _get_pool_or_404(pool_id, db)

    # Fetch entry scores ordered by rank
    stmt = (
        select(GolfPoolEntryScore, GolfPoolEntry.email, GolfPoolEntry.entry_name)
        .join(GolfPoolEntry, GolfPoolEntry.id == GolfPoolEntryScore.entry_id)
        .where(GolfPoolEntryScore.pool_id == pool_id)
        .order_by(
            GolfPoolEntryScore.rank.asc().nullslast(),
            GolfPoolEntryScore.aggregate_score.asc().nullslast(),
        )
    )
    result = await db.execute(stmt)
    rows = result.all()

    leaderboard = []
    for score, email, entry_name in rows:
        # Fetch per-golfer detail
        player_result = await db.execute(
            select(GolfPoolEntryScorePlayer).where(
                GolfPoolEntryScorePlayer.entry_id == score.entry_id,
                GolfPoolEntryScorePlayer.pool_id == pool_id,
            ).order_by(GolfPoolEntryScorePlayer.pick_slot)
        )
        players = player_result.scalars().all()

        leaderboard.append({
            "entry_id": score.entry_id,
            "email": email,
            "entry_name": entry_name,
            "aggregate_score": score.aggregate_score,
            "qualified_golfers_count": score.qualified_golfers_count,
            "counted_golfers_count": score.counted_golfers_count,
            "qualification_status": score.qualification_status,
            "is_complete": score.is_complete,
            "rank": score.rank,
            "is_tied": score.is_tied,
            "last_scored_at": score.last_scored_at.isoformat() if score.last_scored_at else None,
            "players": [
                {
                    "dg_id": sp.dg_id,
                    "player_name": sp.player_name_snapshot,
                    "pick_slot": sp.pick_slot,
                    "bucket_number": sp.bucket_number,
                    "status": sp.status_snapshot,
                    "position": sp.position_snapshot,
                    "total_score": sp.total_score_snapshot,
                    "thru": sp.thru_snapshot,
                    "r1": sp.r1,
                    "r2": sp.r2,
                    "r3": sp.r3,
                    "r4": sp.r4,
                    "made_cut": sp.made_cut_snapshot,
                    "counts_toward_total": sp.counts_toward_total,
                    "is_dropped": sp.is_dropped,
                }
                for sp in players
            ],
        })

    return {"pool_id": pool_id, "leaderboard": leaderboard, "count": len(leaderboard)}


@router.get("/pools/{pool_id}/entries/{entry_id}")
async def get_entry_detail(
    pool_id: int,
    entry_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get entry detail with picks and scoring."""
    await _get_pool_or_404(pool_id, db)

    entry_result = await db.execute(
        select(GolfPoolEntry).where(
            GolfPoolEntry.id == entry_id,
            GolfPoolEntry.pool_id == pool_id,
        )
    )
    entry = entry_result.scalar_one_or_none()
    if entry is None:
        raise HTTPException(status_code=404, detail="Entry not found")

    # Picks
    picks_result = await db.execute(
        select(GolfPoolEntryPick).where(GolfPoolEntryPick.entry_id == entry_id).order_by(
            GolfPoolEntryPick.pick_slot
        )
    )
    picks = picks_result.scalars().all()

    # Scoring (may not exist yet)
    score_result = await db.execute(
        select(GolfPoolEntryScore).where(GolfPoolEntryScore.entry_id == entry_id)
    )
    score = score_result.scalar_one_or_none()

    score_players = []
    if score:
        sp_result = await db.execute(
            select(GolfPoolEntryScorePlayer).where(
                GolfPoolEntryScorePlayer.entry_id == entry_id
            ).order_by(GolfPoolEntryScorePlayer.pick_slot)
        )
        score_players = sp_result.scalars().all()

    data = _serialize_entry(entry)
    data["picks"] = [_serialize_pick(pk) for pk in picks]
    data["scoring"] = None
    if score:
        data["scoring"] = {
            "aggregate_score": score.aggregate_score,
            "qualified_golfers_count": score.qualified_golfers_count,
            "counted_golfers_count": score.counted_golfers_count,
            "qualification_status": score.qualification_status,
            "is_complete": score.is_complete,
            "rank": score.rank,
            "is_tied": score.is_tied,
            "last_scored_at": score.last_scored_at.isoformat() if score.last_scored_at else None,
            "players": [
                {
                    "dg_id": sp.dg_id,
                    "player_name": sp.player_name_snapshot,
                    "pick_slot": sp.pick_slot,
                    "bucket_number": sp.bucket_number,
                    "status": sp.status_snapshot,
                    "position": sp.position_snapshot,
                    "total_score": sp.total_score_snapshot,
                    "thru": sp.thru_snapshot,
                    "r1": sp.r1,
                    "r2": sp.r2,
                    "r3": sp.r3,
                    "r4": sp.r4,
                    "made_cut": sp.made_cut_snapshot,
                    "counts_toward_total": sp.counts_toward_total,
                    "is_dropped": sp.is_dropped,
                }
                for sp in score_players
            ],
        }
    return data


# ---------------------------------------------------------------------------
# Admin endpoints
# ---------------------------------------------------------------------------


@router.post("/pools")
async def create_pool(
    req: PoolCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Create a new golf pool."""
    # Verify tournament exists
    t_result = await db.execute(
        select(GolfTournament.id).where(GolfTournament.id == req.tournament_id)
    )
    if t_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Tournament not found")

    pool = GolfPool(
        code=req.code,
        name=req.name,
        club_code=req.club_code,
        tournament_id=req.tournament_id,
        status=req.status,
        rules_json=req.rules_json,
        entry_deadline=datetime.fromisoformat(req.entry_deadline) if req.entry_deadline else None,
        entry_open_at=datetime.fromisoformat(req.entry_open_at) if req.entry_open_at else None,
        max_entries_per_email=req.max_entries_per_email,
        scoring_enabled=req.scoring_enabled,
        require_upload=req.require_upload,
        allow_self_service_entry=req.allow_self_service_entry,
        notes=req.notes,
    )
    db.add(pool)
    await db.flush()
    await db.refresh(pool)
    return {"status": "created", **_serialize_pool(pool)}


@router.patch("/pools/{pool_id}")
async def update_pool(
    pool_id: int,
    req: PoolUpdateRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Update a pool."""
    pool = await _get_pool_or_404(pool_id, db)

    if req.name is not None:
        pool.name = req.name
    if req.status is not None:
        pool.status = req.status
    if req.rules_json is not None:
        pool.rules_json = req.rules_json
    if req.entry_deadline is not None:
        pool.entry_deadline = datetime.fromisoformat(req.entry_deadline)
    if req.entry_open_at is not None:
        pool.entry_open_at = datetime.fromisoformat(req.entry_open_at)
    if req.max_entries_per_email is not None:
        pool.max_entries_per_email = req.max_entries_per_email
    if req.scoring_enabled is not None:
        pool.scoring_enabled = req.scoring_enabled
    if req.require_upload is not None:
        pool.require_upload = req.require_upload
    if req.allow_self_service_entry is not None:
        pool.allow_self_service_entry = req.allow_self_service_entry
    if req.notes is not None:
        pool.notes = req.notes

    await db.flush()
    await db.refresh(pool)
    return {"status": "updated", **_serialize_pool(pool)}


@router.delete("/pools/{pool_id}")
async def delete_pool(
    pool_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Delete a pool and all related data (cascades)."""
    pool = await _get_pool_or_404(pool_id, db)
    name = pool.name
    await db.delete(pool)
    return {"status": "deleted", "id": pool_id, "name": name}


@router.post("/pools/{pool_id}/buckets")
async def create_or_replace_buckets(
    pool_id: int,
    req: BucketCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Create or replace bucket assignments for a pool (Crestmont)."""
    pool = await _get_pool_or_404(pool_id, db)

    # Delete existing buckets (cascade deletes bucket_players too)
    existing = await db.execute(
        select(GolfPoolBucket.id).where(GolfPoolBucket.pool_id == pool_id)
    )
    existing_ids = [row.id for row in existing]
    if existing_ids:
        await db.execute(
            delete(GolfPoolBucketPlayer).where(
                GolfPoolBucketPlayer.bucket_id.in_(existing_ids)
            )
        )
        await db.execute(
            delete(GolfPoolBucket).where(GolfPoolBucket.pool_id == pool_id)
        )
        await db.flush()

    created_count = 0
    for bucket_item in req.buckets:
        bucket = GolfPoolBucket(
            pool_id=pool.id,
            bucket_number=bucket_item.bucket_number,
            label=bucket_item.label,
        )
        db.add(bucket)
        await db.flush()
        await db.refresh(bucket)

        for player in bucket_item.players:
            db.add(
                GolfPoolBucketPlayer(
                    bucket_id=bucket.id,
                    dg_id=player.dg_id,
                    player_name_snapshot=player.player_name,
                )
            )
            created_count += 1

    await db.flush()
    return {
        "status": "created",
        "pool_id": pool_id,
        "buckets_count": len(req.buckets),
        "players_count": created_count,
    }


@router.get("/pools/{pool_id}/entries")
async def admin_list_entries(
    pool_id: int,
    email: str | None = Query(None, description="Filter by email"),
    status: str | None = Query(None, description="Filter by status"),
    source: str | None = Query(None, description="Filter by source"),
    limit: int = Query(200, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Admin: list all entries for a pool with optional filters."""
    await _get_pool_or_404(pool_id, db)

    stmt = (
        select(GolfPoolEntry)
        .where(GolfPoolEntry.pool_id == pool_id)
        .order_by(GolfPoolEntry.created_at.desc())
        .limit(limit)
    )
    if email:
        stmt = stmt.where(GolfPoolEntry.email == email.lower())
    if status:
        stmt = stmt.where(GolfPoolEntry.status == status)
    if source:
        stmt = stmt.where(GolfPoolEntry.source == source)

    result = await db.execute(stmt)
    entries = result.scalars().all()
    return {
        "entries": [_serialize_entry(e) for e in entries],
        "count": len(entries),
    }


@router.post("/pools/{pool_id}/rescore")
async def trigger_rescore(
    pool_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Trigger manual rescoring for a pool via Celery."""
    pool = await _get_pool_or_404(pool_id, db)

    from app.celery_client import get_celery_app

    celery = get_celery_app()
    task = celery.send_task(
        "rescore_golf_pool",
        args=[pool_id],
        queue="sports-scraper",
    )
    return {
        "status": "dispatched",
        "pool_id": pool_id,
        "task_id": task.id,
    }


@router.post("/pools/{pool_id}/lock")
async def lock_pool(
    pool_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Lock pool entries (set status to locked)."""
    pool = await _get_pool_or_404(pool_id, db)
    pool.status = "locked"
    await db.flush()
    await db.refresh(pool)
    return {"status": "locked", **_serialize_pool(pool)}


@router.post("/pools/{pool_id}/entries/upload")
async def upload_entries_csv(
    pool_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Bulk import entries from a CSV file.

    Expected CSV columns: email, entry_name, pick_1, pick_2, ..., pick_N
    where pick values are dg_id integers.  For bucketed pools, use
    pick_1_bucket, pick_2_bucket, ... for bucket assignments.
    """
    pool = await _get_pool_or_404(pool_id, db)
    rules_json = pool.rules_json or {}
    variant = rules_json.get("variant", "")
    uses_buckets = rules_json.get("uses_buckets", False)
    pick_count = rules_json.get("pick_count", 7)

    content = await file.read()
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))

    results: list[dict[str, Any]] = []
    created_count = 0
    error_count = 0

    # Build valid player set
    field_result = await db.execute(
        select(GolfTournamentField.dg_id).where(
            GolfTournamentField.tournament_id == pool.tournament_id
        )
    )
    valid_dg_ids = {row.dg_id for row in field_result}

    # Build player names lookup
    all_dg_ids = list(valid_dg_ids)
    player_names = await _get_player_names(all_dg_ids, db)

    for row_num, row in enumerate(reader, start=2):  # start=2 for 1-indexed + header
        row_errors: list[str] = []
        email = (row.get("email") or "").strip().lower()
        entry_name = (row.get("entry_name") or "").strip() or None

        if not email:
            row_errors.append("Missing email")
            results.append({"row": row_num, "status": "error", "errors": row_errors})
            error_count += 1
            continue

        # Parse picks
        picks: list[PickRequest] = []
        for slot in range(1, pick_count + 1):
            dg_id_str = (row.get(f"pick_{slot}") or "").strip()
            if not dg_id_str:
                row_errors.append(f"Missing pick_{slot}")
                continue
            try:
                dg_id = int(dg_id_str)
            except ValueError:
                row_errors.append(f"Invalid pick_{slot}: {dg_id_str}")
                continue

            bucket_number = None
            if uses_buckets:
                bucket_str = (row.get(f"pick_{slot}_bucket") or "").strip()
                if bucket_str:
                    try:
                        bucket_number = int(bucket_str)
                    except ValueError:
                        row_errors.append(f"Invalid pick_{slot}_bucket: {bucket_str}")
                        continue

            picks.append(PickRequest(dg_id=dg_id, pick_slot=slot, bucket_number=bucket_number))

        if row_errors:
            results.append({"row": row_num, "status": "error", "errors": row_errors})
            error_count += 1
            continue

        # Validate picks against rules
        validation_errors = await _validate_entry_picks(pool, picks, player_names, db)
        if validation_errors:
            results.append({"row": row_num, "status": "error", "errors": validation_errors})
            error_count += 1
            continue

        # Check max entries per email
        if pool.max_entries_per_email:
            count = await _count_entries_for_email(pool_id, email, db)
            if count >= pool.max_entries_per_email:
                results.append({
                    "row": row_num,
                    "status": "error",
                    "errors": [f"Max entries ({pool.max_entries_per_email}) reached for {email}"],
                })
                error_count += 1
                continue

        entry = await _create_entry_and_picks(
            pool, email, entry_name, picks, player_names, db,
            source="csv_upload", upload_filename=file.filename,
        )
        results.append({"row": row_num, "status": "created", "entry_id": entry.id})
        created_count += 1

    return {
        "status": "completed",
        "pool_id": pool_id,
        "filename": file.filename,
        "created": created_count,
        "errors": error_count,
        "total_rows": created_count + error_count,
        "details": results,
    }
