"""Base interface for all ML models in the analytics pipeline.

All sport-specific models must inherit from ``BaseModel`` and implement
the ``predict`` and ``predict_proba`` methods. This ensures a uniform
contract between the model layer and the simulation engine.

Usage::

    class MyModel(BaseModel):
        model_type = "plate_appearance"
        sport = "mlb"

        def predict(self, features):
            ...
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseModel(ABC):
    """Abstract base class for all analytics ML models.

    Subclasses must set ``model_type`` and ``sport`` class attributes
    and implement ``predict`` and ``predict_proba``.
    """

    model_type: str = ""
    sport: str = ""

    def __init__(self) -> None:
        self._model: Any = None
        self._loaded = False

    @property
    def is_loaded(self) -> bool:
        """Whether the underlying model artifact has been loaded."""
        return self._loaded

    def load(self, model_path: str | None = None) -> None:
        """Load a serialized model artifact.

        Args:
            model_path: Path to the serialized model file.
                If ``None``, the model should use built-in defaults.
        """
        if model_path is not None:
            from .model_loader import ModelLoader
            loader = ModelLoader()
            self._model = loader.load_model(model_path)
            self._loaded = True

    @abstractmethod
    def predict(self, features: dict[str, Any]) -> dict[str, Any]:
        """Generate a prediction from input features.

        Args:
            features: Feature dict (sport-specific keys).

        Returns:
            Prediction dict (sport-specific structure).
        """

    @abstractmethod
    def predict_proba(self, features: dict[str, Any]) -> dict[str, float]:
        """Generate probability distributions from input features.

        Args:
            features: Feature dict (sport-specific keys).

        Returns:
            Dict mapping outcome labels to probabilities (sum to ~1.0).
        """

    def get_info(self) -> dict[str, Any]:
        """Return metadata about this model."""
        return {
            "model_type": self.model_type,
            "sport": self.sport,
            "loaded": self._loaded,
            "class": self.__class__.__name__,
        }
