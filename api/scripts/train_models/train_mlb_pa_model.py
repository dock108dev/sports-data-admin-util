#!/usr/bin/env python
"""Train MLB plate-appearance classification model.

Usage::

    cd api
    python -m scripts.train_models.train_mlb_pa_model

Trains a GradientBoostingClassifier on plate-appearance outcomes
using the configured feature set from ``mlb_pa_model.yaml``.
"""

from __future__ import annotations

import json
import sys

from app.analytics.training.core.training_pipeline import TrainingPipeline


def main() -> None:
    pipeline = TrainingPipeline(
        sport="mlb",
        model_type="plate_appearance",
        config_name="mlb_pa_model",
        model_id="mlb_pa_model_v1",
        random_state=42,
        test_size=0.2,
    )

    # Load data — the MLBTrainingPipeline.load_plate_appearance_training_data()
    # returns [] by default. Pass records via pipeline.run(records=...) or
    # implement database loading in mlb_training.py.
    result = pipeline.run()

    if "error" in result:
        print(f"Training failed: {result['error']}")
        sys.exit(1)

    print("Training complete:")
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
