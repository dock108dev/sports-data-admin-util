"""Task 6.3: Tone & Style Profiles.

Tone profiles affect wording, not facts.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ToneProfile(Enum):
    """Tone profiles that affect wording, not facts."""

    NEUTRAL = "neutral"  # Default, objective, factual
    ANALYST = "analyst"  # Technical, strategic focus
    FAN = "fan"  # Energetic, emotional
    MINIMAL = "minimal"  # Brief, headline-style


@dataclass
class ToneConfig:
    """Configuration for a tone profile."""

    profile: ToneProfile = ToneProfile.NEUTRAL
    verb_energy: float = 0.5  # 0.0 = calm, 1.0 = intense
    adjective_level: float = 0.3  # 0.0 = none, 1.0 = liberal
    prefer_short_sentences: bool = False
    allow_questions: bool = False

    @classmethod
    def from_profile(cls, profile: ToneProfile) -> "ToneConfig":
        """Create config from a profile."""
        configs = {
            ToneProfile.NEUTRAL: cls(
                profile=ToneProfile.NEUTRAL,
                verb_energy=0.5,
                adjective_level=0.3,
                prefer_short_sentences=False,
                allow_questions=False,
            ),
            ToneProfile.ANALYST: cls(
                profile=ToneProfile.ANALYST,
                verb_energy=0.3,
                adjective_level=0.2,
                prefer_short_sentences=False,
                allow_questions=False,
            ),
            ToneProfile.FAN: cls(
                profile=ToneProfile.FAN,
                verb_energy=0.9,
                adjective_level=0.7,
                prefer_short_sentences=True,
                allow_questions=True,
            ),
            ToneProfile.MINIMAL: cls(
                profile=ToneProfile.MINIMAL,
                verb_energy=0.4,
                adjective_level=0.1,
                prefer_short_sentences=True,
                allow_questions=False,
            ),
        }
        return configs.get(profile, configs[ToneProfile.NEUTRAL])

    def to_prompt_instructions(self) -> str:
        """Convert to prompt instructions for LLM."""
        instructions = []

        if self.profile == ToneProfile.NEUTRAL:
            instructions.append("Use objective, factual language.")
        elif self.profile == ToneProfile.ANALYST:
            instructions.append(
                "Use analytical, strategic language. Focus on tactics and execution."
            )
        elif self.profile == ToneProfile.FAN:
            instructions.append(
                "Use energetic, engaging language. Capture the excitement."
            )
        elif self.profile == ToneProfile.MINIMAL:
            instructions.append("Use brief, headline-style language. Be concise.")

        if self.prefer_short_sentences:
            instructions.append("Keep sentences short and punchy.")

        if not self.allow_questions:
            instructions.append("Do not use rhetorical questions.")

        return " ".join(instructions)
