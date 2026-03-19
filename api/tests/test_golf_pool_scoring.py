"""Tests for golf pool scoring engine.

Covers RVCC and Crestmont variants with all edge cases.
"""

from __future__ import annotations

import pytest

from app.services.golf_pool_scoring import (
    CRESTMONT_RULES,
    RVCC_RULES,
    Entry,
    GolferScore,
    Pick,
    PoolRules,
    ScoredEntry,
    get_rules,
    rank_entries,
    rules_from_json,
    score_entry,
    score_pool,
    validate_picks,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _gs(dg_id: int, name: str, total: int, status: str = "active", **kw) -> GolferScore:
    return GolferScore(dg_id=dg_id, player_name=name, status=status, total_score=total, **kw)


def _pick(dg_id: int, name: str, slot: int, bucket: int | None = None) -> Pick:
    return Pick(dg_id=dg_id, player_name=name, pick_slot=slot, bucket_number=bucket)


def _entry(entry_id: int, picks: list[Pick], email: str = "test@example.com") -> Entry:
    return Entry(entry_id=entry_id, email=email, entry_name=f"Entry {entry_id}", picks=picks)


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------

class TestRules:
    def test_rvcc_rules(self):
        assert RVCC_RULES.pick_count == 7
        assert RVCC_RULES.count_best == 5
        assert RVCC_RULES.min_cuts_to_qualify == 5
        assert RVCC_RULES.uses_buckets is False

    def test_crestmont_rules(self):
        assert CRESTMONT_RULES.pick_count == 6
        assert CRESTMONT_RULES.count_best == 4
        assert CRESTMONT_RULES.min_cuts_to_qualify == 4
        assert CRESTMONT_RULES.uses_buckets is True

    def test_get_rules(self):
        assert get_rules("rvcc") == RVCC_RULES
        assert get_rules("RVCC") == RVCC_RULES
        assert get_rules("crestmont") == CRESTMONT_RULES

    def test_get_rules_unknown(self):
        with pytest.raises(ValueError, match="Unknown pool variant"):
            get_rules("unknown")

    def test_rules_from_json(self):
        rules = rules_from_json({"variant": "rvcc", "pick_count": 7, "count_best": 5,
                                  "min_cuts_to_qualify": 5, "uses_buckets": False})
        assert rules == RVCC_RULES


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

class TestValidation:
    def test_rvcc_valid_7_picks(self):
        picks = [_pick(i, f"P{i}", i) for i in range(1, 8)]
        errors = validate_picks(picks, RVCC_RULES)
        assert errors == []

    def test_rvcc_wrong_count(self):
        picks = [_pick(i, f"P{i}", i) for i in range(1, 6)]
        errors = validate_picks(picks, RVCC_RULES)
        assert any("Expected 7" in e for e in errors)

    def test_duplicate_picks_rejected(self):
        picks = [_pick(1, "Same", i) for i in range(1, 8)]
        errors = validate_picks(picks, RVCC_RULES)
        assert any("Duplicate" in e for e in errors)

    def test_invalid_player_rejected(self):
        picks = [_pick(i, f"P{i}", i) for i in range(1, 8)]
        valid_ids = {1, 2, 3, 4, 5, 6}  # Missing 7
        errors = validate_picks(picks, RVCC_RULES, valid_dg_ids=valid_ids)
        assert any("not in tournament field" in e for e in errors)

    def test_crestmont_valid_buckets(self):
        picks = [_pick(i, f"P{i}", i, bucket=i) for i in range(1, 7)]
        bucket_players = {i: {i} for i in range(1, 7)}
        errors = validate_picks(picks, CRESTMONT_RULES, bucket_players=bucket_players)
        assert errors == []

    def test_crestmont_wrong_bucket(self):
        picks = [_pick(i, f"P{i}", i, bucket=i) for i in range(1, 7)]
        bucket_players = {i: {i + 100} for i in range(1, 7)}  # Wrong players
        errors = validate_picks(picks, CRESTMONT_RULES, bucket_players=bucket_players)
        assert len(errors) == 6  # All 6 picks in wrong bucket

    def test_crestmont_duplicate_bucket(self):
        picks = [_pick(i, f"P{i}", i, bucket=1) for i in range(1, 7)]  # All bucket 1
        bucket_players = {1: set(range(1, 7))}
        errors = validate_picks(picks, CRESTMONT_RULES, bucket_players=bucket_players)
        assert any("used more than once" in e for e in errors)


# ---------------------------------------------------------------------------
# RVCC Scoring
# ---------------------------------------------------------------------------

class TestRVCCScoring:
    def test_happy_path_all_7_make_cut(self):
        """7 picks, all active, best 5 counted."""
        scores = {
            i: _gs(i, f"P{i}", total=-10 + i)  # -9, -8, -7, -6, -5, -4, -3
            for i in range(1, 8)
        }
        picks = [_pick(i, f"P{i}", i) for i in range(1, 8)]
        entry = _entry(1, picks)

        result = score_entry(entry, scores, RVCC_RULES)

        assert result.qualification_status == "qualified"
        assert result.qualified_golfers_count == 7
        assert result.counted_golfers_count == 5
        # Best 5: -9, -8, -7, -6, -5 = -35
        assert result.aggregate_score == -35
        counted = [p for p in result.picks if p.counts_toward_total]
        assert len(counted) == 5
        dropped = [p for p in result.picks if p.is_dropped]
        assert len(dropped) == 2

    def test_exactly_5_make_cut(self):
        """5 active + 2 cut — exactly qualifies."""
        scores = {}
        for i in range(1, 6):
            scores[i] = _gs(i, f"P{i}", total=-5 + i)
        scores[6] = _gs(6, "P6", total=0, status="cut")
        scores[7] = _gs(7, "P7", total=0, status="cut")

        picks = [_pick(i, f"P{i}", i) for i in range(1, 8)]
        result = score_entry(_entry(1, picks), scores, RVCC_RULES)

        assert result.qualification_status == "qualified"
        assert result.qualified_golfers_count == 5
        assert result.counted_golfers_count == 5

    def test_4_make_cut_not_qualified(self):
        """Only 4 active after cut is settled — not qualified."""
        scores = {}
        for i in range(1, 5):
            scores[i] = _gs(i, f"P{i}", total=-5 + i, r1=-3, r2=-2)  # R2 done = cut settled
        for i in range(5, 8):
            scores[i] = _gs(i, f"P{i}", total=0, status="cut", r1=2, r2=3)

        picks = [_pick(i, f"P{i}", i) for i in range(1, 8)]
        result = score_entry(_entry(1, picks), scores, RVCC_RULES)

        assert result.qualification_status == "not_qualified"
        assert result.qualified_golfers_count == 4

    def test_wd_and_dq_not_eligible(self):
        """WD and DQ golfers don't count."""
        scores = {
            1: _gs(1, "P1", -10),
            2: _gs(2, "P2", -8),
            3: _gs(3, "P3", -6),
            4: _gs(4, "P4", -4),
            5: _gs(5, "P5", -2),
            6: _gs(6, "P6", 0, status="wd"),
            7: _gs(7, "P7", 0, status="dq"),
        }
        picks = [_pick(i, f"P{i}", i) for i in range(1, 8)]
        result = score_entry(_entry(1, picks), scores, RVCC_RULES)

        assert result.qualification_status == "qualified"
        assert result.qualified_golfers_count == 5  # Only active golfers

    def test_golfer_not_on_leaderboard(self):
        """Golfer not in leaderboard data — treated as unknown."""
        scores = {i: _gs(i, f"P{i}", total=-5 + i) for i in range(1, 7)}
        # Player 7 not in scores dict
        picks = [_pick(i, f"P{i}", i) for i in range(1, 8)]
        result = score_entry(_entry(1, picks), scores, RVCC_RULES)

        unknown = [p for p in result.picks if p.status == "unknown"]
        assert len(unknown) == 1
        assert unknown[0].dg_id == 7

    def test_pending_qualification_borderline(self):
        """Borderline case: exactly 5 active but R2 not done — could lose golfers at cut."""
        scores = {
            1: _gs(1, "P1", -5, r1=-5, r2=None),
            2: _gs(2, "P2", -3, r1=-3, r2=None),
            3: _gs(3, "P3", -1, r1=-1, r2=None),
            4: _gs(4, "P4", 0, r1=0, r2=None),
            5: _gs(5, "P5", 1, r1=1, r2=None),
            6: _gs(6, "P6", 3, status="cut", r1=3, r2=5),
            7: _gs(7, "P7", 5, status="cut", r1=5, r2=6),
        }
        picks = [_pick(i, f"P{i}", i) for i in range(1, 8)]
        result = score_entry(_entry(1, picks), scores, RVCC_RULES)

        # 5 active with R2 pending on some — qualified provisionally
        assert result.qualification_status == "qualified"
        assert result.counted_golfers_count == 5

    def test_pending_when_below_threshold_and_rounds_pending(self):
        """Below cut threshold but rounds still pending — pending not not_qualified."""
        scores = {
            1: _gs(1, "P1", -5, r1=-5, r2=None),  # R2 not done
            2: _gs(2, "P2", -3, r1=-3, r2=None),
            3: _gs(3, "P3", -1, r1=-1, r2=None),
            4: _gs(4, "P4", 0, r1=0, r2=None),
            5: _gs(5, "P5", 1, status="cut", r1=3, r2=5),
            6: _gs(6, "P6", 3, status="cut", r1=4, r2=6),
            7: _gs(7, "P7", 5, status="cut", r1=5, r2=7),
        }
        picks = [_pick(i, f"P{i}", i) for i in range(1, 8)]
        result = score_entry(_entry(1, picks), scores, RVCC_RULES)

        # Only 4 active but some still have R2 pending — pending
        assert result.qualification_status == "pending"


# ---------------------------------------------------------------------------
# Crestmont Scoring
# ---------------------------------------------------------------------------

class TestCrestmontScoring:
    def test_happy_path_all_6_make_cut(self):
        """6 picks from 6 buckets, all active, best 4 counted."""
        scores = {
            i: _gs(i, f"P{i}", total=-12 + i * 2)
            for i in range(1, 7)
        }
        picks = [_pick(i, f"P{i}", i, bucket=i) for i in range(1, 7)]
        result = score_entry(_entry(1, picks), scores, CRESTMONT_RULES)

        assert result.qualification_status == "qualified"
        assert result.counted_golfers_count == 4
        assert result.qualified_golfers_count == 6

    def test_exactly_4_make_cut(self):
        """4 active + 2 cut — exactly qualifies."""
        scores = {}
        for i in range(1, 5):
            scores[i] = _gs(i, f"P{i}", total=-5 + i)
        scores[5] = _gs(5, "P5", total=0, status="cut")
        scores[6] = _gs(6, "P6", total=0, status="cut")

        picks = [_pick(i, f"P{i}", i, bucket=i) for i in range(1, 7)]
        result = score_entry(_entry(1, picks), scores, CRESTMONT_RULES)

        assert result.qualification_status == "qualified"
        assert result.counted_golfers_count == 4

    def test_3_make_cut_not_qualified(self):
        """Only 3 active after cut settled — not qualified."""
        scores = {}
        for i in range(1, 4):
            scores[i] = _gs(i, f"P{i}", total=-5 + i, r1=-3, r2=-2)
        for i in range(4, 7):
            scores[i] = _gs(i, f"P{i}", total=0, status="cut", r1=2, r2=3)

        picks = [_pick(i, f"P{i}", i, bucket=i) for i in range(1, 7)]
        result = score_entry(_entry(1, picks), scores, CRESTMONT_RULES)

        assert result.qualification_status == "not_qualified"


# ---------------------------------------------------------------------------
# Ranking / Ties
# ---------------------------------------------------------------------------

class TestRanking:
    def test_basic_ranking(self):
        """Entries ranked by aggregate score."""
        entries = [
            ScoredEntry(entry_id=1, email="a@x.com", entry_name="A", picks=[],
                        aggregate_score=-20, qualified_golfers_count=5,
                        counted_golfers_count=5, qualification_status="qualified",
                        is_complete=True),
            ScoredEntry(entry_id=2, email="b@x.com", entry_name="B", picks=[],
                        aggregate_score=-15, qualified_golfers_count=5,
                        counted_golfers_count=5, qualification_status="qualified",
                        is_complete=True),
            ScoredEntry(entry_id=3, email="c@x.com", entry_name="C", picks=[],
                        aggregate_score=-25, qualified_golfers_count=5,
                        counted_golfers_count=5, qualification_status="qualified",
                        is_complete=True),
        ]
        ranked = rank_entries(entries)
        assert ranked[0].entry_id == 3  # -25
        assert ranked[0].rank == 1
        assert ranked[1].entry_id == 1  # -20
        assert ranked[1].rank == 2
        assert ranked[2].entry_id == 2  # -15
        assert ranked[2].rank == 3

    def test_tied_entries_share_rank(self):
        """Two entries with same score share rank."""
        entries = [
            ScoredEntry(entry_id=1, email="a@x.com", entry_name="A", picks=[],
                        aggregate_score=-20, qualified_golfers_count=5,
                        counted_golfers_count=5, qualification_status="qualified",
                        is_complete=True),
            ScoredEntry(entry_id=2, email="b@x.com", entry_name="B", picks=[],
                        aggregate_score=-20, qualified_golfers_count=5,
                        counted_golfers_count=5, qualification_status="qualified",
                        is_complete=True),
        ]
        ranked = rank_entries(entries)
        assert ranked[0].rank == 1
        assert ranked[1].rank == 1
        assert ranked[0].is_tied is True
        assert ranked[1].is_tied is True

    def test_not_qualified_has_no_rank(self):
        entries = [
            ScoredEntry(entry_id=1, email="a@x.com", entry_name="A", picks=[],
                        aggregate_score=-20, qualified_golfers_count=5,
                        counted_golfers_count=5, qualification_status="qualified",
                        is_complete=True),
            ScoredEntry(entry_id=2, email="b@x.com", entry_name="B", picks=[],
                        aggregate_score=None, qualified_golfers_count=3,
                        counted_golfers_count=3, qualification_status="not_qualified",
                        is_complete=True),
        ]
        ranked = rank_entries(entries)
        assert ranked[0].rank == 1
        assert ranked[1].rank is None

    def test_pending_ranked_after_qualified(self):
        entries = [
            ScoredEntry(entry_id=1, email="a@x.com", entry_name="A", picks=[],
                        aggregate_score=-20, qualified_golfers_count=5,
                        counted_golfers_count=5, qualification_status="qualified",
                        is_complete=True),
            ScoredEntry(entry_id=2, email="b@x.com", entry_name="B", picks=[],
                        aggregate_score=-15, qualified_golfers_count=7,
                        counted_golfers_count=5, qualification_status="pending",
                        is_complete=False),
        ]
        ranked = rank_entries(entries)
        assert ranked[0].qualification_status == "qualified"
        assert ranked[1].qualification_status == "pending"


# ---------------------------------------------------------------------------
# Full pool scoring
# ---------------------------------------------------------------------------

class TestScorePool:
    def test_full_pool_rvcc(self):
        """Score a complete RVCC pool with multiple entries."""
        scores = {i: _gs(i, f"P{i}", total=-10 + i) for i in range(1, 20)}

        entry1 = _entry(1, [_pick(i, f"P{i}", i) for i in range(1, 8)], "a@x.com")
        entry2 = _entry(2, [_pick(i, f"P{i}", i) for i in range(5, 12)], "b@x.com")

        results = score_pool([entry1, entry2], scores, RVCC_RULES)

        assert len(results) == 2
        assert results[0].rank == 1
        # Entry 1 has players 1-7 (scores -9 to -3), best 5 = -35
        assert results[0].aggregate_score == -35
        assert results[0].entry_id == 1

    def test_full_pool_crestmont(self):
        """Score a complete Crestmont pool."""
        scores = {i: _gs(i, f"P{i}", total=-12 + i * 2) for i in range(1, 20)}

        entry = _entry(1, [_pick(i, f"P{i}", i, bucket=i) for i in range(1, 7)])
        results = score_pool([entry], scores, CRESTMONT_RULES)

        assert len(results) == 1
        assert results[0].qualification_status == "qualified"
        assert results[0].counted_golfers_count == 4
