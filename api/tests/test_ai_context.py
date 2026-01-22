"""
Unit tests for AI Context Rules (Issue 0.4).

These tests validate the "prior chapters only" policy and story state derivation.
"""

import pytest
from typing import Any

from app.services.chapters import (
    Chapter,
    Play,
    GameStory,
    StoryState,
    PlayerStoryState,
    TeamStoryState,
    MomentumHint,
    ChapterSummary,
    derive_story_state_from_chapters,
    build_chapter_ai_input,
    build_book_ai_input,
    validate_no_future_context,
)


# Test 1: No Future Context Test

def test_no_future_context_validation():
    """When generating Chapter N, payload must not include future chapters."""
    # Create chapters
    ch1 = Chapter(
        chapter_id="ch_001",
        play_start_idx=0,
        play_end_idx=4,
        plays=[Play(index=i, event_type="pbp", raw_data={"description": f"Play {i}"}) for i in range(5)],
        reason_codes=["PERIOD_START"],
        period=1,
    )
    
    ch2 = Chapter(
        chapter_id="ch_002",
        play_start_idx=5,
        play_end_idx=9,
        plays=[Play(index=i, event_type="pbp", raw_data={"description": f"Play {i}"}) for i in range(5, 10)],
        reason_codes=["TIMEOUT"],
        period=1,
    )
    
    ch3 = Chapter(
        chapter_id="ch_003",
        play_start_idx=10,
        play_end_idx=14,
        plays=[Play(index=i, event_type="pbp", raw_data={"description": f"Play {i}"}) for i in range(10, 15)],
        reason_codes=["PERIOD_START"],
        period=2,
    )
    
    # Valid: ch2 with prior=[ch1]
    ai_input = build_chapter_ai_input(
        current_chapter=ch2,
        prior_chapters=[ch1],
    )
    
    assert ai_input.chapter["chapter_id"] == "ch_002"
    assert len(ai_input.prior_chapters) == 1
    assert ai_input.prior_chapters[0].chapter_id == "ch_001"
    
    # Invalid: ch2 with prior=[ch1, ch3] (ch3 is future)
    with pytest.raises(ValueError, match="Future chapter detected"):
        build_chapter_ai_input(
            current_chapter=ch2,
            prior_chapters=[ch1, ch3],
        )


def test_no_future_context_in_story_state():
    """Story state must only include prior chapters."""
    ch1 = Chapter(
        chapter_id="ch_001",
        play_start_idx=0,
        play_end_idx=1,
        plays=[
            Play(index=0, event_type="pbp", raw_data={"description": "LeBron James makes layup"}),
            Play(index=1, event_type="pbp", raw_data={"description": "Tatum makes 3-pointer"}),
        ],
        reason_codes=["PERIOD_START"],
        period=1,
    )
    
    ch2 = Chapter(
        chapter_id="ch_002",
        play_start_idx=2,
        play_end_idx=2,
        plays=[
            Play(index=2, event_type="pbp", raw_data={"description": "LeBron James makes dunk"}),
        ],
        reason_codes=["TIMEOUT"],
        period=1,
    )
    
    # Build AI input for ch2
    ai_input = build_chapter_ai_input(
        current_chapter=ch2,
        prior_chapters=[ch1],
    )
    
    # Story state should only include ch1
    story_state = StoryState.from_dict(ai_input.story_state)
    assert story_state.chapter_index_last_processed == 0  # Only ch1 (index 0)
    
    # LeBron should have points from ch1 only (2 points from layup)
    assert "LeBron James" in story_state.players
    assert story_state.players["LeBron James"].points_so_far == 2


def test_no_final_totals_in_payload():
    """Payload must not include final totals or end-of-game markers."""
    ch1 = Chapter(
        chapter_id="ch_001",
        play_start_idx=0,
        play_end_idx=4,
        plays=[Play(index=i, event_type="pbp", raw_data={"description": f"Play {i}"}) for i in range(5)],
        reason_codes=["PERIOD_START"],
        period=1,
    )
    
    ai_input = build_chapter_ai_input(
        current_chapter=ch1,
        prior_chapters=[],
    )
    
    # Check that payload doesn't have final totals
    assert "final_score" not in ai_input.chapter
    assert "final_stats" not in ai_input.chapter
    assert "game_result" not in ai_input.chapter


