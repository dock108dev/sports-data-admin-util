"""
Unit tests for Running Story State Builder (Phase 1 Issue 8).

These tests validate incremental state building and safety guarantees.
"""

import pytest
import json

from app.services.chapters import (
    Chapter,
    Play,
    StoryState,
    PlayerStoryState,
    MomentumHint,
    build_initial_state,
    update_state,
    build_state_incrementally,
    derive_story_state_from_chapters,
)


def make_play(index: int, description: str, quarter: int = 1) -> Play:
    """Helper to create Play with required fields."""
    return Play(
        index=index,
        event_type="pbp",
        raw_data={"description": description, "quarter": quarter}
    )


def make_chapter(chapter_id: str, start_idx: int, plays: list[Play], reason_codes: list[str]) -> Chapter:
    """Helper to create Chapter."""
    return Chapter(
        chapter_id=chapter_id,
        play_start_idx=start_idx,
        play_end_idx=start_idx + len(plays) - 1,
        plays=plays,
        reason_codes=reason_codes,
    )


# Test 1: No Future Leakage Test

def test_no_future_leakage():
    """Story state for Chapter N must not include data from Chapter N or later."""
    chapters = [
        make_chapter("ch_001", 0, [
            make_play(0, "LeBron makes layup"),
            make_play(1, "Curry makes 3-pointer"),
        ], ["PERIOD_START"]),
        make_chapter("ch_002", 2, [
            make_play(2, "Durant makes dunk"),
            make_play(3, "Giannis makes layup"),
        ], ["TIMEOUT"]),
    ]
    
    # Build state after Chapter 0 only
    state = derive_story_state_from_chapters(chapters[:1], sport="NBA")
    
    # Should have processed only Chapter 0
    assert state.chapter_index_last_processed == 0
    
    # Should have only players from Chapter 0
    assert "LeBron" in state.players
    assert "Curry" in state.players
    assert "Durant" not in state.players
    assert "Giannis" not in state.players


def test_chapter_index_last_processed_correct():
    """chapter_index_last_processed must equal N-1 when building state for Chapter N."""
    chapters = [
        make_chapter("ch_001", 0, [make_play(0, "Play 1")], ["PERIOD_START"]),
        make_chapter("ch_002", 1, [make_play(1, "Play 2")], ["TIMEOUT"]),
        make_chapter("ch_003", 2, [make_play(2, "Play 3", quarter=2)], ["PERIOD_START"]),
    ]
    
    # State after 0 chapters (initial)
    state0 = build_initial_state()
    assert state0.chapter_index_last_processed == -1
    
    # State after 1 chapter
    state1 = derive_story_state_from_chapters(chapters[:1], sport="NBA")
    assert state1.chapter_index_last_processed == 0
    
    # State after 2 chapters
    state2 = derive_story_state_from_chapters(chapters[:2], sport="NBA")
    assert state2.chapter_index_last_processed == 1
    
    # State after 3 chapters
    state3 = derive_story_state_from_chapters(chapters[:3], sport="NBA")
    assert state3.chapter_index_last_processed == 2


# Test 2: Determinism Test

def test_determinism_same_chapters_same_state():
    """Same chapters must produce identical StoryState JSON."""
    chapters = [
        make_chapter("ch_001", 0, [
            make_play(0, "LeBron makes layup"),
            make_play(1, "Curry makes 3-pointer"),
        ], ["PERIOD_START"]),
    ]
    
    state1 = derive_story_state_from_chapters(chapters, sport="NBA")
    state2 = derive_story_state_from_chapters(chapters, sport="NBA")
    
    # Should produce identical JSON
    json1 = json.dumps(state1.to_dict(), sort_keys=True)
    json2 = json.dumps(state2.to_dict(), sort_keys=True)
    
    assert json1 == json2


# Test 3: Incremental Equivalence Test

def test_incremental_equivalence():
    """Building state incrementally must equal building from scratch."""
    chapters = [
        make_chapter("ch_001", 0, [
            make_play(0, "LeBron makes layup"),
            make_play(1, "Curry makes 3-pointer"),
        ], ["PERIOD_START"]),
        make_chapter("ch_002", 2, [
            make_play(2, "Durant makes dunk"),
            make_play(3, "LeBron makes 3-pointer"),
        ], ["TIMEOUT"]),
    ]
    
    # Build incrementally
    incremental_states = build_state_incrementally(chapters, sport="NBA")
    final_incremental = incremental_states[-1]
    
    # Build from scratch
    from_scratch = derive_story_state_from_chapters(chapters, sport="NBA")
    
    # Should be equivalent
    assert final_incremental.chapter_index_last_processed == from_scratch.chapter_index_last_processed
    assert final_incremental.players.keys() == from_scratch.players.keys()
    
    # Check player stats match
    for player_name in final_incremental.players:
        inc_player = final_incremental.players[player_name]
        scratch_player = from_scratch.players[player_name]
        assert inc_player.points_so_far == scratch_player.points_so_far


