"""Prediction repository for storing and retrieving model predictions.

Stores pregame predictions linked to game IDs so they can later be
compared against actual outcomes for calibration analysis.

Usage::

    repo = PredictionRepository()
    pred_id = repo.save_prediction({
        "sport": "mlb",
        "game_id": "game_456",
        "home_team": "LAD",
        "away_team": "TOR",
        "model_output": {"home_win_probability": 0.61, ...},
    })
    pred = repo.get_prediction(pred_id)
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

logger = logging.getLogger(__name__)


class PredictionRepository:
    """Stores model predictions for later calibration evaluation.

    Default implementation uses an in-memory dict. Replace with a
    database-backed store for production persistence.
    """

    def __init__(self) -> None:
        self._store: dict[str, dict[str, Any]] = {}

    def save_prediction(self, prediction: dict[str, Any]) -> str:
        """Persist a model prediction.

        Args:
            prediction: Prediction record. Expected keys include
                ``sport``, ``game_id``, ``home_team``, ``away_team``,
                ``model_output``, and optionally ``sportsbook_lines``.

        Returns:
            Unique prediction ID.
        """
        pred_id = prediction.get("prediction_id") or str(uuid.uuid4())
        record: dict[str, Any] = {
            "prediction_id": pred_id,
            "sport": prediction.get("sport", "unknown"),
            "game_id": prediction.get("game_id"),
            "timestamp": prediction.get("timestamp", time.time()),
            "home_team": prediction.get("home_team"),
            "away_team": prediction.get("away_team"),
            "model_output": prediction.get("model_output", {}),
            "sportsbook_lines": prediction.get("sportsbook_lines"),
            "actual_result": prediction.get("actual_result"),
        }
        self._store[pred_id] = record
        logger.info("prediction_saved", extra={"prediction_id": pred_id})
        return pred_id

    def get_prediction(self, prediction_id: str) -> dict[str, Any] | None:
        """Retrieve a prediction by ID."""
        return self._store.get(prediction_id)

    def get_predictions_for_game(self, game_id: str) -> list[dict[str, Any]]:
        """Retrieve all predictions for a specific game."""
        return [
            p for p in self._store.values()
            if p.get("game_id") == game_id
        ]

    def list_predictions(
        self,
        sport: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """List predictions, optionally filtered by sport.

        Returns newest first.
        """
        records = list(self._store.values())
        if sport:
            records = [r for r in records if r.get("sport") == sport]
        records.sort(key=lambda r: r.get("timestamp", 0), reverse=True)
        return records[:limit]

    def record_outcome(
        self,
        prediction_id: str,
        actual_result: dict[str, Any],
    ) -> bool:
        """Attach an actual game outcome to a stored prediction.

        Args:
            prediction_id: The prediction to update.
            actual_result: ``{"home_score": int, "away_score": int}``.

        Returns:
            ``True`` if prediction was found and updated.
        """
        record = self._store.get(prediction_id)
        if record is None:
            return False
        record["actual_result"] = actual_result
        return True

    def get_evaluated_predictions(
        self,
        sport: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return predictions that have actual outcomes recorded."""
        records = [
            p for p in self._store.values()
            if p.get("actual_result") is not None
        ]
        if sport:
            records = [r for r in records if r.get("sport") == sport]
        return records

    @property
    def count(self) -> int:
        return len(self._store)
