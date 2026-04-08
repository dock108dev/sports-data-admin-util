"""Feature vector representation for ML model input.

Wraps a dict of named features with deterministic ordering for
consistent array output between training and inference.

Usage::

    vec = FeatureVector(
        {"batter_contact_rate": 0.83, "pitcher_k_rate": 0.28},
        feature_order=["batter_contact_rate", "pitcher_k_rate"],
    )
    arr = vec.to_array()   # [0.83, 0.28]
    d = vec.to_dict()      # {"batter_contact_rate": 0.83, ...}
"""

from __future__ import annotations


class FeatureVector:
    """Immutable, ordered feature vector for ML model input.

    Args:
        features: Dict mapping feature names to numeric values.
        feature_order: Explicit ordering of feature names for
            ``to_array()``. If ``None``, uses sorted key order.
    """

    __slots__ = ("_features", "_order")

    def __init__(
        self,
        features: dict[str, float],
        feature_order: list[str] | None = None,
    ) -> None:
        self._features = dict(features)
        self._order = list(feature_order) if feature_order else sorted(features.keys())

    def to_array(self) -> list[float]:
        """Return features as an ordered numeric list.

        Uses the feature order specified at construction. Missing
        features default to ``0.0``.
        """
        return [self._features.get(k, 0.0) for k in self._order]

    def to_dict(self) -> dict[str, float]:
        """Return the raw feature dict."""
        return dict(self._features)

    @property
    def feature_names(self) -> list[str]:
        """Return the ordered feature names."""
        return list(self._order)

    @property
    def size(self) -> int:
        """Number of features in the ordered vector."""
        return len(self._order)

    def get(self, name: str, default: float = 0.0) -> float:
        """Get a single feature value by name."""
        return self._features.get(name, default)

    def __len__(self) -> int:
        return self.size

    def __repr__(self) -> str:
        return f"FeatureVector({len(self._order)} features)"


def build_features_from_spec(
    spec: list[tuple[str, str, str]],
    profiles: dict[str, object],
    baselines: dict[str, float],
) -> FeatureVector:
    """Build a FeatureVector from a (name, source, key) spec.

    This is the single implementation used by all sport-specific feature
    builders. Each profile value can be a flat dict, a dict with a
    ``metrics`` key, or an object with a ``.metrics`` attribute.

    Values are normalized against sport-specific baselines (ratio to
    baseline). Missing values default to 0.0.

    Args:
        spec: List of ``(feature_name, source_entity, source_key)`` tuples.
        profiles: Mapping of source entity names to profile data.
        baselines: Sport-specific baseline values for normalization.

    Returns:
        ``FeatureVector`` with features in spec order.
    """
    features: dict[str, float] = {}
    order: list[str] = []

    for feat_name, entity_key, source_key in spec:
        raw_profile = profiles.get(entity_key, {})

        # Extract metrics dict from various profile shapes
        if isinstance(raw_profile, dict):
            metrics = raw_profile.get("metrics", raw_profile)
        elif hasattr(raw_profile, "metrics"):
            metrics = raw_profile.metrics  # type: ignore[union-attr]
        else:
            metrics = {}

        val = metrics.get(source_key) if isinstance(metrics, dict) else None

        if val is not None:
            baseline = baselines.get(source_key, 1.0)
            features[feat_name] = round(
                float(val) / baseline if baseline else float(val), 4
            )
        else:
            features[feat_name] = 0.0

        order.append(feat_name)

    return FeatureVector(features, feature_order=order)
