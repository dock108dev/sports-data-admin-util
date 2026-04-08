"""NHL feature builder for ML models.

Converts NHL analytics profiles (home team, away team) into feature
vectors for shot and game-level ML models.
"""

from __future__ import annotations

from typing import Any

from app.analytics.features.core.feature_vector import FeatureVector, build_features_from_spec
from app.analytics.sports.nhl.constants import FEATURE_BASELINES as _BASELINES

# Shot model features: (feature_name, source_entity, source_key)
_SHOT_FEATURES: list[tuple[str, str, str]] = [
    (f"{side}_{key}", f"{side}_profile", key)
    for side in ("home", "away")
    for key in (
        "xgoals_for", "xgoals_against", "corsi_pct", "fenwick_pct",
        "shooting_pct", "save_pct", "pdo",
    )
]

# Market probability features
_MARKET_FEATURES: list[tuple[str, str, str]] = [
    ("market_home_wp", "market_profile", "home_wp"),
    ("market_away_wp", "market_profile", "away_wp"),
]

_GAME_FEATURES: list[tuple[str, str, str]] = _SHOT_FEATURES + _MARKET_FEATURES


class NHLFeatureBuilder:
    """Build NHL feature vectors from analytics profiles."""

    def build_features(
        self,
        entity_profiles: dict[str, Any],
        model_type: str,
    ) -> FeatureVector:
        if model_type in ("shot", "game"):
            return build_features_from_spec(
                _GAME_FEATURES, entity_profiles, _BASELINES,
            )
        return FeatureVector({})
