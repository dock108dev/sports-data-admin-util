"""
Unit tests for AI Signals (Phase 1 Issue 9).

These tests validate signal discipline and prevent leakage.
"""

import pytest

from app.services.chapters import (
    StoryState,
    PlayerStoryState,
    TeamStoryState,
    MomentumHint,
    SignalValidationError,
    validate_ai_signals,
    check_for_disallowed_signals,
    ALLOWED_PLAYER_SIGNALS,
    ALLOWED_TEAM_SIGNALS,
    ALLOWED_THEME_TAGS,
    DISALLOWED_SIGNALS,
)


# Test 1: Signal Whitelist Test

def test_signal_whitelist_valid_signals():
    """Valid signals should pass validation."""
    state = StoryState(
        chapter_index_last_processed=0,
        players={
            "LeBron": PlayerStoryState(
                player_name="LeBron",
                points_so_far=20,
                made_fg_so_far=8,
                made_3pt_so_far=2,
                made_ft_so_far=2,
                notable_actions_so_far=["dunk", "3PT"],
            ),
        },
        teams={
            "Lakers": TeamStoryState(team_name="Lakers", score_so_far=58),
        },
        momentum_hint=MomentumHint.SURGING,
        theme_tags=["hot_shooting", "defensive_intensity"],
    )
    
    # Should not raise
    validate_ai_signals(state)


def test_signal_whitelist_player_fields():
    """Only allowed player fields should be present."""
    state = StoryState(
        chapter_index_last_processed=0,
        players={
            "LeBron": PlayerStoryState(
                player_name="LeBron",
                points_so_far=20,
            ),
        },
    )
    
    state_dict = state.to_dict()
    player_fields = set(state_dict["players"]["LeBron"].keys())
    
    # All player fields should be in whitelist
    assert player_fields.issubset(ALLOWED_PLAYER_SIGNALS)


def test_signal_whitelist_team_fields():
    """Only allowed team fields should be present."""
    state = StoryState(
        chapter_index_last_processed=0,
        teams={
            "Lakers": TeamStoryState(team_name="Lakers", score_so_far=58),
        },
    )
    
    state_dict = state.to_dict()
    team_fields = set(state_dict["teams"]["Lakers"].keys())
    
    # All team fields should be in whitelist
    assert team_fields.issubset(ALLOWED_TEAM_SIGNALS)


# Test 2: Bounding Test

def test_bounding_max_6_players():
    """Only top 6 players should be exposed."""
    # Create valid state with 6 players
    players = {
        f"Player{i}": PlayerStoryState(
            player_name=f"Player{i}",
            points_so_far=10 - i,
        )
        for i in range(6)
    }
    
    state = StoryState(
        chapter_index_last_processed=0,
        players=players,
    )
    
    # Manually add extra players to bypass __post_init__
    state.players["Player7"] = PlayerStoryState(player_name="Player7", points_so_far=3)
    state.players["Player8"] = PlayerStoryState(player_name="Player8", points_so_far=2)
    
    # Should fail validation (more than 6 players)
    with pytest.raises(SignalValidationError, match="Too many players"):
        validate_ai_signals(state)


def test_bounding_exactly_6_players():
    """Exactly 6 players should pass validation."""
    players = {
        f"Player{i}": PlayerStoryState(
            player_name=f"Player{i}",
            points_so_far=10 - i,
        )
        for i in range(6)
    }
    
    state = StoryState(
        chapter_index_last_processed=0,
        players=players,
    )
    
    # Should not raise
    validate_ai_signals(state)


def test_bounding_max_8_theme_tags():
    """Only max 8 theme tags should be exposed."""
    state = StoryState(
        chapter_index_last_processed=0,
        theme_tags=["hot_shooting", "defensive_intensity", "crunch_time", "overtime", "run_based", "timeout_heavy", "review_heavy", "free_throw_battle"],
    )
    
    # Manually add extra valid tag to bypass __post_init__
    # Use a valid tag so it passes theme validation but fails bounding
    state.theme_tags.append("hot_shooting")  # Duplicate, but valid
    
    # Should fail validation (more than 8 themes)
    with pytest.raises(SignalValidationError, match="Too many theme tags"):
        validate_ai_signals(state)


def test_bounding_max_5_notable_actions():
    """Max 5 notable actions per player should be enforced."""
    # PlayerStoryState already enforces this in __post_init__
    with pytest.raises(ValueError, match="max 5 items"):
        PlayerStoryState(
            player_name="LeBron",
            notable_actions_so_far=["dunk", "block", "steal", "3PT", "and-1", "technical"],
        )


