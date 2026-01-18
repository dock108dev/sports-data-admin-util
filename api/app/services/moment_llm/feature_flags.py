"""Task 6.5: Kill Switch & Feature Flags.

Controls for LLM augmentation features.
All flags default to False (AI disabled) for safety.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class LLMFeatureFlags:
    """Feature flags for LLM augmentation.

    All flags default to False (AI disabled) for safety.
    Enable explicitly per-league, per-environment, or per-game.
    """

    enable_moment_rewrite: bool = False
    enable_transitions: bool = False
    enable_tone_profiles: bool = False

    league_overrides: dict[str, "LLMFeatureFlags"] = field(default_factory=dict)
    game_overrides: dict[str, "LLMFeatureFlags"] = field(default_factory=dict)

    def for_game(self, game_id: str, league: str | None = None) -> "LLMFeatureFlags":
        """Get effective flags for a specific game."""
        if game_id in self.game_overrides:
            return self.game_overrides[game_id]

        if league and league in self.league_overrides:
            return self.league_overrides[league]

        return self

    @classmethod
    def all_enabled(cls) -> "LLMFeatureFlags":
        """Create flags with all features enabled."""
        return cls(
            enable_moment_rewrite=True,
            enable_transitions=True,
            enable_tone_profiles=True,
        )

    @classmethod
    def all_disabled(cls) -> "LLMFeatureFlags":
        """Create flags with all features disabled (safe default)."""
        return cls()
