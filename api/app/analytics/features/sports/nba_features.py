"""NBA feature builder for ML models.

Converts NBA analytics profiles (home team, away team) into feature
vectors for possession and game-level ML models.
"""

from __future__ import annotations

from typing import Any

from app.analytics.features.core.feature_vector import FeatureVector, build_features_from_spec
from app.analytics.sports.nba.constants import FEATURE_BASELINES as _BASELINES

# Possession model features: (feature_name, source_entity, source_key)
_POSSESSION_FEATURES: list[tuple[str, str, str]] = [
    (f"{side}_{key}", f"{side}_profile", key)
    for side in ("home", "away")
    for key in (
        "off_rating", "def_rating", "pace", "efg_pct", "ts_pct",
        "tov_pct", "orb_pct", "ft_rate", "fg3_pct", "ast_pct",
    )
]

# Market probability features (devigged Pinnacle lines)
_MARKET_FEATURES: list[tuple[str, str, str]] = [
    ("market_home_wp", "market_profile", "home_wp"),
    ("market_away_wp", "market_profile", "away_wp"),
]

_GAME_FEATURES: list[tuple[str, str, str]] = _POSSESSION_FEATURES + _MARKET_FEATURES


class NBAFeatureBuilder:
    """Build NBA feature vectors from analytics profiles."""

    def build_features(
        self,
        entity_profiles: dict[str, Any],
        model_type: str,
    ) -> FeatureVector:
        if model_type in ("possession", "game"):
            return build_features_from_spec(
                _GAME_FEATURES, entity_profiles, _BASELINES,
            )
        return FeatureVector({})
