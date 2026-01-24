"""Stub implementations for unimplemented pipeline stages.

These stages are placeholders for future implementation.
Each raises NotImplementedError to make it explicit these aren't ready for use.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..models import StageInput, StageOutput

if TYPE_CHECKING:
    from ....db import AsyncSession


async def execute_derive_signals(stage_input: StageInput) -> StageOutput:
    """Derive signals from normalized PBP data.

    NOT YET IMPLEMENTED - placeholder for future stage.
    """
    raise NotImplementedError("DERIVE_SIGNALS stage not yet implemented")


async def execute_generate_moments(stage_input: StageInput) -> StageOutput:
    """Generate moments from derived signals.

    NOT YET IMPLEMENTED - placeholder for future stage.
    """
    raise NotImplementedError("GENERATE_MOMENTS stage not yet implemented")


async def execute_validate_moments(stage_input: StageInput) -> StageOutput:
    """Validate generated moments.

    NOT YET IMPLEMENTED - placeholder for future stage.
    """
    raise NotImplementedError("VALIDATE_MOMENTS stage not yet implemented")


async def execute_finalize_moments(
    session: "AsyncSession",
    stage_input: StageInput,
    run_uuid: str,
) -> StageOutput:
    """Finalize moments and persist to database.

    NOT YET IMPLEMENTED - placeholder for future stage.
    """
    raise NotImplementedError("FINALIZE_MOMENTS stage not yet implemented")