# Test 3: No Disallowed Fields Test

def test_no_disallowed_fields_in_valid_state():
    """Valid state should have no disallowed signals."""
    state = StoryState(
        chapter_index_last_processed=0,
        players={
            "LeBron": PlayerStoryState(player_name="LeBron", points_so_far=20),
        },
    )
    
    state_dict = state.to_dict()
    disallowed = check_for_disallowed_signals(state_dict)
    
    # Should have no disallowed signals
    assert len(disallowed) == 0


def test_no_disallowed_fields_detection():
    """Disallowed signals should be detected."""
    # Manually create dict with disallowed field
    bad_data = {
        "players": {
            "LeBron": {
                "player_name": "LeBron",
                "points_so_far": 20,
                "final_points": 35,  # Disallowed!
            }
        }
    }
    
    disallowed = check_for_disallowed_signals(bad_data)
    
    # Should detect disallowed signal
    assert len(disallowed) > 0
    assert any("final_points" in sig for sig in disallowed)


def test_no_disallowed_fields_nested():
    """Nested disallowed signals should be detected."""
    bad_data = {
        "teams": {
            "Lakers": {
                "team_name": "Lakers",
                "stats": {
                    "win_probability": 0.75,  # Disallowed!
                }
            }
        }
    }
    
    disallowed = check_for_disallowed_signals(bad_data)
    
    # Should detect nested disallowed signal
    assert len(disallowed) > 0
    assert any("win_probability" in sig for sig in disallowed)


# Test 4: Schema Validation Test

def test_schema_validation_momentum_hint():
    """Momentum hint must be valid enum."""
    state = StoryState(
        chapter_index_last_processed=0,
        momentum_hint=MomentumHint.SURGING,
    )
    
    # Should not raise
    validate_ai_signals(state)


def test_schema_validation_invalid_momentum_hint():
    """Invalid momentum hint should fail validation."""
    # Create state dict with invalid momentum
    state_dict = {
        "chapter_index_last_processed": 0,
        "players": {},
        "teams": {},
        "momentum_hint": "invalid_momentum",  # Invalid!
        "theme_tags": [],
        "constraints": {
            "no_future_knowledge": True,
            "source": "derived_from_prior_chapters_only",
        }
    }
    
    from app.services.chapters.ai_signals import validate_story_state_signals
    
    # Should raise validation error
    with pytest.raises(SignalValidationError, match="Invalid momentum hint"):
        validate_story_state_signals(state_dict)


def test_schema_validation_theme_tags():
    """Theme tags must be in allowed list."""
    state_dict = {
        "chapter_index_last_processed": 0,
        "players": {},
        "teams": {},
        "momentum_hint": "steady",
        "theme_tags": ["invalid_theme"],  # Invalid!
        "constraints": {
            "no_future_knowledge": True,
            "source": "derived_from_prior_chapters_only",
        }
    }
    
    from app.services.chapters.ai_signals import validate_story_state_signals
    
    # Should raise validation error
    with pytest.raises(SignalValidationError, match="Disallowed theme tag"):
        validate_story_state_signals(state_dict)


def test_schema_validation_notable_actions():
    """Notable actions must be in allowed list."""
    player_dict = {
        "player_name": "LeBron",
        "points_so_far": 20,
        "made_fg_so_far": 8,
        "made_3pt_so_far": 0,
        "made_ft_so_far": 4,
        "notable_actions_so_far": ["invalid_action"],  # Invalid!
    }
    
    from app.services.chapters.ai_signals import validate_player_signals
    
    # Should raise validation error
    with pytest.raises(SignalValidationError, match="Disallowed notable action"):
        validate_player_signals(player_dict)


# Test 5: Constraints Validation

def test_constraints_no_future_knowledge():
    """no_future_knowledge constraint must be true."""
    state = StoryState(
        chapter_index_last_processed=0,
    )
    
    # Manually modify constraints to bypass __post_init__
    state.constraints["no_future_knowledge"] = False
    
    # Should fail validation
    with pytest.raises(SignalValidationError, match="no_future_knowledge"):
        validate_ai_signals(state)


def test_constraints_source():
    """source constraint must be correct."""
    state = StoryState(
        chapter_index_last_processed=0,
    )
    
    # Manually modify constraints to bypass __post_init__
    state.constraints["source"] = "invalid_source"
    
    # Should fail validation
    with pytest.raises(SignalValidationError, match="derived_from_prior_chapters_only"):
        validate_ai_signals(state)


