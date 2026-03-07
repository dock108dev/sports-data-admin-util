"""MLB-specific training data loading and label extraction.

Provides sport-specific logic for loading MLB historical data
and extracting training labels for plate-appearance and game models.

Usage::

    mlb = MLBTrainingPipeline()
    records = mlb.load_plate_appearance_training_data()
    label = mlb.pa_label_fn(record)
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Plate appearance outcome classes
PA_OUTCOMES: list[str] = [
    "strikeout",
    "out",
    "walk",
    "single",
    "double",
    "triple",
    "home_run",
]


class MLBTrainingPipeline:
    """MLB-specific training data and label helpers.

    Data loading methods return empty lists by default. In production,
    these would query the database (SportsGame, MLBGameAdvancedStats,
    etc.). Training scripts can also pass records directly to the
    core TrainingPipeline.
    """

    def load_plate_appearance_training_data(self) -> list[dict[str, Any]]:
        """Load historical plate-appearance training data.

        Returns:
            List of record dicts with batter_profile, pitcher_profile,
            and label keys. Returns empty list if no data source
            is configured.
        """
        logger.info("mlb_pa_training_data_load_start")
        # Production: query MLBPlayerAdvancedStats + play-by-play data.
        # For now, returns empty — caller should pass records directly.
        return []

    def load_game_training_data(self) -> list[dict[str, Any]]:
        """Load historical game-level training data.

        Returns:
            List of record dicts with home_profile, away_profile,
            and label keys.
        """
        logger.info("mlb_game_training_data_load_start")
        # Production: query SportsGame with home/away team profiles.
        return []

    @staticmethod
    def pa_label_fn(record: dict[str, Any]) -> str | None:
        """Extract plate-appearance outcome label from a record.

        Looks for ``outcome`` or ``label`` key.
        Returns ``None`` if no valid label is found.
        """
        outcome = record.get("outcome") or record.get("label")
        if outcome is None:
            return None
        outcome = str(outcome).lower().strip()
        if outcome in PA_OUTCOMES:
            return outcome
        return None

    @staticmethod
    def game_label_fn(record: dict[str, Any]) -> int | None:
        """Extract game outcome label from a record.

        Returns 1 for home win, 0 for away win.
        Looks for ``home_win``, ``label``, or computes from scores.
        """
        if "home_win" in record:
            return int(record["home_win"])
        if "label" in record:
            return int(record["label"])
        home_score = record.get("home_score")
        away_score = record.get("away_score")
        if home_score is not None and away_score is not None:
            return 1 if home_score > away_score else 0
        return None

    @staticmethod
    def build_pa_record(
        batter_metrics: dict[str, Any],
        pitcher_metrics: dict[str, Any],
        outcome: str,
    ) -> dict[str, Any]:
        """Build a training record for plate-appearance model.

        Convenience method for constructing training data in the
        format expected by the DatasetBuilder.
        """
        return {
            "batter_profile": {"metrics": batter_metrics},
            "pitcher_profile": {"metrics": pitcher_metrics},
            "outcome": outcome,
        }

    @staticmethod
    def build_game_record(
        home_metrics: dict[str, Any],
        away_metrics: dict[str, Any],
        home_win: bool,
        *,
        home_score: int | None = None,
        away_score: int | None = None,
    ) -> dict[str, Any]:
        """Build a training record for game model.

        Convenience method for constructing training data.
        """
        record: dict[str, Any] = {
            "home_profile": {"metrics": home_metrics},
            "away_profile": {"metrics": away_metrics},
            "home_win": int(home_win),
        }
        if home_score is not None:
            record["home_score"] = home_score
        if away_score is not None:
            record["away_score"] = away_score
        return record