# Test 2: StoryState Determinism Test

def test_story_state_determinism():
    """Given the same prior chapters, StoryState output must be identical."""
    chapters = [
        Chapter(
            chapter_id="ch_001",
            play_start_idx=0,
            play_end_idx=1,
            plays=[
                Play(index=0, event_type="pbp", raw_data={"description": "LeBron James makes layup"}),
                Play(index=1, event_type="pbp", raw_data={"description": "Tatum makes 3-pointer"}),
            ],
            reason_codes=["PERIOD_START"],
            period=1,
        ),
        Chapter(
            chapter_id="ch_002",
            play_start_idx=2,
            play_end_idx=2,
            plays=[
                Play(index=2, event_type="pbp", raw_data={"description": "LeBron James makes dunk"}),
            ],
            reason_codes=["TIMEOUT"],
            period=1,
        ),
    ]
    
    # Build story state twice
    state1 = derive_story_state_from_chapters(chapters)
    state2 = derive_story_state_from_chapters(chapters)
    
    # Should be identical
    assert state1.to_dict() == state2.to_dict()
    assert state1.chapter_index_last_processed == state2.chapter_index_last_processed
    assert state1.players.keys() == state2.players.keys()
    
    for player_name in state1.players:
        p1 = state1.players[player_name]
        p2 = state2.players[player_name]
        assert p1.points_so_far == p2.points_so_far
        assert p1.notable_actions_so_far == p2.notable_actions_so_far


# Test 3: StoryState Derivation Test

def test_story_state_points_accumulation():
    """Points should increment correctly from play text."""
    chapters = [
        Chapter(
            chapter_id="ch_001",
            play_start_idx=0,
            play_end_idx=3,
            plays=[
                Play(index=0, event_type="pbp", raw_data={"description": "LeBron James makes layup"}),  # 2 pts
                Play(index=1, event_type="pbp", raw_data={"description": "LeBron James makes 3-pointer"}),  # 3 pts
                Play(index=2, event_type="pbp", raw_data={"description": "LeBron James makes free throw"}),  # 1 pt
                Play(index=3, event_type="pbp", raw_data={"description": "Tatum makes layup"}),  # 2 pts
            ],
            reason_codes=["PERIOD_START"],
            period=1,
        ),
    ]
    
    state = derive_story_state_from_chapters(chapters)
    
    # LeBron: 2 + 3 + 1 = 6 points
    assert "LeBron James" in state.players
    assert state.players["LeBron James"].points_so_far == 6
    assert state.players["LeBron James"].made_fg_so_far == 2  # Layup + 3PT
    assert state.players["LeBron James"].made_3pt_so_far == 1
    assert state.players["LeBron James"].made_ft_so_far == 1
    
    # Tatum: 2 points
    assert "Tatum" in state.players
    assert state.players["Tatum"].points_so_far == 2


def test_story_state_notable_actions():
    """Notable actions should be derived from eligible play types."""
    chapters = [
        Chapter(
            chapter_id="ch_001",
            play_start_idx=0,
            play_end_idx=3,
            plays=[
                Play(index=0, event_type="pbp", raw_data={"description": "LeBron James makes dunk"}),
                Play(index=1, event_type="pbp", raw_data={"description": "LeBron James block"}),
                Play(index=2, event_type="pbp", raw_data={"description": "LeBron James steal"}),
                Play(index=3, event_type="pbp", raw_data={"description": "LeBron James makes 3-pointer"}),
            ],
            reason_codes=["PERIOD_START"],
            period=1,
        ),
    ]
    
    state = derive_story_state_from_chapters(chapters)
    
    assert "LeBron James" in state.players
    notable = state.players["LeBron James"].notable_actions_so_far
    
    # Should have: dunk, block, steal, 3PT
    assert "dunk" in notable
    assert "block" in notable
    assert "steal" in notable
    assert "3PT" in notable