# Test 6: Integration Tests

def test_integration_valid_full_state():
    """Full valid state should pass all validations."""
    state = StoryState(
        chapter_index_last_processed=2,
        players={
            "LeBron": PlayerStoryState(
                player_name="LeBron",
                points_so_far=25,
                made_fg_so_far=10,
                made_3pt_so_far=3,
                made_ft_so_far=2,
                notable_actions_so_far=["dunk", "3PT", "block"],
            ),
            "Curry": PlayerStoryState(
                player_name="Curry",
                points_so_far=20,
                made_fg_so_far=7,
                made_3pt_so_far=4,
                made_ft_so_far=2,
                notable_actions_so_far=["3PT", "3PT", "3PT"],
            ),
        },
        teams={
            "Lakers": TeamStoryState(team_name="Lakers", score_so_far=65),
            "Warriors": TeamStoryState(team_name="Warriors", score_so_far=58),
        },
        momentum_hint=MomentumHint.VOLATILE,
        theme_tags=["hot_shooting", "crunch_time", "defensive_intensity"],
    )
    
    # Should pass all validations
    validate_ai_signals(state)
    
    # Should have no disallowed signals
    state_dict = state.to_dict()
    disallowed = check_for_disallowed_signals(state_dict)
    assert len(disallowed) == 0


def test_integration_format_signals_summary():
    """Signal summary should format correctly."""
    state = StoryState(
        chapter_index_last_processed=0,
        players={
            "LeBron": PlayerStoryState(
                player_name="LeBron",
                points_so_far=20,
                notable_actions_so_far=["dunk", "3PT"],
            ),
        },
        teams={
            "Lakers": TeamStoryState(team_name="Lakers", score_so_far=58),
        },
        momentum_hint=MomentumHint.SURGING,
        theme_tags=["hot_shooting"],
    )
    
    from app.services.chapters.ai_signals import format_ai_signals_summary
    
    summary = format_ai_signals_summary(state)
    
    # Should contain key information
    assert "LeBron" in summary
    assert "20 pts" in summary
    assert "Lakers" in summary
    assert "58 pts" in summary
    assert "surging" in summary
    assert "hot_shooting" in summary
    assert "no_future_knowledge" in summary


# Test 7: Blacklist Enforcement

def test_blacklist_final_points():
    """final_points should be blacklisted."""
    assert "final_points" in DISALLOWED_SIGNALS


def test_blacklist_shooting_percentage():
    """shooting_percentage should be blacklisted."""
    assert "shooting_percentage" in DISALLOWED_SIGNALS


def test_blacklist_win_probability():
    """win_probability should be blacklisted."""
    assert "win_probability" in DISALLOWED_SIGNALS


def test_blacklist_ladder_tier():
    """ladder_tier should be blacklisted."""
    assert "ladder_tier" in DISALLOWED_SIGNALS


def test_blacklist_moment_type():
    """moment_type should be blacklisted."""
    assert "moment_type" in DISALLOWED_SIGNALS


# Test 8: Whitelist Enforcement

def test_whitelist_player_signals():
    """Player whitelist should contain required fields."""
    assert "player_name" in ALLOWED_PLAYER_SIGNALS
    assert "points_so_far" in ALLOWED_PLAYER_SIGNALS
    assert "made_fg_so_far" in ALLOWED_PLAYER_SIGNALS
    assert "made_3pt_so_far" in ALLOWED_PLAYER_SIGNALS
    assert "made_ft_so_far" in ALLOWED_PLAYER_SIGNALS
    assert "notable_actions_so_far" in ALLOWED_PLAYER_SIGNALS


def test_whitelist_team_signals():
    """Team whitelist should contain required fields."""
    assert "team_name" in ALLOWED_TEAM_SIGNALS
    assert "score_so_far" in ALLOWED_TEAM_SIGNALS


def test_whitelist_theme_tags():
    """Theme tags whitelist should contain NBA v1 themes."""
    assert "timeout_heavy" in ALLOWED_THEME_TAGS
    assert "crunch_time" in ALLOWED_THEME_TAGS
    assert "overtime" in ALLOWED_THEME_TAGS
    assert "defensive_intensity" in ALLOWED_THEME_TAGS
    assert "hot_shooting" in ALLOWED_THEME_TAGS
