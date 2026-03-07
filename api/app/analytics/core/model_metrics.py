"""Long-term model performance metrics.

Calculates statistical measures of prediction quality over a dataset
of predictions with recorded outcomes: Brier score, log loss, MAE,
and calibration curves.

Usage::

    metrics = ModelMetrics()
    score = metrics.brier_score(0.61, 1)
    report = metrics.compute_all(predictions)
"""

from __future__ import annotations

import math
from typing import Any


class ModelMetrics:
    """Compute aggregate model performance metrics."""

    def brier_score(self, predicted_prob: float, actual_outcome: int) -> float:
        """Brier score for a single prediction.

        Args:
            predicted_prob: Predicted probability of event (0-1).
            actual_outcome: 1 if event occurred, 0 otherwise.

        Returns:
            Squared error between prediction and outcome.
        """
        return (predicted_prob - actual_outcome) ** 2

    def log_loss(self, predicted_prob: float, actual_outcome: int) -> float:
        """Log loss (cross-entropy) for a single prediction.

        Clips probability to [1e-15, 1-1e-15] to avoid log(0).
        """
        p = max(1e-15, min(1 - 1e-15, predicted_prob))
        if actual_outcome == 1:
            return -math.log(p)
        return -math.log(1 - p)

    def mean_absolute_error(
        self,
        predictions: list[tuple[float, float]],
    ) -> float:
        """Mean absolute error across prediction/actual pairs.

        Args:
            predictions: List of ``(predicted, actual)`` tuples.

        Returns:
            Average absolute difference.
        """
        if not predictions:
            return 0.0
        return sum(abs(p - a) for p, a in predictions) / len(predictions)

    def compute_all(
        self,
        evaluated_predictions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Compute all metrics from a dataset of evaluated predictions.

        Args:
            evaluated_predictions: List of prediction records with
                ``model_output`` and ``actual_result`` keys.

        Returns:
            Dict with brier_score, log_loss, mae_score, mae_total,
            winner_accuracy, and calibration_buckets.
        """
        if not evaluated_predictions:
            return self._empty_metrics()

        brier_scores: list[float] = []
        log_losses: list[float] = []
        score_errors: list[tuple[float, float]] = []
        total_errors: list[tuple[float, float]] = []
        correct = 0
        n = 0

        for pred in evaluated_predictions:
            model = pred.get("model_output", {})
            actual = pred.get("actual_result")
            if actual is None:
                continue

            home_score = actual.get("home_score", 0)
            away_score = actual.get("away_score", 0)
            actual_home_win = 1 if home_score > away_score else 0
            pred_wp = model.get("home_win_probability", 0.5)

            brier_scores.append(self.brier_score(pred_wp, actual_home_win))
            log_losses.append(self.log_loss(pred_wp, actual_home_win))

            pred_home = model.get("expected_home_score", 0)
            pred_away = model.get("expected_away_score", 0)
            score_errors.append((pred_home, home_score))
            score_errors.append((pred_away, away_score))
            total_errors.append(
                (pred_home + pred_away, home_score + away_score),
            )

            predicted_winner = "home" if pred_wp > 0.5 else "away"
            actual_winner = "home" if actual_home_win == 1 else "away"
            if predicted_winner == actual_winner:
                correct += 1
            n += 1

        if n == 0:
            return self._empty_metrics()

        calibration = self._calibration_buckets(evaluated_predictions)

        return {
            "total_predictions": n,
            "brier_score": round(sum(brier_scores) / n, 4),
            "log_loss": round(sum(log_losses) / n, 4),
            "mae_score": round(self.mean_absolute_error(score_errors), 2),
            "mae_total": round(self.mean_absolute_error(total_errors), 2),
            "winner_accuracy": round(correct / n, 4),
            "calibration_buckets": calibration,
        }

    def _calibration_buckets(
        self,
        predictions: list[dict[str, Any]],
        n_buckets: int = 10,
    ) -> list[dict[str, Any]]:
        """Group predictions into probability buckets for calibration curves.

        Divides [0, 1] into ``n_buckets`` equal bins and computes the
        average predicted probability and actual win rate per bin.
        """
        buckets: dict[int, list[tuple[float, int]]] = {
            i: [] for i in range(n_buckets)
        }

        for pred in predictions:
            model = pred.get("model_output", {})
            actual = pred.get("actual_result")
            if actual is None:
                continue

            pred_wp = model.get("home_win_probability", 0.5)
            actual_win = 1 if actual.get("home_score", 0) > actual.get("away_score", 0) else 0
            bucket_idx = min(int(pred_wp * n_buckets), n_buckets - 1)
            buckets[bucket_idx].append((pred_wp, actual_win))

        result = []
        for i in range(n_buckets):
            entries = buckets[i]
            if not entries:
                continue
            avg_pred = sum(p for p, _ in entries) / len(entries)
            avg_actual = sum(a for _, a in entries) / len(entries)
            result.append({
                "bucket": f"{i / n_buckets:.1f}-{(i + 1) / n_buckets:.1f}",
                "count": len(entries),
                "avg_predicted": round(avg_pred, 4),
                "avg_actual": round(avg_actual, 4),
            })

        return result

    def _empty_metrics(self) -> dict[str, Any]:
        return {
            "total_predictions": 0,
            "brier_score": 0.0,
            "log_loss": 0.0,
            "mae_score": 0.0,
            "mae_total": 0.0,
            "winner_accuracy": 0.0,
            "calibration_buckets": [],
        }
