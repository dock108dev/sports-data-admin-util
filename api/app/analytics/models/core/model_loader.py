"""Model artifact loader.

Handles loading serialized ML models from disk. Supports joblib
(scikit-learn) and pickle formats.

Usage::

    loader = ModelLoader()
    model = loader.load_model("models/mlb/pa_model_v1.pkl")
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


class ModelLoader:
    """Loads serialized ML model artifacts from the filesystem."""

    def load_model(self, model_path: str) -> Any:
        """Load a model from the given path.

        Tries joblib first, falls back to pickle.

        Args:
            model_path: Absolute or relative path to the model file.

        Returns:
            The deserialized model object.

        Raises:
            FileNotFoundError: If the model file does not exist.
            RuntimeError: If the file cannot be loaded.
        """
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Model file not found: {model_path}")

        try:
            return self._load_joblib(model_path)
        except Exception:
            logger.debug("joblib_load_failed, trying pickle", extra={"path": model_path})

        try:
            return self._load_pickle(model_path)
        except Exception as exc:
            raise RuntimeError(f"Failed to load model from {model_path}: {exc}") from exc

    def _load_joblib(self, path: str) -> Any:
        import joblib
        return joblib.load(path)

    def _load_pickle(self, path: str) -> Any:
        import pickle
        with open(path, "rb") as f:
            return pickle.load(f)  # noqa: S301
