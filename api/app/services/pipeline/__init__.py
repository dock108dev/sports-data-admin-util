"""Game Pipeline Service.

Legacy moment stages removed. System is now chapters-first.

The pipeline framework remains for potential future use with chapter generation stages.
"""

from .executor import PipelineExecutor
from .models import (
    PipelineStage,
    StageInput,
    StageOutput,
    StageResult,
)

__all__ = [
    "PipelineExecutor",
    "PipelineStage",
    "StageInput",
    "StageOutput",
    "StageResult",
]
