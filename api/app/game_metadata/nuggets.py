"""Generate short, template-driven explanation nuggets."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .models import GameContext


@dataclass(frozen=True)
class NuggetTemplate:
    text: str
    required_tags: frozenset[str]


DEFAULT_NUGGET = "High-stakes matchup with plenty on the line."


def _normalize_tags(tags: Iterable[str]) -> set[str]:
    return {
        tag.strip().lower().replace(" ", "_")
        for tag in tags
        if isinstance(tag, str) and tag.strip()
    }


def _context_tags(context: GameContext) -> set[str]:
    context_tags: set[str] = set()
    if context.rivalry:
        context_tags.add("rivalry")
    if context.playoff_implications:
        context_tags.add("playoff_implications")
    if context.national_broadcast:
        context_tags.add("national_broadcast")
    if context.has_big_name_players:
        context_tags.add("star_power")
    if context.coach_vs_former_team:
        context_tags.add("coach_revenge")
    if context.projected_spread is not None and abs(context.projected_spread) <= 4:
        context_tags.add("tight_spread")
    if context.projected_total is not None and context.projected_total >= 150:
        context_tags.add("high_total")
    return context_tags


TEMPLATES: tuple[NuggetTemplate, ...] = (
    NuggetTemplate(
        text="First place vs second place — conference lead on the line.",
        required_tags=frozenset({"conference_lead", "top_two_conference"}),
    ),
    NuggetTemplate(
        text="In-state rivalry and both teams fighting for seeding.",
        required_tags=frozenset({"in_state_rivalry", "seeding_battle"}),
    ),
    NuggetTemplate(
        text="Projected tournament preview between two top-rated teams.",
        required_tags=frozenset({"tournament_preview", "top_rated"}),
    ),
    NuggetTemplate(
        text="Rivalry matchup with postseason positioning at stake.",
        required_tags=frozenset({"rivalry", "playoff_implications"}),
    ),
    NuggetTemplate(
        text="Postseason positioning is on the line in this matchup.",
        required_tags=frozenset({"playoff_implications"}),
    ),
    NuggetTemplate(
        text="National spotlight with star power on both sides.",
        required_tags=frozenset({"national_broadcast", "star_power"}),
    ),
    NuggetTemplate(
        text="Oddsmakers see this one coming down to the final stretch.",
        required_tags=frozenset({"tight_spread"}),
    ),
    NuggetTemplate(
        text="Up-tempo matchup with points expected.",
        required_tags=frozenset({"high_total"}),
    ),
)


def generate_nugget(context: GameContext, tags: Iterable[str]) -> str:
    """Generate a short, non-spoiler nugget from templates."""
    normalized_tags = _normalize_tags(tags)
    normalized_tags |= _context_tags(context)

    for template in TEMPLATES:
        if template.required_tags.issubset(normalized_tags):
            return template.text

    return DEFAULT_NUGGET
