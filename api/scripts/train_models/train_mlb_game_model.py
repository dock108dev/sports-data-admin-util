#!/usr/bin/env python
"""Train MLB game outcome classification model.

Usage::

    cd api
    python -m scripts.train_models.train_mlb_game_model

Trains a GradientBoostingClassifier on game win/loss outcomes
using the configured feature set from ``mlb_game_model.yaml``.
"""

from __future__ import annotations

import json
import sys

from app.analytics.training.core.training_pipeline import TrainingPipeline


def main() -> None:
    pipeline = TrainingPipeline(
        sport="mlb",
        model_type="game",
        config_name="mlb_game_model",
        model_id="mlb_game_model_v1",
        random_state=42,
        test_size=0.2,
    )

    result = pipeline.run()

    if "error" in result:
        print(f"Training failed: {result['error']}")
        sys.exit(1)

    print("Training complete:")
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
