"""Phase 6: LLM Augmentation & Narrative Guardrails

This module introduces the LLM as a controlled enhancement layer, not a decision-maker.

TASK 6.1: Constrained LLM Rewrite (per-moment)
TASK 6.2: Full-Game Narrative Stitching
TASK 6.3: Tone & Style Profiles
TASK 6.4: LLM Safety & Regression Guards
TASK 6.5: Kill Switch & Feature Flags

CRITICAL RULES:
- LLM cannot select moments
- LLM cannot change ordering
- LLM cannot invent stats
- LLM cannot override templates
- LLM cannot fix upstream bugs

If the LLM fails, we fall back — not forward.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Sequence, TYPE_CHECKING

if TYPE_CHECKING:
    from .moments import Moment

logger = logging.getLogger(__name__)


# =============================================================================
# TASK 6.5: KILL SWITCH & FEATURE FLAGS
# =============================================================================


@dataclass
class LLMFeatureFlags:
    """Feature flags for LLM augmentation.
    
    All flags default to False (AI disabled) for safety.
    Enable explicitly per-league, per-environment, or per-game.
    """
    
    # Per-moment rewriting
    enable_moment_rewrite: bool = False
    
    # Full-game transitions
    enable_transitions: bool = False
    
    # Tone profiles
    enable_tone_profiles: bool = False
    
    # Per-league overrides
    league_overrides: dict[str, "LLMFeatureFlags"] = field(default_factory=dict)
    
    # Per-game overrides (game_id -> flags)
    game_overrides: dict[str, "LLMFeatureFlags"] = field(default_factory=dict)
    
    def for_game(self, game_id: str, league: str | None = None) -> "LLMFeatureFlags":
        """Get effective flags for a specific game."""
        # Game override takes priority
        if game_id in self.game_overrides:
            return self.game_overrides[game_id]
        
        # Then league override
        if league and league in self.league_overrides:
            return self.league_overrides[league]
        
        # Default to self
        return self
    
    @classmethod
    def all_enabled(cls) -> "LLMFeatureFlags":
        """Create flags with all features enabled."""
        return cls(
            enable_moment_rewrite=True,
            enable_transitions=True,
            enable_tone_profiles=True,
        )
    
    @classmethod
    def all_disabled(cls) -> "LLMFeatureFlags":
        """Create flags with all features disabled (safe default)."""
        return cls()


# =============================================================================
# TASK 6.3: TONE & STYLE PROFILES
# =============================================================================


class ToneProfile(Enum):
    """Tone profiles that affect wording, not facts."""
    
    NEUTRAL = "neutral"      # Default, objective, factual
    ANALYST = "analyst"      # Technical, strategic focus
    FAN = "fan"              # Energetic, emotional
    MINIMAL = "minimal"      # Brief, headline-style


@dataclass
class ToneConfig:
    """Configuration for a tone profile."""
    
    profile: ToneProfile = ToneProfile.NEUTRAL
    
    # Verb energy level (0.0 = calm, 1.0 = intense)
    verb_energy: float = 0.5
    
    # Adjective usage (0.0 = none, 1.0 = liberal)
    adjective_level: float = 0.3
    
    # Sentence length preference
    prefer_short_sentences: bool = False
    
    # Include rhetorical questions
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
            instructions.append("Use analytical, strategic language. Focus on tactics and execution.")
        elif self.profile == ToneProfile.FAN:
            instructions.append("Use energetic, engaging language. Capture the excitement.")
        elif self.profile == ToneProfile.MINIMAL:
            instructions.append("Use brief, headline-style language. Be concise.")
        
        if self.prefer_short_sentences:
            instructions.append("Keep sentences short and punchy.")
        
        if not self.allow_questions:
            instructions.append("Do not use rhetorical questions.")
        
        return " ".join(instructions)


# =============================================================================
# TASK 6.1: CONSTRAINED LLM REWRITE (PER-MOMENT)
# =============================================================================


@dataclass
class MomentRewriteInput:
    """Input contract for per-moment LLM rewrite.
    
    STRICT: The LLM only sees this, nothing else.
    """
    
    moment_type: str  # "FLIP", "LEAD_BUILD", etc.
    quarter: str      # "Q2"
    time_range: str   # "7:32–4:10"
    
    # The deterministic template summary (ground truth)
    template_summary: str
    
    # Boxscore data (the only stats allowed)
    moment_boxscore: dict[str, Any]
    
    # Hard constraints
    constraints: dict[str, Any] = field(default_factory=lambda: {
        "no_new_stats": True,
        "no_reordering": True,
        "max_sentences": 3,
    })
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "moment_type": self.moment_type,
            "quarter": self.quarter,
            "time_range": self.time_range,
            "template_summary": self.template_summary,
            "moment_boxscore": self.moment_boxscore,
            "constraints": self.constraints,
        }


@dataclass
class MomentRewriteOutput:
    """Output contract for per-moment LLM rewrite."""
    
    rewritten_summary: str
    players_mentioned: list[str] = field(default_factory=list)
    confidence: float = 0.0
    
    # Validation results
    passed_validation: bool = True
    validation_errors: list[str] = field(default_factory=list)
    
    # Whether we fell back to template
    used_fallback: bool = False
    fallback_reason: str | None = None
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "rewritten_summary": self.rewritten_summary,
            "players_mentioned": self.players_mentioned,
            "confidence": self.confidence,
            "passed_validation": self.passed_validation,
            "validation_errors": self.validation_errors,
            "used_fallback": self.used_fallback,
            "fallback_reason": self.fallback_reason,
        }


def build_moment_rewrite_prompt(
    input_data: MomentRewriteInput,
    tone_config: ToneConfig,
) -> str:
    """Build the LLM prompt for moment rewriting.
    
    The prompt is carefully constrained to prevent the LLM from
    inventing facts or changing structure.
    """
    tone_instructions = tone_config.to_prompt_instructions()
    max_sentences = input_data.constraints.get("max_sentences", 3)
    
    # Extract allowed players from boxscore
    allowed_players = list(input_data.moment_boxscore.get("points_by_player", {}).keys())
    
    prompt = f"""Rewrite the following game moment summary to improve flow and readability.