def test_story_state_notable_actions_bounded():
    """Notable actions should be bounded to max 5 (FIFO)."""
    chapters = [
        Chapter(
            chapter_id="ch_001",
            play_start_idx=0,
            play_end_idx=9,
            plays=[
                Play(index=i, event_type="pbp", raw_data={"description": f"LeBron James makes dunk"})
                for i in range(10)  # 10 dunks
            ],
            reason_codes=["PERIOD_START"],
            period=1,
        ),
    ]
    
    state = derive_story_state_from_chapters(chapters)
    
    assert "LeBron James" in state.players
    notable = state.players["LeBron James"].notable_actions_so_far
    
    # Should have max 5
    assert len(notable) <= 5


# Test 4: Schema Validation Test

def test_story_state_schema_validation():
    """StoryState should conform to schema."""
    state = StoryState(
        chapter_index_last_processed=2,
        players={
            "LeBron James": PlayerStoryState(
                player_name="LeBron James",
                points_so_far=18,
                made_fg_so_far=7,
                made_3pt_so_far=2,
                made_ft_so_far=2,
                notable_actions_so_far=["dunk", "3PT", "and-1"],
            ),
        },
        teams={
            "Lakers": TeamStoryState(team_name="Lakers", score_so_far=54),
        },
        momentum_hint=MomentumHint.SURGING,
        theme_tags=["hot_shooting", "defensive_intensity"],
    )
    
    # Should serialize without error
    state_dict = state.to_dict()
    
    # Check required fields
    assert "chapter_index_last_processed" in state_dict
    assert "players" in state_dict
    assert "teams" in state_dict
    assert "momentum_hint" in state_dict
    assert "theme_tags" in state_dict
    assert "constraints" in state_dict
    
    # Check constraints
    assert state_dict["constraints"]["no_future_knowledge"] is True
    assert state_dict["constraints"]["source"] == "derived_from_prior_chapters_only"


def test_story_state_bounded_lists_enforced():
    """Bounded lists should be enforced (max sizes)."""
    # Too many players (max 6)
    with pytest.raises(ValueError, match="players max 6"):
        StoryState(
            chapter_index_last_processed=0,
            players={
                f"Player {i}": PlayerStoryState(player_name=f"Player {i}")
                for i in range(10)  # 10 players (too many)
            },
        )
    
    # Too many theme tags (max 8)
    with pytest.raises(ValueError, match="theme_tags max 8"):
        StoryState(
            chapter_index_last_processed=0,
            theme_tags=[f"theme_{i}" for i in range(10)],  # 10 themes (too many)
        )
    
    # Too many notable actions per player (max 5)
    with pytest.raises(ValueError, match="notable_actions_so_far max 5"):
        PlayerStoryState(
            player_name="LeBron",
            notable_actions_so_far=["action"] * 10,  # 10 actions (too many)
        )


def test_story_state_constraints_required():
    """Story state must have required constraints."""
    # Missing no_future_knowledge
    with pytest.raises(ValueError, match="no_future_knowledge must be true"):
        StoryState(
            chapter_index_last_processed=0,
            constraints={"source": "derived_from_prior_chapters_only"},
        )
    
    # Wrong source
    with pytest.raises(ValueError, match="source must be"):
        StoryState(
            chapter_index_last_processed=0,
            constraints={
                "no_future_knowledge": True,
                "source": "wrong_source",
            },
        )


# Test 5: Integration Tests

def test_integration_chapter_ai_input_full_flow():
    """Full flow: build chapters → derive state → build AI input."""
    from app.services.chapters import build_chapters
    
    timeline = [
        {"event_type": "pbp", "quarter": 1, "play_id": 0, "description": "LeBron James makes layup"},
        {"event_type": "pbp", "quarter": 1, "play_id": 1, "description": "Tatum makes 3-pointer"},
        {"event_type": "pbp", "quarter": 1, "play_id": 2, "description": "Timeout: Lakers"},
        {"event_type": "pbp", "quarter": 1, "play_id": 3, "description": "LeBron James makes dunk"},
    ]
    
    story = build_chapters(timeline, game_id=1, sport="NBA")
    
    # Should have 2 chapters (Q1 start, then timeout)
    assert story.chapter_count >= 2
    
    # Build AI input for chapter 2
    if story.chapter_count >= 2:
        ai_input = build_chapter_ai_input(
            current_chapter=story.chapters[1],
            prior_chapters=[story.chapters[0]],
        )
        
        # Validate
        assert ai_input.chapter["chapter_id"] == story.chapters[1].chapter_id
        assert len(ai_input.prior_chapters) == 1
        assert ai_input.story_state["chapter_index_last_processed"] == 0
        
        # LeBron should have points from ch1
        assert "LeBron James" in ai_input.story_state["players"]


