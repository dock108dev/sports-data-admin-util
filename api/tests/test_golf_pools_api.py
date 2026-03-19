"""Tests for golf pool ORM models, helpers, and scoring edge cases.

Covers:
- Import of all golf ORM models (app.db.golf, app.db.golf_pools)
- Serializers: serialize_pool, serialize_entry, serialize_pick
- validate_entry_picks with mocked DB
- Scoring edge cases not covered by test_golf_pool_scoring.py
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# -----------------------------------------------------------------------
# Import all ORM models to boost coverage on app/db/golf.py (0%) and
# app/db/golf_pools.py
# -----------------------------------------------------------------------
from app.db.golf import (  # noqa: F401
    GolfDFSProjection,
    GolfLeaderboard,
    GolfPlayer,
    GolfPlayerStats,
    GolfRound,
    GolfTournament,
    GolfTournamentField,
    GolfTournamentOdds,
)
from app.db.golf_pools import (  # noqa: F401
    GolfPool,
    GolfPoolBucket,
    GolfPoolBucketPlayer,
    GolfPoolEntry,
    GolfPoolEntryPick,
    GolfPoolEntryScore,
    GolfPoolEntryScorePlayer,
    GolfPoolScoreRun,
)
from app.routers.golf.pools_helpers import (
    PickRequest,
    serialize_entry,
    serialize_pick,
    serialize_pool,
    validate_entry_picks,
)
from app.services.golf_pool_scoring import (
    CRESTMONT_RULES,
    RVCC_RULES,
    Entry,
    GolferScore,
    Pick,
    PoolRules,
    ScoredEntry,
    _any_rounds_pending,
    get_rules,
    rank_entries,
    rules_from_json,
    score_entry,
    validate_picks,
)


# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------

def _pool_obj(**overrides):
    """Return a mock GolfPool-like object with sensible defaults."""
    defaults = dict(
        id=1,
        code="test-pool",
        name="Test Pool",
        club_code="rvcc",
        tournament_id=10,
        status="open",
        rules_json={"variant": "rvcc"},
        entry_open_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
        entry_deadline=datetime(2026, 3, 15, tzinfo=timezone.utc),
        scoring_enabled=False,
        max_entries_per_email=3,
        require_upload=False,
        allow_self_service_entry=True,
        notes="some notes",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _entry_obj(**overrides):
    """Return a mock GolfPoolEntry-like object."""
    defaults = dict(
        id=100,
        pool_id=1,
        email="alice@example.com",
        entry_name="Alice's Entry",
        entry_number=1,
        status="submitted",
        source="self_service",
        submitted_at=datetime(2026, 3, 10, tzinfo=timezone.utc),
        created_at=datetime(2026, 3, 10, tzinfo=timezone.utc),
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _pick_obj(**overrides):
    """Return a mock GolfPoolEntryPick-like object."""
    defaults = dict(
        id=200,
        dg_id=42,
        player_name_snapshot="Tiger Woods",
        pick_slot=1,
        bucket_number=None,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


# -----------------------------------------------------------------------
# Serializer tests
# -----------------------------------------------------------------------

class TestSerializePool:
    def test_full_pool(self):
        p = _pool_obj()
        result = serialize_pool(p)
        assert result["id"] == 1
        assert result["code"] == "test-pool"
        assert result["name"] == "Test Pool"
        assert result["club_code"] == "rvcc"
        assert result["tournament_id"] == 10
        assert result["status"] == "open"
        assert result["rules_json"] == {"variant": "rvcc"}
        assert result["entry_open_at"] == "2026-03-01T00:00:00+00:00"
        assert result["entry_deadline"] == "2026-03-15T00:00:00+00:00"
        assert result["scoring_enabled"] is False
        assert result["max_entries_per_email"] == 3
        assert result["require_upload"] is False
        assert result["allow_self_service_entry"] is True
        assert result["notes"] == "some notes"
        assert result["created_at"] is not None
        assert result["updated_at"] is not None

    def test_pool_with_none_dates(self):
        p = _pool_obj(entry_open_at=None, entry_deadline=None, created_at=None, updated_at=None)
        result = serialize_pool(p)
        assert result["entry_open_at"] is None
        assert result["entry_deadline"] is None
        assert result["created_at"] is None
        assert result["updated_at"] is None


class TestSerializeEntry:
    def test_full_entry(self):
        e = _entry_obj()
        result = serialize_entry(e)
        assert result["id"] == 100
        assert result["pool_id"] == 1
        assert result["email"] == "alice@example.com"
        assert result["entry_name"] == "Alice's Entry"
        assert result["entry_number"] == 1
        assert result["status"] == "submitted"
        assert result["source"] == "self_service"
        assert result["submitted_at"] == "2026-03-10T00:00:00+00:00"

    def test_entry_with_none_dates(self):
        e = _entry_obj(submitted_at=None, created_at=None)
        result = serialize_entry(e)
        assert result["submitted_at"] is None
        assert result["created_at"] is None


class TestSerializePick:
    def test_full_pick(self):
        pk = _pick_obj()
        result = serialize_pick(pk)
        assert result["id"] == 200
        assert result["dg_id"] == 42
        assert result["player_name"] == "Tiger Woods"
        assert result["pick_slot"] == 1
        assert result["bucket_number"] is None

    def test_pick_with_bucket(self):
        pk = _pick_obj(bucket_number=3)
        result = serialize_pick(pk)
        assert result["bucket_number"] == 3


# -----------------------------------------------------------------------
# validate_entry_picks (async, mocked DB)
# -----------------------------------------------------------------------

class TestValidateEntryPicks:
    @pytest.mark.asyncio
    async def test_no_rules_configured(self):
        pool = _pool_obj(rules_json={})
        db = AsyncMock()
        errors = await validate_entry_picks(pool, [], {}, db)
        assert errors == ["Pool has no rules configured"]

    @pytest.mark.asyncio
    async def test_no_rules_json_at_all(self):
        pool = _pool_obj(rules_json=None)
        db = AsyncMock()
        errors = await validate_entry_picks(pool, [], {}, db)
        assert errors == ["Pool has no rules configured"]

    @pytest.mark.asyncio
    async def test_valid_rvcc_picks(self):
        pool = _pool_obj(rules_json={"variant": "rvcc"})
        picks = [PickRequest(dg_id=i, pick_slot=i) for i in range(1, 8)]
        player_names = {i: f"Player {i}" for i in range(1, 8)}

        # Mock the field query to return all 7 dg_ids as valid
        mock_field_result = MagicMock()
        mock_field_result.__iter__ = MagicMock(
            return_value=iter([SimpleNamespace(dg_id=i) for i in range(1, 8)])
        )

        db = AsyncMock()
        db.execute = AsyncMock(return_value=mock_field_result)

        errors = await validate_entry_picks(pool, picks, player_names, db)
        assert errors == []

    @pytest.mark.asyncio
    async def test_wrong_pick_count(self):
        pool = _pool_obj(rules_json={"variant": "rvcc"})
        picks = [PickRequest(dg_id=i, pick_slot=i) for i in range(1, 4)]  # only 3
        player_names = {i: f"Player {i}" for i in range(1, 4)}

        mock_field_result = MagicMock()
        mock_field_result.__iter__ = MagicMock(
            return_value=iter([SimpleNamespace(dg_id=i) for i in range(1, 4)])
        )

        db = AsyncMock()
        db.execute = AsyncMock(return_value=mock_field_result)

        errors = await validate_entry_picks(pool, picks, player_names, db)
        assert any("Expected 7" in e for e in errors)

    @pytest.mark.asyncio
    async def test_crestmont_with_buckets(self):
        pool = _pool_obj(rules_json={"variant": "crestmont"}, tournament_id=10)
        picks = [PickRequest(dg_id=i, pick_slot=i, bucket_number=i) for i in range(1, 7)]
        player_names = {i: f"Player {i}" for i in range(1, 7)}

        # First call: field query; Second call: bucket query
        mock_field_result = MagicMock()
        mock_field_result.__iter__ = MagicMock(
            return_value=iter([SimpleNamespace(dg_id=i) for i in range(1, 7)])
        )

        mock_bucket_result = MagicMock()
        mock_bucket_result.__iter__ = MagicMock(
            return_value=iter(
                [SimpleNamespace(bucket_number=i, dg_id=i) for i in range(1, 7)]
            )
        )

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[mock_field_result, mock_bucket_result])

        errors = await validate_entry_picks(pool, picks, player_names, db)
        assert errors == []


# -----------------------------------------------------------------------
# Scoring edge cases not covered in test_golf_pool_scoring.py
# -----------------------------------------------------------------------

def _gs(dg_id, name, total, status="active", **kw):
    return GolferScore(dg_id=dg_id, player_name=name, status=status, total_score=total, **kw)


def _pick_s(dg_id, name, slot, bucket=None):
    return Pick(dg_id=dg_id, player_name=name, pick_slot=slot, bucket_number=bucket)


class TestScoringEdgeCases:
    def test_all_golfers_missing_from_leaderboard(self):
        """Every pick is unknown — pending because cut not settled."""
        picks = [_pick_s(i, f"P{i}", i) for i in range(1, 8)]
        entry = Entry(entry_id=1, email="x@x.com", entry_name="X", picks=picks)
        result = score_entry(entry, {}, RVCC_RULES)

        assert result.qualification_status == "pending"
        assert result.aggregate_score is None
        assert result.qualified_golfers_count == 0
        assert all(p.status == "unknown" for p in result.picks)

    def test_golfer_with_none_total_score(self):
        """Active golfer but total_score is None (hasn't started)."""
        scores = {
            i: _gs(i, f"P{i}", total=-5 + i) for i in range(1, 7)
        }
        scores[7] = GolferScore(
            dg_id=7, player_name="P7", status="active", total_score=None
        )
        picks = [_pick_s(i, f"P{i}", i) for i in range(1, 8)]
        entry = Entry(entry_id=1, email="x@x.com", entry_name="X", picks=picks)
        result = score_entry(entry, scores, RVCC_RULES)

        # All 7 active, but one has None total_score -> sort_score = 999
        assert result.qualified_golfers_count == 7
        assert result.qualification_status == "qualified"
        # The None-score golfer should be dropped (worst of 7)
        p7 = [p for p in result.picks if p.dg_id == 7][0]
        assert p7.sort_score == 999

    def test_completeness_with_thru_18(self):
        """All counted golfers have thru=18 — is_complete should be True."""
        scores = {
            i: _gs(i, f"P{i}", total=-5 + i, thru=18, r1=-3, r2=-2) for i in range(1, 8)
        }
        picks = [_pick_s(i, f"P{i}", i) for i in range(1, 8)]
        entry = Entry(entry_id=1, email="x@x.com", entry_name="X", picks=picks)
        result = score_entry(entry, scores, RVCC_RULES)
        assert result.is_complete is True

    def test_completeness_mid_round(self):
        """A counted golfer has thru=10 — is_complete should be False."""
        scores = {}
        for i in range(1, 8):
            scores[i] = _gs(i, f"P{i}", total=-5 + i, thru=18, r1=-3, r2=-2)
        scores[1] = _gs(1, "P1", total=-4, thru=10, r1=-3, r2=-2)
        picks = [_pick_s(i, f"P{i}", i) for i in range(1, 8)]
        entry = Entry(entry_id=1, email="x@x.com", entry_name="X", picks=picks)
        result = score_entry(entry, scores, RVCC_RULES)
        assert result.is_complete is False

    def test_aggregate_none_when_no_counted(self):
        """No eligible golfers — aggregate should be None."""
        scores = {
            i: _gs(i, f"P{i}", total=5, status="cut", r1=3, r2=5) for i in range(1, 8)
        }
        picks = [_pick_s(i, f"P{i}", i) for i in range(1, 8)]
        entry = Entry(entry_id=1, email="x@x.com", entry_name="X", picks=picks)
        result = score_entry(entry, scores, RVCC_RULES)
        assert result.aggregate_score is None
        assert result.counted_golfers_count == 0

    def test_score_entry_best_5_selection(self):
        """Verify best 5 of 7 are selected correctly with varied scores."""
        scores = {
            1: _gs(1, "P1", -10),
            2: _gs(2, "P2", -8),
            3: _gs(3, "P3", +5),  # Bad
            4: _gs(4, "P4", -3),
            5: _gs(5, "P5", -1),
            6: _gs(6, "P6", +10),  # Worst
            7: _gs(7, "P7", -6),
        }
        picks = [_pick_s(i, f"P{i}", i) for i in range(1, 8)]
        entry = Entry(entry_id=1, email="x@x.com", entry_name="X", picks=picks)
        result = score_entry(entry, scores, RVCC_RULES)

        counted_ids = {p.dg_id for p in result.picks if p.counts_toward_total}
        # Best 5: -10, -8, -6, -3, -1 -> players 1,2,7,4,5
        assert counted_ids == {1, 2, 4, 5, 7}
        assert result.aggregate_score == -10 + -8 + -6 + -3 + -1  # -28

    def test_rules_from_json_with_overrides(self):
        """rules_from_json should let JSON override defaults."""
        rules = rules_from_json({
            "variant": "rvcc",
            "pick_count": 8,
            "count_best": 6,
            "min_cuts_to_qualify": 6,
        })
        assert rules.pick_count == 8
        assert rules.count_best == 6
        assert rules.min_cuts_to_qualify == 6
        assert rules.uses_buckets is False  # default from rvcc

    def test_rules_from_json_minimal(self):
        """rules_from_json with just variant uses all defaults."""
        rules = rules_from_json({"variant": "crestmont"})
        assert rules == CRESTMONT_RULES


class TestAnyRoundsPending:
    def test_all_rounds_complete(self):
        picks = [_pick_s(1, "P1", 1), _pick_s(2, "P2", 2)]
        scores = {
            1: _gs(1, "P1", -5, r1=-3, r2=-2),
            2: _gs(2, "P2", -3, r1=-2, r2=-1),
        }
        assert _any_rounds_pending(scores, picks) is False

    def test_golfer_missing_from_scores(self):
        picks = [_pick_s(1, "P1", 1), _pick_s(2, "P2", 2)]
        scores = {1: _gs(1, "P1", -5, r1=-3, r2=-2)}
        assert _any_rounds_pending(scores, picks) is True

    def test_active_with_r2_none(self):
        picks = [_pick_s(1, "P1", 1)]
        scores = {1: _gs(1, "P1", -5, r1=-3, r2=None)}
        assert _any_rounds_pending(scores, picks) is True

    def test_cut_with_r2_none_not_pending(self):
        """Cut golfer with r2=None is NOT pending (status overrides)."""
        picks = [_pick_s(1, "P1", 1)]
        scores = {1: _gs(1, "P1", 5, status="cut", r1=3, r2=None)}
        # cut status means not active, so r2=None check doesn't fire
        assert _any_rounds_pending(scores, picks) is False


class TestValidatePicksEdgeCases:
    def test_crestmont_missing_bucket_assignment(self):
        """Picks without bucket_number on a bucket variant."""
        picks = [_pick_s(i, f"P{i}", i, bucket=None) for i in range(1, 7)]
        bucket_players = {i: {i} for i in range(1, 7)}
        errors = validate_picks(picks, CRESTMONT_RULES, bucket_players=bucket_players)
        assert any("missing bucket assignment" in e for e in errors)

    def test_crestmont_no_bucket_players_provided(self):
        """Bucket variant with no bucket_players map is an error."""
        picks = [_pick_s(i, f"P{i}", i, bucket=i) for i in range(1, 7)]
        errors = validate_picks(picks, CRESTMONT_RULES, bucket_players=None)
        assert any("Bucket assignments required" in e for e in errors)

    def test_no_errors_when_valid_ids_none(self):
        """When valid_dg_ids is None, skip that check entirely."""
        picks = [_pick_s(i, f"P{i}", i) for i in range(1, 8)]
        errors = validate_picks(picks, RVCC_RULES, valid_dg_ids=None)
        assert errors == []


class TestRankingEdgeCases:
    def test_three_way_tie(self):
        entries = [
            ScoredEntry(
                entry_id=i, email=f"{i}@x.com", entry_name=f"E{i}", picks=[],
                aggregate_score=-20, qualified_golfers_count=5,
                counted_golfers_count=5, qualification_status="qualified",
                is_complete=True,
            )
            for i in range(1, 4)
        ]
        ranked = rank_entries(entries)
        assert all(e.rank == 1 for e in ranked)
        assert all(e.is_tied for e in ranked)

    def test_empty_entries(self):
        ranked = rank_entries([])
        assert ranked == []

    def test_mixed_qualified_pending_not_qualified(self):
        """Verify ordering: qualified, pending, not_qualified."""
        entries = [
            ScoredEntry(entry_id=1, email="a@x.com", entry_name="A", picks=[],
                        aggregate_score=None, qualified_golfers_count=3,
                        counted_golfers_count=3, qualification_status="not_qualified",
                        is_complete=True),
            ScoredEntry(entry_id=2, email="b@x.com", entry_name="B", picks=[],
                        aggregate_score=-10, qualified_golfers_count=5,
                        counted_golfers_count=5, qualification_status="pending",
                        is_complete=False),
            ScoredEntry(entry_id=3, email="c@x.com", entry_name="C", picks=[],
                        aggregate_score=-20, qualified_golfers_count=5,
                        counted_golfers_count=5, qualification_status="qualified",
                        is_complete=True),
        ]
        ranked = rank_entries(entries)
        assert ranked[0].qualification_status == "qualified"
        assert ranked[1].qualification_status == "pending"
        assert ranked[2].qualification_status == "not_qualified"
        assert ranked[0].rank == 1
        assert ranked[2].rank is None


class TestPydanticModels:
    """Verify Pydantic request models from pools_helpers parse correctly."""

    def test_pick_request_defaults(self):
        pr = PickRequest(dg_id=42, pick_slot=1)
        assert pr.dg_id == 42
        assert pr.pick_slot == 1
        assert pr.bucket_number is None

    def test_pick_request_with_bucket(self):
        pr = PickRequest(dg_id=42, pick_slot=1, bucket_number=3)
        assert pr.bucket_number == 3