ORIGINAL SUMMARY:
{input_data.template_summary}

MOMENT CONTEXT:
- Type: {input_data.moment_type}
- Quarter: {input_data.quarter}
- Time: {input_data.time_range}

ALLOWED PLAYERS: {', '.join(allowed_players) if allowed_players else 'No specific players'}

BOXSCORE DATA:
{_format_boxscore_for_prompt(input_data.moment_boxscore)}

STYLE INSTRUCTIONS:
{tone_instructions}

STRICT RULES (VIOLATIONS WILL BE REJECTED):
1. Keep ALL stats exactly as they appear in the original
2. Only mention players from the ALLOWED PLAYERS list
3. Maximum {max_sentences} sentences
4. Do not add new facts or statistics
5. Do not speculate about intent or strategy
6. Do not add drama not supported by the data
7. Do not change the meaning of the summary

Return ONLY the rewritten summary text, nothing else."""

    return prompt


def _format_boxscore_for_prompt(boxscore: dict[str, Any]) -> str:
    """Format boxscore data for inclusion in prompt."""
    lines = []
    
    if "points_by_player" in boxscore:
        lines.append("Points:")
        for player, pts in boxscore["points_by_player"].items():
            lines.append(f"  - {player}: {pts}")
    
    if "team_totals" in boxscore:
        tt = boxscore["team_totals"]
        lines.append(f"Team totals: Home {tt.get('home', 0)}, Away {tt.get('away', 0)}")
    
    if "key_plays" in boxscore:
        kp = boxscore["key_plays"]
        if kp.get("blocks"):
            for player, count in kp["blocks"].items():
                lines.append(f"  - {player}: {count} block(s)")
        if kp.get("steals"):
            for player, count in kp["steals"].items():
                lines.append(f"  - {player}: {count} steal(s)")
    
    return "\n".join(lines) if lines else "No detailed stats available"


# =============================================================================
# TASK 6.4: LLM SAFETY & REGRESSION GUARDS
# =============================================================================


@dataclass
class ValidationResult:
    """Result of LLM output validation."""
    
    passed: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    
    def add_error(self, error: str) -> None:
        self.errors.append(error)
        self.passed = False
    
    def add_warning(self, warning: str) -> None:
        self.warnings.append(warning)


def validate_stat_preservation(
    original: str,
    rewritten: str,
    boxscore: dict[str, Any],
) -> ValidationResult:
    """Verify that all stats in original are preserved in rewrite.
    
    Extracts numbers from both texts and ensures the rewrite
    contains all numbers from the original.
    """
    result = ValidationResult()
    
    # Extract all numbers from original
    original_numbers = set(re.findall(r'\b\d+\b', original))
    
    # Extract all numbers from rewrite
    rewrite_numbers = set(re.findall(r'\b\d+\b', rewritten))
    
    # Check for missing numbers (stats that disappeared)
    missing = original_numbers - rewrite_numbers
    if missing:
        result.add_error(f"Stats missing from rewrite: {missing}")
    
    # Check for new numbers (stats that were invented)
    # Allow some common numbers that might appear naturally
    common_numbers = {'1', '2', '3', '4'}
    new_numbers = rewrite_numbers - original_numbers - common_numbers
    
    # Cross-check against boxscore
    boxscore_numbers = _extract_boxscore_numbers(boxscore)
    truly_new = new_numbers - boxscore_numbers
    
    if truly_new:
        result.add_error(f"New stats invented by LLM: {truly_new}")
    
    return result


def _extract_boxscore_numbers(boxscore: dict[str, Any]) -> set[str]:
    """Extract all numbers from boxscore for validation."""
    numbers: set[str] = set()
    
    if "points_by_player" in boxscore:
        for pts in boxscore["points_by_player"].values():
            numbers.add(str(pts))
    
    if "team_totals" in boxscore:
        for val in boxscore["team_totals"].values():
            if isinstance(val, (int, float)):
                numbers.add(str(int(val)))
    
    if "key_plays" in boxscore:
        for play_type in boxscore["key_plays"].values():
            if isinstance(play_type, dict):
                for count in play_type.values():
                    numbers.add(str(count))
    
    return numbers


def validate_player_mentions(
    rewritten: str,
    boxscore: dict[str, Any],
) -> ValidationResult:
    """Verify that only players from boxscore are mentioned."""
    result = ValidationResult()
    
    # Get allowed players
    allowed_players = set()
    if "points_by_player" in boxscore:
        allowed_players.update(boxscore["points_by_player"].keys())
    if "key_plays" in boxscore:
        for play_type in boxscore["key_plays"].values():
            if isinstance(play_type, dict):
                allowed_players.update(play_type.keys())
    if "top_assists" in boxscore:
        for assist in boxscore["top_assists"]:
            if isinstance(assist, dict):
                allowed_players.add(assist.get("from", ""))
                allowed_players.add(assist.get("to", ""))
    
    # Remove empty strings
    allowed_players.discard("")
    
    if not allowed_players:
        # No players to validate against
        return result
    
    # Check for player name patterns in rewrite
    # This is a heuristic - look for capitalized multi-word names
    name_pattern = r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b'
    mentioned_names = set(re.findall(name_pattern, rewritten))
    
    # Check if any mentioned names are not in allowed list
    for name in mentioned_names:
        if name not in allowed_players:
            # Could be team name or other proper noun
            # Only flag if it looks like a player name
            if len(name.split()) >= 2:
                result.add_warning(f"Potentially unknown player: {name}")
    
    return result


def validate_sentence_count(
    rewritten: str,
    max_sentences: int,
) -> ValidationResult:
    """Verify sentence count is within limits."""
    result = ValidationResult()
    
    # Count sentences (simple heuristic)
    sentences = re.split(r'[.!?]+', rewritten)
    sentences = [s.strip() for s in sentences if s.strip()]
    
    if len(sentences) > max_sentences:
        result.add_error(
            f"Too many sentences: {len(sentences)} > {max_sentences}"
        )
    
    return result


def validate_length(
    rewritten: str,
    original: str,
    max_ratio: float = 1.5,
) -> ValidationResult:
    """Verify rewrite isn't excessively longer than original."""
    result = ValidationResult()
    
    if len(original) == 0:
        return result
    
    ratio = len(rewritten) / len(original)
    if ratio > max_ratio:
        result.add_error(
            f"Rewrite too long: {ratio:.1f}x original (max {max_ratio}x)"
        )
    
    return result