def test_integration_book_ai_input():
    """Full book AI input should include all chapters."""
    from app.services.chapters import build_chapters
    
    timeline = [
        {"event_type": "pbp", "quarter": 1, "play_id": 0, "description": "Play 1"},
        {"event_type": "pbp", "quarter": 2, "play_id": 1, "description": "Play 2"},
    ]
    
    story = build_chapters(timeline, game_id=1, sport="NBA")
    
    # Create summaries (stubbed)
    summaries = [
        ChapterSummary(
            chapter_id=ch.chapter_id,
            title=f"Chapter {i+1}",
            summary=f"Summary of chapter {i+1}",
            reason_codes=ch.reason_codes,
            period=ch.period,
        )
        for i, ch in enumerate(story.chapters)
    ]
    
    # Build book AI input
    book_input = build_book_ai_input(story, summaries)
    
    assert book_input.game_id == 1
    assert book_input.sport == "NBA"
    assert len(book_input.chapters) == story.chapter_count


def test_validate_no_future_context_function():
    """validate_no_future_context should catch violations."""
    ch1 = Chapter(
        chapter_id="ch_001",
        play_start_idx=0,
        play_end_idx=4,
        plays=[Play(index=i, event_type="pbp", raw_data={}) for i in range(5)],
        reason_codes=["PERIOD_START"],
        period=1,
    )
    
    ch2 = Chapter(
        chapter_id="ch_002",
        play_start_idx=5,
        play_end_idx=9,
        plays=[Play(index=i, event_type="pbp", raw_data={}) for i in range(5, 10)],
        reason_codes=["TIMEOUT"],
        period=1,
    )
    
    state = derive_story_state_from_chapters([ch1])
    
    # Valid: ch2 with prior=[ch1]
    validate_no_future_context(ch2, [ch1], state)
    
    # Invalid: ch1 with prior=[ch2] (ch2 is future relative to ch1)
    with pytest.raises(ValueError, match="Future chapter detected"):
        validate_no_future_context(ch1, [ch2], state)


def test_momentum_hint_derivation():
    """Momentum hint should be derived from chapter reason codes."""
    # RUN_START → surging
    ch_run = Chapter(
        chapter_id="ch_001",
        play_start_idx=0,
        play_end_idx=4,
        plays=[Play(index=i, event_type="pbp", raw_data={}) for i in range(5)],
        reason_codes=["RUN_START"],
        period=1,
    )
    
    state = derive_story_state_from_chapters([ch_run])
    assert state.momentum_hint == MomentumHint.SURGING
    
    # CRUNCH_START → volatile
    ch_crunch = Chapter(
        chapter_id="ch_002",
        play_start_idx=5,
        play_end_idx=9,
        plays=[Play(index=i, event_type="pbp", raw_data={}) for i in range(5, 10)],
        reason_codes=["CRUNCH_START"],
        period=4,
    )
    
    state = derive_story_state_from_chapters([ch_crunch])
    assert state.momentum_hint == MomentumHint.VOLATILE


def test_theme_tags_derivation():
    """Theme tags should be derived from chapter patterns."""
    # TIMEOUT reason code → timeout_heavy
    ch_timeout = Chapter(
        chapter_id="ch_001",
        play_start_idx=0,
        play_end_idx=4,
        plays=[Play(index=i, event_type="pbp", raw_data={}) for i in range(5)],
        reason_codes=["TIMEOUT"],
        period=1,
    )
    
    state = derive_story_state_from_chapters([ch_timeout])
    assert "timeout_heavy" in state.theme_tags
    
    # CRUNCH_START → crunch_time
    ch_crunch = Chapter(
        chapter_id="ch_002",
        play_start_idx=5,
        play_end_idx=9,
        plays=[Play(index=i, event_type="pbp", raw_data={}) for i in range(5, 10)],
        reason_codes=["CRUNCH_START"],
        period=4,
    )
    
    state = derive_story_state_from_chapters([ch_crunch])
    assert "crunch_time" in state.theme_tags
