"""Stub implementations for unimplemented pipeline stages.

These stages are placeholders for future implementation.
Each returns a no-op StageOutput to allow pipeline runs to complete,
while logging that the stage was skipped.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..models import StageInput, StageOutput

if TYPE_CHECKING:
    from ....db import AsyncSession


async def execute_derive_signals(stage_input: StageInput) -> StageOutput:
    """Derive signals from normalized PBP data.

    NOT YET IMPLEMENTED - returns no-op output.
    """
    output = StageOutput(data={"skipped": True, "reason": "Stage not yet implemented"})
    output.add_log("DERIVE_SIGNALS stage skipped - not yet implemented", level="warning")
    return output


async def execute_generate_moments(stage_input: StageInput) -> StageOutput:
    """Generate moments from derived signals.

    NOT YET IMPLEMENTED - returns no-op output.
    """
    output = StageOutput(data={"skipped": True, "reason": "Stage not yet implemented"})
    output.add_log("GENERATE_MOMENTS stage skipped - not yet implemented", level="warning")
    return output


async def execute_validate_moments(stage_input: StageInput) -> StageOutput:
    """Validate generated moments.

    NOT YET IMPLEMENTED - returns no-op output.
    """
    output = StageOutput(data={"skipped": True, "reason": "Stage not yet implemented"})
    output.add_log("VALIDATE_MOMENTS stage skipped - not yet implemented", level="warning")
    return output


async def execute_finalize_moments(
    session: "AsyncSession",
    stage_input: StageInput,
    run_uuid: str,
) -> StageOutput:
    """Finalize moments and persist to database.

    NOT YET IMPLEMENTED - returns no-op output.
    """
    output = StageOutput(data={"skipped": True, "reason": "Stage not yet implemented"})
    output.add_log("FINALIZE_MOMENTS stage skipped - not yet implemented", level="warning")
    return output
