"""MLB pitch outcome labeler.

Maps MLB Stats API pitch ``details.code`` values to canonical pitch
outcome labels used by the ``MLBPitchOutcomeModel``.

Canonical outcomes:
- ball
- called_strike
- swinging_strike
- foul
- in_play
"""

from __future__ import annotations

PITCH_OUTCOME_LABELS: list[str] = [
    "ball",
    "called_strike",
    "swinging_strike",
    "foul",
    "in_play",
]

# Mapping from MLB Stats API pitch details.code to canonical outcome.
_PITCH_CODE_MAP: dict[str, str] = {
    # Balls
    "B": "ball",
    "*B": "ball",
    # Called strikes
    "C": "called_strike",
    # Swinging strikes
    "S": "swinging_strike",
    "W": "swinging_strike",
    "M": "swinging_strike",
    "Q": "swinging_strike",
    # Fouls
    "F": "foul",
    "R": "foul",
    "L": "foul",
    "T": "foul",
    # In play
    "X": "in_play",
    "D": "in_play",
    "E": "in_play",
}


def label_pitch_code(code: str) -> str | None:
    """Map an MLB Stats API pitch code to a canonical pitch outcome.

    Args:
        code: The ``details.code`` value from a ``playEvents`` entry.

    Returns:
        Canonical pitch outcome string, or ``None`` if the code is
        unrecognized or not a pitch event.
    """
    if not code:
        return None
    return _PITCH_CODE_MAP.get(code.strip())