def test_incremental_update_immutable():
    """update_state must not mutate previous state."""
    initial = build_initial_state()
    
    chapter = make_chapter("ch_001", 0, [
        make_play(0, "LeBron makes layup"),
    ], ["PERIOD_START"])
    
    # Update state
    new_state = update_state(initial, chapter, sport="NBA")
    
    # Initial state should be unchanged
    assert initial.chapter_index_last_processed == -1
    assert len(initial.players) == 0
    
    # New state should have updates
    assert new_state.chapter_index_last_processed == 0
    assert len(new_state.players) > 0


# Test 4: Player Bounding Test

def test_player_bounding_top_6():
    """Only top 6 players by points should be included."""
    # Create 10 players with different scores
    plays = []
    for name, points in [
        ("Player1", 30), ("Player2", 25), ("Player3", 20),
        ("Player4", 15), ("Player5", 10), ("Player6", 8),
        ("Player7", 5), ("Player8", 3), ("Player9", 2), ("Player10", 1),
    ]:
        for _ in range(points // 2):
            plays.append(make_play(len(plays), f"{name} makes layup"))
    
    chapter = make_chapter("ch_001", 0, plays, ["PERIOD_START"])
    state = derive_story_state_from_chapters([chapter], sport="NBA")
    
    # Should have exactly 6 players
    assert len(state.players) == 6
    
    # Should be top 6 by points
    player_names = list(state.players.keys())
    assert "Player1" in player_names
    assert "Player2" in player_names
    assert "Player3" in player_names
    assert "Player4" in player_names
    assert "Player5" in player_names
    assert "Player6" in player_names
    assert "Player7" not in player_names


# Test 5: Notable Action Extraction Test

def test_notable_action_extraction_allowed_only():
    """Only allowed notable actions should be extracted."""
    plays = [
        make_play(0, "LeBron makes dunk"),
        make_play(1, "LeBron makes block"),  # Note: block is defensive, but testing extraction
        make_play(2, "LeBron makes steal"),  # Note: steal is defensive, but testing extraction
        make_play(3, "LeBron makes 3-pointer"),
        make_play(4, "LeBron makes layup and-1"),
    ]
    
    chapter = make_chapter("ch_001", 0, plays, ["PERIOD_START"])
    state = derive_story_state_from_chapters([chapter], sport="NBA")
    
    assert "LeBron" in state.players
    player = state.players["LeBron"]
    
    # Should have notable actions (at least 3PT and and-1)
    assert "3PT" in player.notable_actions_so_far
    assert "and-1" in player.notable_actions_so_far


def test_notable_action_no_fabrication():
    """Notable actions must not be inferred or fabricated."""
    plays = [
        make_play(0, "LeBron makes layup"),
        make_play(1, "LeBron misses shot"),
    ]
    
    chapter = make_chapter("ch_001", 0, plays, ["PERIOD_START"])
    state = derive_story_state_from_chapters([chapter], sport="NBA")
    
    assert "LeBron" in state.players
    player = state.players["LeBron"]
    
    # Should not have any notable actions (layup and miss are not notable)
    assert len(player.notable_actions_so_far) == 0


def test_notable_action_bounded_max_5():
    """Notable actions should be bounded to max 5 per player."""
    plays = [make_play(i, "LeBron makes dunk") for i in range(10)]
    
    chapter = make_chapter("ch_001", 0, plays, ["PERIOD_START"])
    state = derive_story_state_from_chapters([chapter], sport="NBA")
    
    assert "LeBron" in state.players
    player = state.players["LeBron"]
    
    # Should have max 5 notable actions
    assert len(player.notable_actions_so_far) <= 5


# Test 6: Schema Validation Test

def test_schema_validation_all_required_fields():
    """StoryState must have all required fields."""
    state = build_initial_state()
    
    # Check required fields
    assert hasattr(state, 'chapter_index_last_processed')
    assert hasattr(state, 'players')
    assert hasattr(state, 'teams')
    assert hasattr(state, 'momentum_hint')
    assert hasattr(state, 'theme_tags')
    assert hasattr(state, 'constraints')
    
    # Check constraints
    assert state.constraints["no_future_knowledge"] is True
    assert state.constraints["source"] == "derived_from_prior_chapters_only"


def test_schema_validation_serializable():
    """StoryState must be serializable to JSON."""
    chapters = [
        make_chapter("ch_001", 0, [
            make_play(0, "LeBron makes layup"),
        ], ["PERIOD_START"]),
    ]
    
    state = derive_story_state_from_chapters(chapters, sport="NBA")
    
    # Should serialize to JSON without error
    json_str = json.dumps(state.to_dict())
    assert json_str
    
    # Should deserialize back
    data = json.loads(json_str)
    assert data["chapter_index_last_processed"] == 0


def test_schema_validation_constraints_enforced():
    """StoryState constraints must be enforced."""
    # Try to create state with invalid constraints
    with pytest.raises(ValueError, match="no_future_knowledge"):
        StoryState(
            chapter_index_last_processed=0,
            constraints={"no_future_knowledge": False}
        )
    
    with pytest.raises(ValueError, match="source"):
        StoryState(
            chapter_index_last_processed=0,
            constraints={
                "no_future_knowledge": True,
                "source": "invalid"
            }
        )


# Test 7: Player Stats Accumulation

def test_player_stats_accumulation_points():
    """Player points should accumulate correctly across chapters."""
    chapters = [
        make_chapter("ch_001", 0, [
            make_play(0, "LeBron makes layup"),  # 2 pts
            make_play(1, "LeBron makes 3-pointer"),  # 3 pts
        ], ["PERIOD_START"]),
        make_chapter("ch_002", 2, [
            make_play(2, "LeBron makes free throw"),  # 1 pt
            make_play(3, "LeBron makes layup"),  # 2 pts
        ], ["TIMEOUT"]),
    ]
    
    state = derive_story_state_from_chapters(chapters, sport="NBA")
    
    assert "LeBron" in state.players
    player = state.players["LeBron"]
    
    # Should have 8 points total (2 + 3 + 1 + 2)
    assert player.points_so_far == 8
    assert player.made_fg_so_far == 3  # layup, 3pt, layup
    assert player.made_3pt_so_far == 1
    assert player.made_ft_so_far == 1


def test_player_stats_accumulation_incremental():
    """Incremental updates should accumulate stats correctly."""
    chapter1 = make_chapter("ch_001", 0, [
        make_play(0, "LeBron makes layup"),  # 2 pts
    ], ["PERIOD_START"])
    
    chapter2 = make_chapter("ch_002", 1, [
        make_play(1, "LeBron makes 3-pointer"),  # 3 pts
    ], ["TIMEOUT"])
    
    # Build incrementally
    state1 = update_state(build_initial_state(), chapter1, sport="NBA")
    state2 = update_state(state1, chapter2, sport="NBA")
    
    assert "LeBron" in state2.players
    player = state2.players["LeBron"]
    
    # Should have 5 points total
    assert player.points_so_far == 5


# Test 8: Momentum Hints

def test_momentum_hint_from_reason_codes():
    """Momentum hint should be derived from chapter reason codes."""
    # RUN_START → surging
    chapter_run = make_chapter("ch_001", 0, [make_play(0, "Play")], ["RUN_START"])
    state_run = derive_story_state_from_chapters([chapter_run], sport="NBA")
    assert state_run.momentum_hint == MomentumHint.SURGING
    
    # RUN_END_RESPONSE → volatile
    chapter_response = make_chapter("ch_002", 1, [make_play(1, "Play")], ["RUN_END_RESPONSE"])
    state_response = derive_story_state_from_chapters([chapter_response], sport="NBA")
    assert state_response.momentum_hint == MomentumHint.VOLATILE
    
    # CRUNCH_START → volatile
    chapter_crunch = make_chapter("ch_003", 2, [make_play(2, "Play", quarter=4)], ["CRUNCH_START"])
    state_crunch = derive_story_state_from_chapters([chapter_crunch], sport="NBA")
    assert state_crunch.momentum_hint == MomentumHint.VOLATILE


# Test 9: Theme Tags

def test_theme_tags_bounded_max_8():
    """Theme tags should be bounded to max 8."""
    # Create chapters with many different themes
    chapters = [
        make_chapter(f"ch_{i:03d}", i, [make_play(i, "Play")], ["TIMEOUT"])
        for i in range(20)
    ]
    
    state = derive_story_state_from_chapters(chapters, sport="NBA")
    
    # Should have max 8 theme tags
    assert len(state.theme_tags) <= 8


def test_theme_tags_deterministic():
    """Theme tag truncation should be deterministic."""
    chapters = [
        make_chapter("ch_001", 0, [make_play(0, "Play")], ["TIMEOUT"]),
    ]
    
    state1 = derive_story_state_from_chapters(chapters, sport="NBA")
    state2 = derive_story_state_from_chapters(chapters, sport="NBA")
    
    # Should have same theme tags
    assert state1.theme_tags == state2.theme_tags


# Test 10: Integration

def test_integration_full_game():
    """Full game should produce valid story state."""
    chapters = []
    
    # Q1
    for i in range(5):
        plays = [
            make_play(i * 2, f"Player{i} makes layup"),
            make_play(i * 2 + 1, f"Player{i+5} makes 3-pointer"),
        ]
        chapters.append(make_chapter(
            f"ch_{i+1:03d}",
            i * 2,
            plays,
            ["PERIOD_START"] if i == 0 else ["TIMEOUT"]
        ))
    
    state = derive_story_state_from_chapters(chapters, sport="NBA")
    
    # Should have valid state
    assert state.chapter_index_last_processed == len(chapters) - 1
    assert len(state.players) <= 6
    assert len(state.theme_tags) <= 8
    assert state.constraints["no_future_knowledge"] is True
