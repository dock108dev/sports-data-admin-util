"""Model registry for tracking and loading available ML models.

Maintains a catalog of registered models with version tracking and
active-model selection. The simulation engine queries the registry
to obtain the active model for a given sport and model type.

Usage::

    registry = ModelRegistry()
    registry.register_model({
        "model_id": "mlb_pa_model_v1",
        "sport": "mlb",
        "model_type": "plate_appearance",
        "version": 1,
        "path": "models/mlb/pa_model_v1.pkl",
        "active": True,
    })
    model = registry.get_active_model("mlb", "plate_appearance")
"""

from __future__ import annotations

import importlib
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Built-in model classes: (sport, model_type) -> (module_path, class_name)
_BUILTIN_MODELS: dict[tuple[str, str], tuple[str, str]] = {
    ("mlb", "plate_appearance"): (
        "app.analytics.models.sports.mlb.pa_model",
        "MLBPlateAppearanceModel",
    ),
    ("mlb", "game"): (
        "app.analytics.models.sports.mlb.game_model",
        "MLBGameModel",
    ),
}


class ModelRegistry:
    """Tracks registered ML models and resolves active models.

    Models can be registered explicitly or loaded from built-in
    defaults. Each model record includes sport, type, version,
    optional file path, and active flag.
    """

    def __init__(self) -> None:
        self._models: dict[str, dict[str, Any]] = {}

    def register_model(self, model_info: dict[str, Any]) -> str:
        """Register a model in the catalog.

        Args:
            model_info: Model record with keys ``model_id``, ``sport``,
                ``model_type``, ``version``, ``path`` (optional),
                ``active`` (bool).

        Returns:
            The model_id.
        """
        model_id = model_info.get("model_id", "")
        if not model_id:
            raise ValueError("model_info must include 'model_id'")

        # If this model is set as active, deactivate others of same sport/type
        if model_info.get("active", False):
            sport = model_info.get("sport", "")
            model_type = model_info.get("model_type", "")
            for existing in self._models.values():
                if (
                    existing.get("sport") == sport
                    and existing.get("model_type") == model_type
                    and existing.get("model_id") != model_id
                ):
                    existing["active"] = False

        self._models[model_id] = model_info
        logger.info("model_registered", extra={"model_id": model_id})
        return model_id

    def get_model_info(self, model_id: str) -> dict[str, Any] | None:
        """Retrieve a model record by ID."""
        return self._models.get(model_id)

    def get_active_model(self, sport: str, model_type: str) -> Any | None:
        """Get the active model instance for a sport and model type.

        First checks registered models, then falls back to built-in
        defaults. Returns an instantiated model (not just metadata).

        Args:
            sport: Sport code (e.g., ``"mlb"``).
            model_type: Model type (e.g., ``"plate_appearance"``, ``"game"``).

        Returns:
            Instantiated model object, or ``None`` if unavailable.
        """
        sport = sport.lower()

        # Check registered models first
        for info in self._models.values():
            if (
                info.get("sport") == sport
                and info.get("model_type") == model_type
                and info.get("active", False)
            ):
                return self._instantiate_model(info)

        # Fall back to built-in
        return self._load_builtin(sport, model_type)

    def get_active_model_info(
        self,
        sport: str,
        model_type: str,
    ) -> dict[str, Any] | None:
        """Get metadata for the active model (without instantiation)."""
        sport = sport.lower()
        for info in self._models.values():
            if (
                info.get("sport") == sport
                and info.get("model_type") == model_type
                and info.get("active", False)
            ):
                return info
        return None

    def list_models(
        self,
        sport: str | None = None,
        model_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """List registered models, optionally filtered."""
        records = list(self._models.values())
        if sport:
            records = [r for r in records if r.get("sport") == sport.lower()]
        if model_type:
            records = [r for r in records if r.get("model_type") == model_type]
        return records

    def set_active(self, model_id: str) -> bool:
        """Set a registered model as the active one for its sport/type.

        Returns:
            ``True`` if the model was found and activated.
        """
        info = self._models.get(model_id)
        if info is None:
            return False

        sport = info.get("sport", "")
        model_type = info.get("model_type", "")

        # Deactivate others
        for existing in self._models.values():
            if (
                existing.get("sport") == sport
                and existing.get("model_type") == model_type
            ):
                existing["active"] = False

        info["active"] = True
        return True

    def _instantiate_model(self, info: dict[str, Any]) -> Any | None:
        """Create a model instance from a registry record."""
        class_path = info.get("class_path")
        if class_path:
            module_path, class_name = class_path.rsplit(".", 1)
            mod = importlib.import_module(module_path)
            cls = getattr(mod, class_name)
            instance = cls()
        else:
            # Try built-in
            sport = info.get("sport", "")
            model_type = info.get("model_type", "")
            instance = self._load_builtin(sport, model_type)
            if instance is None:
                return None

        # Load artifact if path specified
        path = info.get("path")
        if path:
            instance.load(path)

        return instance

    def _load_builtin(self, sport: str, model_type: str) -> Any | None:
        """Load a built-in model class from the registry."""
        entry = _BUILTIN_MODELS.get((sport, model_type))
        if entry is None:
            return None

        module_path, class_name = entry
        mod = importlib.import_module(module_path)
        cls = getattr(mod, class_name)
        return cls()
