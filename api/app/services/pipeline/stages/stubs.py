"""Stub implementations for unimplemented pipeline stages.

These stages are placeholders for future implementation.
Each returns a no-op StageOutput to allow pipeline runs to complete,
while logging that the stage was skipped.
"""

from __future__ import annotations

from ..models import StageInput, StageOutput


async def execute_derive_signals(stage_input: StageInput) -> StageOutput:
    """Derive signals from normalized PBP data.

    NOTE: This stage is marked for deletion per Story contract review.
    The Story contract specifies that moments are derived DIRECTLY from PBP,
    not from signals. This stub remains only for pipeline structure compatibility.
    """
    output = StageOutput(data={"skipped": True, "reason": "Stage marked for deletion"})
    output.add_log(
        "DERIVE_SIGNALS stage skipped - marked for deletion per Story contract",
        level="warning",
    )
    return output