def validate_llm_output(
    input_data: MomentRewriteInput,
    output: MomentRewriteOutput,
    confidence_threshold: float = 0.6,
) -> ValidationResult:
    """Run all validation checks on LLM output."""
    result = ValidationResult()
    
    # Check confidence
    if output.confidence < confidence_threshold:
        result.add_error(f"Low confidence: {output.confidence:.2f} < {confidence_threshold}")
    
    # Check stat preservation
    stat_result = validate_stat_preservation(
        input_data.template_summary,
        output.rewritten_summary,
        input_data.moment_boxscore,
    )
    result.errors.extend(stat_result.errors)
    result.warnings.extend(stat_result.warnings)
    if not stat_result.passed:
        result.passed = False
    
    # Check player mentions
    player_result = validate_player_mentions(
        output.rewritten_summary,
        input_data.moment_boxscore,
    )
    result.errors.extend(player_result.errors)
    result.warnings.extend(player_result.warnings)
    if not player_result.passed:
        result.passed = False
    
    # Check sentence count
    max_sentences = input_data.constraints.get("max_sentences", 3)
    sentence_result = validate_sentence_count(output.rewritten_summary, max_sentences)
    result.errors.extend(sentence_result.errors)
    if not sentence_result.passed:
        result.passed = False
    
    # Check length
    length_result = validate_length(output.rewritten_summary, input_data.template_summary)
    result.errors.extend(length_result.errors)
    if not length_result.passed:
        result.passed = False
    
    return result


