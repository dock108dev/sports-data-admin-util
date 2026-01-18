"""Game Pipeline Service.

This module provides the replayable game pipeline that decouples data scraping
from moment generation. Each game can be processed through explicit stages:

1. NORMALIZE_PBP - Build normalized PBP events with phases
2. DERIVE_SIGNALS - Compute lead ladder states and tier crossings  
3. GENERATE_MOMENTS - Partition game into narrative moments
4. VALIDATE_MOMENTS - Run validation checks
5. FINALIZE_MOMENTS - Persist final timeline artifact

Key behaviors:
- Prod mode (auto_chain=True): Automatically proceeds through all stages
- Dev/Admin mode (auto_chain=False): Pauses after each stage for inspection
- Each stage persists its output for replayability

Usage:
    from app.services.pipeline import PipelineExecutor
    
    executor = PipelineExecutor(session)
    run = await executor.start_pipeline(game_id, triggered_by="admin")
    result = await executor.execute_stage(run.id, PipelineStage.NORMALIZE_PBP)
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
