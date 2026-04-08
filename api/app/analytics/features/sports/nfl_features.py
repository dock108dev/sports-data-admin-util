"""NFL feature builder for ML models.

Converts NFL analytics profiles (home team, away team) into feature
vectors for drive and game-level ML models.
"""

from __future__ import annotations

from typing import Any

from app.analytics.features.core.feature_vector import FeatureVector, build_features_from_spec
from app.analytics.sports.nfl.constants import FEATURE_BASELINES as _BASELINES

# Metrics from NFLGameAdvancedStats that serve as model inputs.
_GAME_METRIC_KEYS: list[str] = [
    "epa_per_play",
    "pass_epa",
    "rush_epa",
    "total_epa",
    "total_wpa",
    "success_rate",
    "pass_success_rate",
    "rush_success_rate",
    "explosive_play_rate",
    "avg_cpoe",
    "avg_air_yards",
    "avg_yac",
]

# Drive / game model features + market probability
_GAME_FEATURES: list[tuple[str, str, str]] = [
    (f"{side}_{key}", f"{side}_profile", key)
    for side in ("home", "away")
    for key in _GAME_METRIC_KEYS
] + [
    ("market_home_wp", "market_profile", "home_wp"),
    ("market_away_wp", "market_profile", "away_wp"),
]


class NFLFeatureBuilder:
    """Build NFL feature vectors from analytics profiles."""

    def build_features(
        self,
        entity_profiles: dict[str, Any],
        model_type: str,
    ) -> FeatureVector:
        if model_type in ("drive", "game"):
            return build_features_from_spec(
                _GAME_FEATURES, entity_profiles, _BASELINES,
            )
        return FeatureVector({})