# =============================================================================
# TASK 6.1 CONTINUED: REWRITE EXECUTION WITH FALLBACK
# =============================================================================


# Type alias for LLM call function
LLMCallFn = Callable[[str], tuple[str, float]]


def rewrite_moment_with_llm(
    moment: "Moment",
    llm_call: LLMCallFn,
    tone_config: ToneConfig | None = None,
    confidence_threshold: float = 0.6,
) -> MomentRewriteOutput:
    """Rewrite a single moment's summary using LLM.
    
    Args:
        moment: The moment to rewrite
        llm_call: Function that takes prompt and returns (response, confidence)
        tone_config: Optional tone configuration
        confidence_threshold: Minimum confidence to accept rewrite
    
    Returns:
        MomentRewriteOutput with rewritten summary or fallback
    """
    if tone_config is None:
        tone_config = ToneConfig.from_profile(ToneProfile.NEUTRAL)
    
    # Get template summary from moment
    template_summary = ""
    if hasattr(moment, 'narrative_summary') and moment.narrative_summary:
        template_summary = moment.narrative_summary.text
    
    if not template_summary:
        return MomentRewriteOutput(
            rewritten_summary="",
            used_fallback=True,
            fallback_reason="No template summary available",
        )
    
    # Get boxscore from moment
    boxscore: dict[str, Any] = {}
    if hasattr(moment, 'moment_boxscore') and moment.moment_boxscore:
        boxscore = moment.moment_boxscore.to_dict()
    
    # Build input
    input_data = MomentRewriteInput(
        moment_type=moment.type.value if hasattr(moment.type, 'value') else str(moment.type),
        quarter=f"Q{_estimate_quarter(moment)}",
        time_range=moment.clock if hasattr(moment, 'clock') else "",
        template_summary=template_summary,
        moment_boxscore=boxscore,
    )
    
    # Build prompt
    prompt = build_moment_rewrite_prompt(input_data, tone_config)
    
    # Call LLM
    try:
        response, confidence = llm_call(prompt)
    except Exception as e:
        logger.warning(f"LLM call failed: {e}")
        return MomentRewriteOutput(
            rewritten_summary=template_summary,
            used_fallback=True,
            fallback_reason=f"LLM call failed: {str(e)}",
        )
    
    # Build output
    output = MomentRewriteOutput(
        rewritten_summary=response.strip(),
        confidence=confidence,
        players_mentioned=_extract_players_from_text(response, boxscore),
    )
    
    # Validate
    validation = validate_llm_output(input_data, output, confidence_threshold)
    output.passed_validation = validation.passed
    output.validation_errors = validation.errors
    
    # Fallback if validation failed
    if not validation.passed:
        logger.warning(
            f"LLM rewrite failed validation for {moment.id}: {validation.errors}"
        )
        output.rewritten_summary = template_summary
        output.used_fallback = True
        output.fallback_reason = f"Validation failed: {'; '.join(validation.errors)}"
    
    return output


