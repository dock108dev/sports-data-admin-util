"""Model calibration engine for comparing predictions to outcomes.

Evaluates individual prediction accuracy and detects systematic model
errors across a dataset of predictions with recorded outcomes.

Usage::

    cal = ModelCalibration()
    evaluation = cal.evaluate_prediction(prediction, actual_result)
    report = cal.calibration_report(evaluated_predictions)
"""

from __future__ import annotations

import logging
import math
from typing import Any

logger = logging.getLogger(__name__)


class ModelCalibration:
    """Compares model predictions against actual game outcomes."""

    def evaluate_prediction(
        self,
        prediction: dict[str, Any],
        actual_result: dict[str, Any],
    ) -> dict[str, Any]:
        """Evaluate a single prediction against the actual outcome.

        Args:
            prediction: Prediction record with ``model_output`` dict
                containing ``home_win_probability``,
                ``expected_home_score``, ``expected_away_score``.
            actual_result: ``{"home_score": int, "away_score": int}``.

        Returns:
            Dict of error metrics for this prediction.
        """
        model = prediction.get("model_output", {})
        home_score = actual_result.get("home_score", 0)
        away_score = actual_result.get("away_score", 0)
        actual_home_win = 1 if home_score > away_score else 0

        pred_home_wp = model.get("home_win_probability", 0.5)
        pred_home_score = model.get("expected_home_score", 0)
        pred_away_score = model.get("expected_away_score", 0)

        # Win probability error (Brier-style per-prediction)
        wp_error = (pred_home_wp - actual_home_win) ** 2

        # Score errors
        home_score_error = abs(pred_home_score - home_score)
        away_score_error = abs(pred_away_score - away_score)
        total_pred = pred_home_score + pred_away_score
        total_actual = home_score + away_score
        total_error = abs(total_pred - total_actual)

        # Correct prediction?
        predicted_winner = "home" if pred_home_wp > 0.5 else "away"
        actual_winner = "home" if actual_home_win == 1 else "away"
        correct = predicted_winner == actual_winner

        evaluation: dict[str, Any] = {
            "prediction_id": prediction.get("prediction_id"),
            "game_id": prediction.get("game_id"),
            "brier_score": round(wp_error, 6),
            "home_score_error": round(home_score_error, 2),
            "away_score_error": round(away_score_error, 2),
            "total_score_error": round(total_error, 2),
            "predicted_home_wp": pred_home_wp,
            "actual_home_win": actual_home_win,
            "correct_winner": correct,
        }

        # Sportsbook comparison if available
        sportsbook = prediction.get("sportsbook_lines")
        if sportsbook:
            evaluation["sportsbook_comparison"] = self._compare_to_sportsbook(
                pred_home_wp, actual_home_win, sportsbook,
            )

        return evaluation

    def calibration_report(
        self,
        evaluated_predictions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Generate a calibration report from evaluated predictions.

        Args:
            evaluated_predictions: List of prediction records that
                have ``actual_result`` attached.

        Returns:
            Dict with aggregate calibration metrics and bias analysis.
        """
        if not evaluated_predictions:
            return self._empty_report()

        evaluations = []
        for pred in evaluated_predictions:
            actual = pred.get("actual_result")
            if actual is None:
                continue
            evaluations.append(self.evaluate_prediction(pred, actual))

        if not evaluations:
            return self._empty_report()

        n = len(evaluations)
        avg_brier = sum(e["brier_score"] for e in evaluations) / n
        avg_home_err = sum(e["home_score_error"] for e in evaluations) / n
        avg_away_err = sum(e["away_score_error"] for e in evaluations) / n
        avg_total_err = sum(e["total_score_error"] for e in evaluations) / n
        accuracy = sum(1 for e in evaluations if e["correct_winner"]) / n

        # Bias detection
        bias = self._detect_bias(evaluated_predictions)

        return {
            "total_predictions": n,
            "brier_score": round(avg_brier, 4),
            "average_score_error": round((avg_home_err + avg_away_err) / 2, 2),
            "average_total_error": round(avg_total_err, 2),
            "winner_accuracy": round(accuracy, 4),
            "prediction_bias": bias,
        }

    def _detect_bias(
        self,
        predictions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Detect systematic prediction bias.

        Returns bias metrics: positive = over-prediction, negative = under.
        """
        home_wp_diffs: list[float] = []
        total_diffs: list[float] = []
        home_score_diffs: list[float] = []

        for pred in predictions:
            model = pred.get("model_output", {})
            actual = pred.get("actual_result")
            if actual is None:
                continue

            home_score = actual.get("home_score", 0)
            away_score = actual.get("away_score", 0)
            actual_home_win = 1 if home_score > away_score else 0

            pred_wp = model.get("home_win_probability", 0.5)
            home_wp_diffs.append(pred_wp - actual_home_win)

            pred_total = (
                model.get("expected_home_score", 0)
                + model.get("expected_away_score", 0)
            )
            actual_total = home_score + away_score
            total_diffs.append(pred_total - actual_total)

            pred_home = model.get("expected_home_score", 0)
            home_score_diffs.append(pred_home - home_score)

        if not home_wp_diffs:
            return {"home_bias": 0.0, "total_bias": 0.0, "home_score_bias": 0.0}

        n = len(home_wp_diffs)
        return {
            "home_bias": round(sum(home_wp_diffs) / n, 4),
            "total_bias": round(sum(total_diffs) / n, 2),
            "home_score_bias": round(sum(home_score_diffs) / n, 2),
        }

    def _compare_to_sportsbook(
        self,
        model_prob: float,
        actual_outcome: int,
        sportsbook: dict[str, Any],
    ) -> dict[str, Any]:
        """Compare model vs sportsbook accuracy for a single prediction."""
        from .odds_analysis import OddsAnalysis
        odds = OddsAnalysis()

        result: dict[str, Any] = {}
        home_ml = sportsbook.get("home_ml")
        if home_ml is not None:
            book_prob = odds.american_to_implied_probability(home_ml)
            model_error = abs(model_prob - actual_outcome)
            book_error = abs(book_prob - actual_outcome)
            result["model_error"] = round(model_error, 4)
            result["sportsbook_error"] = round(book_error, 4)
            result["model_closer"] = model_error < book_error

        return result

    def _empty_report(self) -> dict[str, Any]:
        return {
            "total_predictions": 0,
            "brier_score": 0.0,
            "average_score_error": 0.0,
            "average_total_error": 0.0,
            "winner_accuracy": 0.0,
            "prediction_bias": {
                "home_bias": 0.0,
                "total_bias": 0.0,
                "home_score_bias": 0.0,
            },
        }
