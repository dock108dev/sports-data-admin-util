"""Pipeline models and data structures.

This module defines the core data structures used by the pipeline executor
and individual stage implementations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class PipelineStage(str, Enum):
    """Pipeline stages for game processing.
    
    Stages are executed in order. Each stage consumes the output of the
    previous stage and produces output for the next stage.
    """

    NORMALIZE_PBP = "NORMALIZE_PBP"
    DERIVE_SIGNALS = "DERIVE_SIGNALS"
    GENERATE_MOMENTS = "GENERATE_MOMENTS"
    VALIDATE_MOMENTS = "VALIDATE_MOMENTS"
    FINALIZE_MOMENTS = "FINALIZE_MOMENTS"

    @classmethod
    def ordered_stages(cls) -> list["PipelineStage"]:
        """Return stages in execution order."""
        return [
            cls.NORMALIZE_PBP,
            cls.DERIVE_SIGNALS,
            cls.GENERATE_MOMENTS,
            cls.VALIDATE_MOMENTS,
            cls.FINALIZE_MOMENTS,
        ]

    def next_stage(self) -> "PipelineStage | None":
        """Return the next stage in the pipeline, or None if this is the last."""
        stages = self.ordered_stages()
        try:
            idx = stages.index(self)
            if idx < len(stages) - 1:
                return stages[idx + 1]
            return None
        except ValueError:
            return None

    def previous_stage(self) -> "PipelineStage | None":
        """Return the previous stage in the pipeline, or None if this is the first."""
        stages = self.ordered_stages()
        try:
            idx = stages.index(self)
            if idx > 0:
                return stages[idx - 1]
            return None
        except ValueError:
            return None


@dataclass
class StageInput:
    """Input data for a pipeline stage.
    
    Attributes:
        game_id: The game being processed
        run_id: The pipeline run ID
        previous_output: Output from the previous stage (None for first stage)
        game_context: Game metadata for team name resolution
    """
    game_id: int
    run_id: int
    previous_output: dict[str, Any] | None = None
    game_context: dict[str, str] = field(default_factory=dict)


@dataclass
class StageOutput:
    """Output data from a pipeline stage.
    
    Attributes:
        data: Stage-specific output data (stored in output_json)
        logs: Log entries generated during execution
    """
    data: dict[str, Any]
    logs: list[dict[str, Any]] = field(default_factory=list)

    def add_log(self, message: str, level: str = "info") -> None:
        """Add a log entry."""
        self.logs.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "message": message,
        })


@dataclass
class StageResult:
    """Result of executing a pipeline stage.
    
    Attributes:
        stage: The stage that was executed
        success: Whether the stage completed successfully
        output: Stage output data (None if failed)
        error: Error message if failed
        duration_seconds: Time taken to execute the stage
    """
    stage: PipelineStage
    success: bool
    output: StageOutput | None = None
    error: str | None = None
    duration_seconds: float = 0.0

    @property
    def failed(self) -> bool:
        return not self.success


@dataclass
class NormalizedPBPOutput:
    """Output schema for NORMALIZE_PBP stage.
    
    Contains the normalized play-by-play events with phase assignments
    and synthetic timestamps.
    """
    pbp_events: list[dict[str, Any]]
    game_start: str  # ISO format datetime
    game_end: str    # ISO format datetime
    has_overtime: bool
    total_plays: int
    phase_boundaries: dict[str, tuple[str, str]]  # phase -> (start, end) ISO datetimes

    def to_dict(self) -> dict[str, Any]:
        return {
            "pbp_events": self.pbp_events,
            "game_start": self.game_start,
            "game_end": self.game_end,
            "has_overtime": self.has_overtime,
            "total_plays": self.total_plays,
            "phase_boundaries": self.phase_boundaries,
        }


@dataclass
class DerivedSignalsOutput:
    """Output schema for DERIVE_SIGNALS stage.
    
    Contains the computed lead states, tier crossings, and runs
    derived from the normalized PBP events.
    """
    lead_states: list[dict[str, Any]]   # Lead state at each play
    tier_crossings: list[dict[str, Any]]  # Detected tier crossings
    runs: list[dict[str, Any]]          # Detected scoring runs
    thresholds: list[int]               # Lead ladder thresholds used

    def to_dict(self) -> dict[str, Any]:
        return {
            "lead_states": self.lead_states,
            "tier_crossings": self.tier_crossings,
            "runs": self.runs,
            "thresholds": self.thresholds,
        }


@dataclass
class GeneratedMomentsOutput:
    """Output schema for GENERATE_MOMENTS stage.
    
    Contains the partitioned moments with all metadata, plus a full
    generation trace for explainability.
    """
    moments: list[dict[str, Any]]
    notable_moments: list[dict[str, Any]]
    moment_count: int
    budget: int
    within_budget: bool
    # Generation trace for explainability
    generation_trace: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        result = {
            "moments": self.moments,
            "notable_moments": self.notable_moments,
            "moment_count": self.moment_count,
            "budget": self.budget,
            "within_budget": self.within_budget,
        }
        if self.generation_trace is not None:
            result["generation_trace"] = self.generation_trace
        return result


@dataclass
class ValidationOutput:
    """Output schema for VALIDATE_MOMENTS stage.
    
    Contains the validation report and pass/fail status.
    """
    passed: bool
    critical_passed: bool
    warnings_count: int
    errors: list[str]
    warnings: list[str]
    validation_details: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "critical_passed": self.critical_passed,
            "warnings_count": self.warnings_count,
            "errors": self.errors,
            "warnings": self.warnings,
            "validation_details": self.validation_details,
        }


@dataclass
class FinalizedOutput:
    """Output schema for FINALIZE_MOMENTS stage.
    
    Contains references to the persisted artifact.
    """
    artifact_id: int
    timeline_events: int
    moment_count: int
    generated_at: str  # ISO format datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "timeline_events": self.timeline_events,
            "moment_count": self.moment_count,
            "generated_at": self.generated_at,
        }