def _estimate_quarter(moment: "Moment") -> int:
    """Estimate quarter from moment's play range."""
    # Rough heuristic: ~100 plays per quarter
    return min(4, max(1, (moment.start_play // 100) + 1))


def _extract_players_from_text(text: str, boxscore: dict[str, Any]) -> list[str]:
    """Extract player names mentioned in text that exist in boxscore."""
    allowed_players = set()
    if "points_by_player" in boxscore:
        allowed_players.update(boxscore["points_by_player"].keys())
    if "key_plays" in boxscore:
        for play_type in boxscore["key_plays"].values():
            if isinstance(play_type, dict):
                allowed_players.update(play_type.keys())
    
    mentioned = []
    for player in allowed_players:
        if player in text:
            mentioned.append(player)
    
    return mentioned


# =============================================================================
# TASK 6.2: FULL-GAME NARRATIVE STITCHING
# =============================================================================


@dataclass
class TransitionInput:
    """Input for narrative transition generation."""
    
    # Ordered moment summaries
    moment_summaries: list[str]
    
    # Act labels for each moment
    act_labels: list[str]  # "opening", "middle", "closing"
    
    # Game context (minimal)
    home_team: str = ""
    away_team: str = ""


@dataclass
class TransitionOutput:
    """Output from transition generation."""
    
    opening_sentence: str = ""
    act_transitions: dict[str, str] = field(default_factory=dict)  # "middle" -> sentence
    closing_sentence: str = ""
    
    # Validation
    passed_validation: bool = True
    used_fallback: bool = False
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "opening_sentence": self.opening_sentence,
            "act_transitions": self.act_transitions,
            "closing_sentence": self.closing_sentence,
            "passed_validation": self.passed_validation,
            "used_fallback": self.used_fallback,
        }


def build_transition_prompt(
    input_data: TransitionInput,
    tone_config: ToneConfig,
) -> str:
    """Build prompt for narrative transitions."""
    
    # Identify which acts are present
    acts = set(input_data.act_labels)
    
    prompt = f"""Generate brief narrative transitions for a basketball game recap.

GAME: {input_data.away_team} @ {input_data.home_team}

You will write:
1. ONE opening sentence (if the game has an opening act)
2. ONE transition sentence for act changes (opening→middle, middle→closing)
3. ONE closing sentence (if the game has a closing act)

ACTS IN THIS GAME: {', '.join(sorted(acts))}

STYLE: {tone_config.to_prompt_instructions()}

STRICT RULES:
1. NO new facts or statistics
2. NO player names
3. NO specific scores
4. Each sentence must be ≤ 20 words
5. Sentences should be general transitions, not summaries

Return in this exact format:
OPENING: [sentence or NONE]
MIDDLE_TRANSITION: [sentence or NONE]
CLOSING: [sentence or NONE]"""

    return prompt


def parse_transition_response(response: str) -> TransitionOutput:
    """Parse LLM response into TransitionOutput."""
    output = TransitionOutput()
    
    lines = response.strip().split('\n')
    for line in lines:
        line = line.strip()
        if line.startswith("OPENING:"):
            value = line[8:].strip()
            if value.upper() != "NONE":
                output.opening_sentence = value
        elif line.startswith("MIDDLE_TRANSITION:"):
            value = line[18:].strip()
            if value.upper() != "NONE":
                output.act_transitions["middle"] = value
        elif line.startswith("CLOSING:"):
            value = line[8:].strip()
            if value.upper() != "NONE":
                output.closing_sentence = value
    
    return output


def validate_transitions(output: TransitionOutput) -> ValidationResult:
    """Validate transition output."""
    result = ValidationResult()
    
    # Check for numbers (stats)
    all_text = " ".join([
        output.opening_sentence,
        *output.act_transitions.values(),
        output.closing_sentence,
    ])
    
    numbers = re.findall(r'\b\d+\b', all_text)
    if numbers:
        result.add_error(f"Transitions contain stats: {numbers}")
    
    # Check sentence lengths
    for sentence in [output.opening_sentence, output.closing_sentence]:
        if sentence and len(sentence.split()) > 25:
            result.add_error(f"Transition too long: {len(sentence.split())} words")
    
    return result


def generate_transitions(
    moments: Sequence["Moment"],
    llm_call: LLMCallFn,
    home_team: str = "",
    away_team: str = "",
    tone_config: ToneConfig | None = None,
) -> TransitionOutput:
    """Generate narrative transitions for a full game.
    
    Args:
        moments: All moments in order
        llm_call: LLM call function
        home_team: Home team name
        away_team: Away team name
        tone_config: Tone configuration
    
    Returns:
        TransitionOutput with generated transitions
    """
    if tone_config is None:
        tone_config = ToneConfig.from_profile(ToneProfile.NEUTRAL)
    
    # Build summaries and act labels
    summaries = []
    act_labels = []
    
    for moment in moments:
        summary = ""
        if hasattr(moment, 'narrative_summary') and moment.narrative_summary:
            summary = moment.narrative_summary.text
        summaries.append(summary)
        
        # Determine act from play position
        act = "middle"
        if moment.start_play < 100:
            act = "opening"
        elif moment.start_play >= 350:
            act = "closing"
        act_labels.append(act)
    
    input_data = TransitionInput(
        moment_summaries=summaries,
        act_labels=act_labels,
        home_team=home_team,
        away_team=away_team,
    )
    
    prompt = build_transition_prompt(input_data, tone_config)
    
    try:
        response, _ = llm_call(prompt)
        output = parse_transition_response(response)
    except Exception as e:
        logger.warning(f"Transition generation failed: {e}")
        return TransitionOutput(used_fallback=True)
    
    # Validate
    validation = validate_transitions(output)
    output.passed_validation = validation.passed
    
    if not validation.passed:
        logger.warning(f"Transition validation failed: {validation.errors}")
        return TransitionOutput(used_fallback=True)
    
    return output


# =============================================================================
# COMBINED AUGMENTATION FLOW
# =============================================================================


@dataclass
class AugmentationResult:
    """Result of full LLM augmentation."""
    
    # Rewritten moments
    moment_rewrites: dict[str, MomentRewriteOutput] = field(default_factory=dict)
    
    # Transitions
    transitions: TransitionOutput = field(default_factory=TransitionOutput)
    
    # Stats
    moments_rewritten: int = 0
    moments_fallback: int = 0
    
    # Feature flags used
    flags_used: LLMFeatureFlags = field(default_factory=LLMFeatureFlags)
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "moment_rewrites": {
                k: v.to_dict() for k, v in self.moment_rewrites.items()
            },
            "transitions": self.transitions.to_dict(),
            "moments_rewritten": self.moments_rewritten,
            "moments_fallback": self.moments_fallback,
        }


def augment_game_narrative(
    moments: Sequence["Moment"],
    llm_call: LLMCallFn | None,
    home_team: str = "",
    away_team: str = "",
    flags: LLMFeatureFlags | None = None,
    tone: ToneProfile = ToneProfile.NEUTRAL,
    game_id: str = "",
    league: str = "",
) -> AugmentationResult:
    """Apply LLM augmentation to a full game.
    
    This is the main entry point for Phase 6 augmentation.
    
    Args:
        moments: All moments for the game
        llm_call: Function to call LLM (None = no LLM)
        home_team: Home team name
        away_team: Away team name
        flags: Feature flags
        tone: Tone profile to use
        game_id: Game identifier for overrides
        league: League code for overrides
    
    Returns:
        AugmentationResult with all rewrites and transitions
    """
    result = AugmentationResult()
    
    # Get effective flags
    if flags is None:
        flags = LLMFeatureFlags.all_disabled()
    
    effective_flags = flags.for_game(game_id, league)
    result.flags_used = effective_flags
    
    # If no LLM or all disabled, return empty result
    if llm_call is None:
        logger.info("LLM augmentation skipped: no LLM provided")
        return result
    
    if not any([
        effective_flags.enable_moment_rewrite,
        effective_flags.enable_transitions,
    ]):
        logger.info("LLM augmentation skipped: all features disabled")
        return result
    
    # Get tone config
    tone_config = ToneConfig.from_profile(tone)
    if not effective_flags.enable_tone_profiles:
        tone_config = ToneConfig.from_profile(ToneProfile.NEUTRAL)
    
    # Rewrite moments
    if effective_flags.enable_moment_rewrite:
        for moment in moments:
            rewrite = rewrite_moment_with_llm(
                moment, llm_call, tone_config
            )
            result.moment_rewrites[moment.id] = rewrite
            
            if rewrite.used_fallback:
                result.moments_fallback += 1
            else:
                result.moments_rewritten += 1
    
    # Generate transitions
    if effective_flags.enable_transitions:
        result.transitions = generate_transitions(
            moments, llm_call, home_team, away_team, tone_config
        )
    
    logger.info(
        "llm_augmentation_complete",
        extra={
            "moments_rewritten": result.moments_rewritten,
            "moments_fallback": result.moments_fallback,
            "transitions_generated": not result.transitions.used_fallback,
        }
    )
    
    return result


# =============================================================================
# CONVENIENCE: MOCK LLM FOR TESTING
# =============================================================================


def create_mock_llm(
    confidence: float = 0.8,
    should_fail: bool = False,
) -> LLMCallFn:
    """Create a mock LLM for testing.
    
    Args:
        confidence: Confidence to return
        should_fail: Whether to raise an exception
    
    Returns:
        LLM call function
    """
    def mock_llm(prompt: str) -> tuple[str, float]:
        if should_fail:
            raise RuntimeError("Mock LLM failure")
        
        # Extract the original summary from prompt and return slightly modified
        # This is a very simple mock that just adds a prefix
        lines = prompt.split('\n')
        for i, line in enumerate(lines):
            if line.startswith("ORIGINAL SUMMARY:"):
                if i + 1 < len(lines):
                    original = lines[i + 1].strip()
                    # Just return the original (safest mock behavior)
                    return original, confidence
        
        return "Mock rewrite.", confidence
    
    return mock_llm
