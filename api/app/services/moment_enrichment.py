"""Phase 4: Player & Box Score Integration

This module makes moments about players and teams, not abstract state changes.

TASK 4.1: Per-Moment Stat Aggregation ("Boxscore-Lite")
- Points by player
- Key plays (blocks, steals, turnovers)
- Top assist connections
- Team totals

TASK 4.2: Deterministic Narrative Summaries
- Templated summaries without AI
- Sentence 1: What changed (structural)
- Sentence 2: Who drove it (player-centric)
- Sentence 3: Context (optional)

This module uses only PBP data - no advanced analytics or ML.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Sequence, TYPE_CHECKING

if TYPE_CHECKING:
    from .moments import Moment

logger = logging.getLogger(__name__)


# =============================================================================
# TASK 4.1: PER-MOMENT STAT AGGREGATION
# =============================================================================


@dataclass
class AssistConnection:
    """An assist connection between two players."""
    
    from_player: str
    to_player: str
    count: int = 1
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "from": self.from_player,
            "to": self.to_player,
            "count": self.count,
        }


@dataclass
class KeyPlays:
    """Defensive and impact plays within a moment."""
    
    blocks: dict[str, int] = field(default_factory=dict)  # player -> count
    steals: dict[str, int] = field(default_factory=dict)
    turnovers_forced: dict[str, int] = field(default_factory=dict)  # player who forced
    turnovers_committed: dict[str, int] = field(default_factory=dict)  # player who committed
    
    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        if self.blocks:
            result["blocks"] = self.blocks
        if self.steals:
            result["steals"] = self.steals
        if self.turnovers_forced:
            result["turnovers_forced"] = self.turnovers_forced
        if self.turnovers_committed:
            result["turnovers_committed"] = self.turnovers_committed
        return result


@dataclass
class TeamTotals:
    """Team scoring totals for a moment."""
    
    home: int = 0
    away: int = 0
    
    @property
    def net(self) -> int:
        return self.home - self.away
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "home": self.home,
            "away": self.away,
            "net": self.net,
        }


@dataclass
class MomentBoxscore:
    """Aggregated stats for a single moment.
    
    This is the "boxscore-lite" that answers:
    - Who scored?
    - Who defended?
    - Which team won the span?
    """
    
    # Points by player
    points_by_player: dict[str, int] = field(default_factory=dict)
    
    # Key defensive/impact plays
    key_plays: KeyPlays = field(default_factory=KeyPlays)
    
    # Assist connections
    top_assists: list[AssistConnection] = field(default_factory=list)
    
    # Team totals
    team_totals: TeamTotals = field(default_factory=TeamTotals)
    
    # Metadata
    plays_analyzed: int = 0
    scoring_plays: int = 0
    
    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "team_totals": self.team_totals.to_dict(),
            "plays_analyzed": self.plays_analyzed,
            "scoring_plays": self.scoring_plays,
        }
        
        if self.points_by_player:
            result["points_by_player"] = self.points_by_player
        
        key_plays_dict = self.key_plays.to_dict()
        if key_plays_dict:
            result["key_plays"] = key_plays_dict
        
        if self.top_assists:
            result["top_assists"] = [a.to_dict() for a in self.top_assists]
        
        return result
    
    @property
    def top_scorer(self) -> tuple[str, int] | None:
        """Get the top scorer in this moment."""
        if not self.points_by_player:
            return None
        return max(self.points_by_player.items(), key=lambda x: x[1])
    
    @property
    def top_scorers(self) -> list[tuple[str, int]]:
        """Get top scorers sorted by points."""
        return sorted(
            self.points_by_player.items(),
            key=lambda x: x[1],
            reverse=True
        )


def aggregate_moment_boxscore(
    moment: "Moment",
    events: Sequence[dict[str, Any]],
) -> MomentBoxscore:
    """Aggregate stats from PBP events for a moment.
    
    Uses only data present in PBP events - no external lookups.
    
    Args:
        moment: The moment to aggregate stats for
        events: All timeline events
    
    Returns:
        MomentBoxscore with aggregated stats
    """
    boxscore = MomentBoxscore()
    
    # Get events within this moment's play range
    moment_events = [
        e for i, e in enumerate(events)
        if moment.start_play <= i <= moment.end_play
        and e.get("event_type") == "pbp"
    ]
    
    boxscore.plays_analyzed = len(moment_events)
    
    # Track assist connections
    assist_counts: dict[tuple[str, str], int] = {}
    
    for event in moment_events:
        # Points by player
        points = event.get("points_scored", 0) or 0
        player = event.get("player_name") or event.get("scorer")
        team = event.get("scoring_team") or event.get("team")
        
        if points > 0 and player:
            boxscore.points_by_player[player] = (
                boxscore.points_by_player.get(player, 0) + points
            )
            boxscore.scoring_plays += 1
            
            # Track team totals
            if team == "home":
                boxscore.team_totals.home += points
            elif team == "away":
                boxscore.team_totals.away += points
        
        # Assist tracking
        assister = event.get("assist_player") or event.get("assister")
        if assister and player:
            key = (assister, player)
            assist_counts[key] = assist_counts.get(key, 0) + 1
        
        # Key plays - blocks
        event_type = (event.get("play_type") or event.get("event_type_detail") or "").lower()
        
        if "block" in event_type:
            blocker = event.get("player_name") or event.get("blocker")
            if blocker:
                boxscore.key_plays.blocks[blocker] = (
                    boxscore.key_plays.blocks.get(blocker, 0) + 1
                )
        
        # Key plays - steals
        if "steal" in event_type:
            stealer = event.get("player_name") or event.get("stealer")
            if stealer:
                boxscore.key_plays.steals[stealer] = (
                    boxscore.key_plays.steals.get(stealer, 0) + 1
                )
        
        # Key plays - turnovers
        if "turnover" in event_type:
            player_name = event.get("player_name")
            if player_name:
                boxscore.key_plays.turnovers_committed[player_name] = (
                    boxscore.key_plays.turnovers_committed.get(player_name, 0) + 1
                )
            
            # Track who forced it if available
            forcer = event.get("steal_player") or event.get("forcer")
            if forcer:
                boxscore.key_plays.turnovers_forced[forcer] = (
                    boxscore.key_plays.turnovers_forced.get(forcer, 0) + 1
                )
    
    # Convert assist counts to connections, sorted by count
    boxscore.top_assists = [
        AssistConnection(from_player=k[0], to_player=k[1], count=v)
        for k, v in sorted(assist_counts.items(), key=lambda x: x[1], reverse=True)
    ][:3]  # Top 3 connections
    
    return boxscore


# =============================================================================
# TASK 4.2: DETERMINISTIC NARRATIVE SUMMARIES
# =============================================================================


@dataclass
class NarrativeSummary:
    """Deterministic narrative summary for a moment."""
    
    # The full summary text
    text: str = ""
    
    # Individual sentences
    structural_sentence: str = ""  # What changed
    player_sentence: str = ""      # Who drove it
    context_sentence: str = ""     # When/where (optional)
    
    # Metadata for debugging
    template_id: str = ""
    players_referenced: list[str] = field(default_factory=list)
    stats_referenced: list[str] = field(default_factory=list)
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "sentences": {
                "structural": self.structural_sentence,
                "player": self.player_sentence,
                "context": self.context_sentence,
            },
            "template_id": self.template_id,
            "players_referenced": self.players_referenced,
            "stats_referenced": self.stats_referenced,
        }


# Template definitions for different moment types
STRUCTURAL_TEMPLATES = {
    "flip_home": "{home_team} took the lead with a {net_points}-point swing.",
    "flip_away": "{away_team} took the lead with a {net_points}-point swing.",
    "run_home": "{home_team} went on a {run_points}-{opp_points} run to {action}.",
    "run_away": "{away_team} went on a {run_points}-{opp_points} run to {action}.",
    "separation": "{leading_team} extended the lead to {margin} points.",
    "cut": "{trailing_team} cut the deficit to {margin} points.",
    "stable": "The teams traded scores with no major separation.",
    "tie": "The game returned to a tie at {score}.",
    "closing": "{leading_team} closed out the game with a decisive stretch.",
}

PLAYER_TEMPLATES = {
    "single_star": "{player1} led the way with {points1} points.",
    "duo": "{player1} and {player2} combined for {total_points} points.",
    "with_defense": "{player1} scored {points1} points while {defender} added {def_stat}.",
    "assist_driven": "{assister} set up {scorer} for {points} points.",
    "team_effort": "{team} scored {points} points in the stretch.",
    "defensive": "{defender} anchored the defense with {blocks} blocks.",
}

CONTEXT_TEMPLATES = {
    "early_game": "The surge came early in the {quarter}.",
    "mid_quarter": "The run occurred midway through the {quarter}.",
    "late_quarter": "The stretch came late in the {quarter}.",
    "halftime": "The run set the tone heading into halftime.",
    "closing": "The decisive stretch came in the final minutes.",
}


def _get_quarter_name(quarter: int) -> str:
    """Get readable quarter name."""
    if quarter <= 4:
        ordinals = {1: "first", 2: "second", 3: "third", 4: "fourth"}
        return f"{ordinals.get(quarter, str(quarter))} quarter"
    else:
        ot_num = quarter - 4
        if ot_num == 1:
            return "overtime"
        return f"overtime {ot_num}"


def _generate_structural_sentence(
    moment: "Moment",
    boxscore: MomentBoxscore,
    home_team: str = "Home",
    away_team: str = "Away",
) -> tuple[str, str]:
    """Generate Sentence 1: What changed structurally.
    
    Returns:
        Tuple of (sentence, template_id)
    """
    from .moments import MomentType
    
    net = boxscore.team_totals.net
    home_pts = boxscore.team_totals.home
    away_pts = boxscore.team_totals.away
    
    # Determine the narrative based on moment type
    if moment.type == MomentType.FLIP:
        if net > 0:
            template_id = "flip_home"
            sentence = STRUCTURAL_TEMPLATES[template_id].format(
                home_team=home_team,
                net_points=abs(net),
            )
        else:
            template_id = "flip_away"
            sentence = STRUCTURAL_TEMPLATES[template_id].format(
                away_team=away_team,
                net_points=abs(net),
            )
    
    elif moment.type == MomentType.TIE:
        template_id = "tie"
        # Get the tied score from score_after
        home_score = moment.score_after[0]
        sentence = STRUCTURAL_TEMPLATES[template_id].format(score=home_score)
    
    elif moment.type == MomentType.CLOSING_CONTROL:
        template_id = "closing"
        leading_team = home_team if net >= 0 else away_team
        sentence = STRUCTURAL_TEMPLATES[template_id].format(leading_team=leading_team)
    
    elif moment.type == MomentType.LEAD_BUILD:
        template_id = "separation"
        leading_team = home_team if net >= 0 else away_team
        margin = abs(moment.score_after[0] - moment.score_after[1])
        sentence = STRUCTURAL_TEMPLATES[template_id].format(
            leading_team=leading_team,
            margin=margin,
        )
    
    elif moment.type == MomentType.CUT:
        template_id = "cut"
        # Trailing team made the cut
        trailing_team = away_team if net > 0 else home_team
        margin = abs(moment.score_after[0] - moment.score_after[1])
        sentence = STRUCTURAL_TEMPLATES[template_id].format(
            trailing_team=trailing_team,
            margin=margin,
        )
    
    elif moment.type == MomentType.MOMENTUM_SHIFT:
        # Big run
        if net > 0:
            template_id = "run_home"
            action = "take control" if net > 8 else "pull ahead"
            sentence = STRUCTURAL_TEMPLATES[template_id].format(
                home_team=home_team,
                run_points=home_pts,
                opp_points=away_pts,
                action=action,
            )
        else:
            template_id = "run_away"
            action = "take control" if abs(net) > 8 else "pull ahead"
            sentence = STRUCTURAL_TEMPLATES[template_id].format(
                away_team=away_team,
                run_points=away_pts,
                opp_points=home_pts,
                action=action,
            )
    
    else:
        # NEUTRAL or default
        template_id = "stable"
        sentence = STRUCTURAL_TEMPLATES[template_id]
    
    return sentence, template_id


def _generate_player_sentence(
    moment: "Moment",
    boxscore: MomentBoxscore,
    home_team: str = "Home",
    away_team: str = "Away",
) -> tuple[str, str, list[str], list[str]]:
    """Generate Sentence 2: Who drove it.
    
    Returns:
        Tuple of (sentence, template_id, players_referenced, stats_referenced)
    """
    players_referenced: list[str] = []
    stats_referenced: list[str] = []
    
    top_scorers = boxscore.top_scorers
    
    # No scorers - fall back to team-centric
    if not top_scorers:
        # Use team totals
        if boxscore.team_totals.home > boxscore.team_totals.away:
            team = home_team
            points = boxscore.team_totals.home
        else:
            team = away_team
            points = boxscore.team_totals.away
        
        if points > 0:
            template_id = "team_effort"
            sentence = PLAYER_TEMPLATES[template_id].format(team=team, points=points)
            stats_referenced.append(f"team_points:{points}")
        else:
            return "", "none", [], []
        
        return sentence, template_id, players_referenced, stats_referenced
    
    # Check for defensive standouts
    blocks = boxscore.key_plays.blocks
    steals = boxscore.key_plays.steals
    
    top_blocker = max(blocks.items(), key=lambda x: x[1]) if blocks else None
    top_stealer = max(steals.items(), key=lambda x: x[1]) if steals else None
    
    # Single dominant scorer
    if len(top_scorers) == 1 or (len(top_scorers) > 1 and top_scorers[0][1] >= top_scorers[1][1] * 2):
        player1, points1 = top_scorers[0]
        players_referenced.append(player1)
        stats_referenced.append(f"points:{points1}")
        
        # Add defensive component if notable (blocks first, then steals)
        if top_blocker and top_blocker[1] >= 2:
            template_id = "with_defense"
            sentence = PLAYER_TEMPLATES[template_id].format(
                player1=player1,
                points1=points1,
                defender=top_blocker[0],
                def_stat=f"{top_blocker[1]} blocks",
            )
            players_referenced.append(top_blocker[0])
            stats_referenced.append(f"blocks:{top_blocker[1]}")
        elif top_stealer and top_stealer[1] >= 2:
            template_id = "with_defense"
            sentence = PLAYER_TEMPLATES[template_id].format(
                player1=player1,
                points1=points1,
                defender=top_stealer[0],
                def_stat=f"{top_stealer[1]} steals",
            )
            players_referenced.append(top_stealer[0])
            stats_referenced.append(f"steals:{top_stealer[1]}")
        else:
            template_id = "single_star"
            sentence = PLAYER_TEMPLATES[template_id].format(
                player1=player1,
                points1=points1,
            )
    
    # Two notable scorers
    elif len(top_scorers) >= 2:
        player1, points1 = top_scorers[0]
        player2, points2 = top_scorers[1]
        total = points1 + points2
        
        template_id = "duo"
        sentence = PLAYER_TEMPLATES[template_id].format(
            player1=player1,
            player2=player2,
            total_points=total,
        )
        players_referenced.extend([player1, player2])
        stats_referenced.extend([f"points:{points1}", f"points:{points2}"])
    
    else:
        return "", "none", [], []
    
    return sentence, template_id, players_referenced, stats_referenced


def _generate_context_sentence(
    moment: "Moment",
    events: Sequence[dict[str, Any]],
) -> tuple[str, str]:
    """Generate Sentence 3: Context (optional).
    
    Returns:
        Tuple of (sentence, template_id)
    """
    # Get quarter from moment's start event
    quarter = 1
    game_clock = ""
    
    if 0 <= moment.start_play < len(events):
        event = events[moment.start_play]
        quarter = event.get("quarter", 1) or 1
        game_clock = event.get("game_clock", "") or ""
    
    quarter_name = _get_quarter_name(quarter)
    
    # Parse game clock to determine timing
    minutes = 12  # Default
    if game_clock and ":" in game_clock:
        try:
            minutes = int(game_clock.split(":")[0])
        except ValueError:
            pass
    
    # Determine template based on timing
    from .moments import MomentType
    
    if moment.type == MomentType.CLOSING_CONTROL:
        template_id = "closing"
        sentence = CONTEXT_TEMPLATES[template_id]
    elif quarter == 2 and minutes <= 2:
        template_id = "halftime"
        sentence = CONTEXT_TEMPLATES[template_id]
    elif minutes >= 9:
        template_id = "early_game"
        sentence = CONTEXT_TEMPLATES[template_id].format(quarter=quarter_name)
    elif minutes <= 3:
        template_id = "late_quarter"
        sentence = CONTEXT_TEMPLATES[template_id].format(quarter=quarter_name)
    else:
        template_id = "mid_quarter"
        sentence = CONTEXT_TEMPLATES[template_id].format(quarter=quarter_name)
    
    return sentence, template_id


def generate_narrative_summary(
    moment: "Moment",
    boxscore: MomentBoxscore,
    events: Sequence[dict[str, Any]],
    home_team: str = "Home",
    away_team: str = "Away",
    include_context: bool = True,
) -> NarrativeSummary:
    """Generate a deterministic narrative summary for a moment.
    
    This creates a 2-3 sentence summary using only the moment's boxscore
    data - no AI involvement.
    
    Args:
        moment: The moment to summarize
        boxscore: Aggregated stats for the moment
        events: Timeline events
        home_team: Home team name
        away_team: Away team name
        include_context: Whether to include context sentence
    
    Returns:
        NarrativeSummary with text and metadata
    """
    summary = NarrativeSummary()
    
    # Sentence 1: Structural change
    structural, struct_template = _generate_structural_sentence(
        moment, boxscore, home_team, away_team
    )
    summary.structural_sentence = structural
    
    # Sentence 2: Player-centric
    player, player_template, players, stats = _generate_player_sentence(
        moment, boxscore, home_team, away_team
    )
    summary.player_sentence = player
    summary.players_referenced = players
    summary.stats_referenced = stats
    
    # Sentence 3: Context (optional)
    if include_context and moment.play_count >= 5:
        context, context_template = _generate_context_sentence(moment, events)
        summary.context_sentence = context
    
    # Combine into full text
    sentences = [s for s in [structural, player, summary.context_sentence] if s]
    summary.text = " ".join(sentences)
    
    # Template ID combines all used templates
    summary.template_id = f"{struct_template}|{player_template}"
    
    return summary


# =============================================================================
# ENRICHMENT APPLICATION
# =============================================================================


@dataclass
class EnrichmentResult:
    """Result of Phase 4 enrichment."""
    
    moments: list["Moment"] = field(default_factory=list)
    
    # Stats
    moments_enriched: int = 0
    players_identified: int = 0
    total_scoring_plays: int = 0
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "moments_enriched": self.moments_enriched,
            "players_identified": self.players_identified,
            "total_scoring_plays": self.total_scoring_plays,
        }


def enrich_moments_with_boxscore(
    moments: list["Moment"],
    events: Sequence[dict[str, Any]],
    home_team: str = "Home",
    away_team: str = "Away",
) -> EnrichmentResult:
    """Enrich all moments with boxscore and narrative summaries.
    
    Args:
        moments: Moments to enrich
        events: Timeline events
        home_team: Home team name
        away_team: Away team name
    
    Returns:
        EnrichmentResult with enriched moments
    """
    result = EnrichmentResult()
    all_players: set[str] = set()
    
    for moment in moments:
        # Aggregate boxscore
        boxscore = aggregate_moment_boxscore(moment, events)
        moment.moment_boxscore = boxscore
        
        # Generate narrative summary
        narrative = generate_narrative_summary(
            moment, boxscore, events, home_team, away_team
        )
        moment.narrative_summary = narrative
        
        # Update stats
        result.moments_enriched += 1
        result.total_scoring_plays += boxscore.scoring_plays
        all_players.update(boxscore.points_by_player.keys())
        all_players.update(boxscore.key_plays.blocks.keys())
        all_players.update(boxscore.key_plays.steals.keys())
    
    result.players_identified = len(all_players)
    result.moments = moments
    
    logger.info(
        "moments_enriched",
        extra={
            "moments_enriched": result.moments_enriched,
            "players_identified": result.players_identified,
            "total_scoring_plays": result.total_scoring_plays,
        }
    )
    
    return result
