"""Feature configuration registry.

Maintains a registry of named feature configurations, allowing
runtime switching between configs for experimentation.

Usage::

    registry = FeatureConfigRegistry()
    registry.register("mlb_pa_model_v1", config)
    active = registry.get_config("mlb_pa_model_v1")
"""

from __future__ import annotations

import logging
from typing import Any

from .feature_config_loader import FeatureConfig, FeatureConfigLoader

logger = logging.getLogger(__name__)


class FeatureConfigRegistry:
    """Register and retrieve feature configurations by name."""

    def __init__(self, loader: FeatureConfigLoader | None = None) -> None:
        self._loader = loader or FeatureConfigLoader()
        self._configs: dict[str, FeatureConfig] = {}
        self._active: dict[str, str] = {}  # (sport, model_type) key -> config name

    def register(self, name: str, config: FeatureConfig) -> None:
        """Register a feature config under the given name."""
        self._configs[name] = config
        logger.info("feature_config_registered", extra={"name": name, "sport": config.sport})

    def get_config(self, name: str) -> FeatureConfig | None:
        """Retrieve a registered config by name.

        Falls back to loading from disk if not registered.
        """
        if name in self._configs:
            return self._configs[name]

        try:
            config = self._loader.load_config(name)
            self._configs[name] = config
            return config
        except FileNotFoundError:
            return None

    def set_active(self, sport: str, model_type: str, config_name: str) -> None:
        """Set the active config for a sport/model_type pair."""
        key = f"{sport}:{model_type}"
        self._active[key] = config_name

    def get_active(self, sport: str, model_type: str) -> FeatureConfig | None:
        """Get the active config for a sport/model_type pair."""
        key = f"{sport}:{model_type}"
        name = self._active.get(key)
        if name is None:
            return None
        return self.get_config(name)

    def list_configs(self) -> list[dict[str, Any]]:
        """List all registered config names and metadata."""
        result = []
        for name, config in self._configs.items():
            result.append({
                "name": name,
                "model": config.model,
                "sport": config.sport,
                "feature_count": len(config.get_enabled_features()),
            })
        return result

    def list_available(self) -> list[str]:
        """List config names available on disk and in registry."""
        disk = set(self._loader.list_configs())
        registered = set(self._configs.keys())
        return sorted(disk | registered)
