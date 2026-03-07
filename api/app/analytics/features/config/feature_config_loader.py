"""Feature configuration loader.

Loads YAML feature configurations from disk, validates their format,
and provides access to enabled features and weights.

Usage::

    loader = FeatureConfigLoader()
    config = loader.load_config("mlb_pa_model")
    enabled = config.get_enabled_features()
    weights = config.get_weights()
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_DEFAULT_CONFIG_DIR = Path(__file__).resolve().parents[3] / ".." / "config" / "features"


class FeatureConfig:
    """Parsed and validated feature configuration."""

    __slots__ = ("_model", "_sport", "_features")

    def __init__(self, model: str, sport: str, features: dict[str, dict[str, Any]]) -> None:
        self._model = model
        self._sport = sport
        self._features = features

    @property
    def model(self) -> str:
        return self._model

    @property
    def sport(self) -> str:
        return self._sport

    @property
    def features(self) -> dict[str, dict[str, Any]]:
        return dict(self._features)

    def get_enabled_features(self) -> list[str]:
        """Return names of features with ``enabled: true``."""
        return [
            name for name, cfg in self._features.items()
            if cfg.get("enabled", True)
        ]

    def get_weights(self) -> dict[str, float]:
        """Return weight map for enabled features."""
        return {
            name: cfg.get("weight", 1.0)
            for name, cfg in self._features.items()
            if cfg.get("enabled", True)
        }

    def to_builder_config(self) -> dict[str, dict[str, Any]]:
        """Return config dict suitable for ``FeatureBuilder.build_features()``."""
        return dict(self._features)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to plain dict."""
        return {
            "model": self._model,
            "sport": self._sport,
            "features": dict(self._features),
        }


class FeatureConfigLoader:
    """Load and validate YAML feature configurations."""

    def __init__(self, config_dir: str | Path | None = None) -> None:
        self._config_dir = Path(config_dir) if config_dir else _DEFAULT_CONFIG_DIR.resolve()

    def load_config(self, model_name: str) -> FeatureConfig:
        """Load a feature config by model name.

        Looks for ``<model_name>.yaml`` in the config directory.

        Args:
            model_name: Config file stem (e.g., ``"mlb_pa_model"``).

        Returns:
            Parsed ``FeatureConfig``.

        Raises:
            FileNotFoundError: Config file does not exist.
            ValueError: Config file has invalid format.
        """
        path = self._config_dir / f"{model_name}.yaml"
        if not path.exists():
            raise FileNotFoundError(f"Feature config not found: {path}")

        with open(path) as f:
            raw = yaml.safe_load(f)

        return self._parse(raw, str(path))

    def load_from_dict(self, data: dict[str, Any]) -> FeatureConfig:
        """Parse a feature config from a raw dict (e.g., API payload)."""
        return self._parse(data, "<dict>")

    def list_configs(self) -> list[str]:
        """Return available config names in the config directory."""
        if not self._config_dir.exists():
            return []
        return sorted(p.stem for p in self._config_dir.glob("*.yaml"))

    def _parse(self, raw: Any, source: str) -> FeatureConfig:
        """Validate and parse raw YAML data."""
        if not isinstance(raw, dict):
            raise ValueError(f"Invalid feature config ({source}): expected dict")

        model = raw.get("model", "unknown")
        sport = raw.get("sport", "unknown")
        features = raw.get("features")

        if not isinstance(features, dict):
            raise ValueError(f"Invalid feature config ({source}): 'features' must be a dict")

        parsed: dict[str, dict[str, Any]] = {}
        for name, cfg in features.items():
            if cfg is None:
                cfg = {}
            if not isinstance(cfg, dict):
                raise ValueError(
                    f"Invalid feature config ({source}): "
                    f"feature '{name}' must be a dict, got {type(cfg).__name__}"
                )
            parsed[name] = {
                "enabled": cfg.get("enabled", True),
                "weight": float(cfg.get("weight", 1.0)),
            }

        return FeatureConfig(model=model, sport=sport, features=parsed)
