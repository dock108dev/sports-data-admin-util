"""NHL Hockey Reference parsing helpers."""

from __future__ import annotations

import re
from typing import Iterable

from bs4 import BeautifulSoup

from ..models import NormalizedPlay, TeamIdentity
from ..normalization import normalize_team_name
from ..utils.parsing import parse_int


SCORE_PATTERN_TYPE = re.Pattern[str]


def parse_scorebox_abbreviations(soup: BeautifulSoup, league_code: str) -> tuple[str | None, str | None]:
    """Extract away/home abbreviations from the scorebox."""
    scorebox = soup.find("div", class_="scorebox")
    if not scorebox:
        return None, None

    team_divs = scorebox.find_all("div", recursive=False)
    if len(team_divs) < 2:
        return None, None

    def parse_abbr(div: BeautifulSoup) -> str | None:
        team_link = div.find("a", itemprop="name")
        if not team_link:
            strong = div.find("strong")
            team_link = strong.find("a") if strong else None
        if not team_link:
            return None
        team_name = team_link.text.strip()
        _, abbr = normalize_team_name(league_code, team_name)
        return abbr

    away_abbr = parse_abbr(team_divs[0])
    home_abbr = parse_abbr(team_divs[1])
    return away_abbr, home_abbr


def parse_scorebox_team(div: BeautifulSoup, league_code: str) -> tuple[TeamIdentity, int] | None:
    """Parse a team block inside the scorebox."""
    team_link = div.find("a", itemprop="name")
    if not team_link:
        strong = div.find("strong")
        team_link = strong.find("a") if strong else None
    if not team_link:
        return None

    team_name = team_link.text.strip()
    canonical_name, abbreviation = normalize_team_name(league_code, team_name)

    score_div = div.find("div", class_="score")
    if not score_div:
        return None

    try:
        score = int(score_div.text.strip())
    except ValueError:
        return None

    identity = TeamIdentity(
        league_code=league_code,
        name=canonical_name,
        short_name=canonical_name,
        abbreviation=abbreviation,
        external_ref=abbreviation.upper(),
    )
    return identity, score


def parse_pbp_period_marker(row: BeautifulSoup, ot_pattern: re.Pattern[str]) -> tuple[int | None, bool]:
    """Parse PBP header rows into a normalized period number."""
    row_id = (row.get("id") or "").strip().lower()
    header_text = row.get_text(" ", strip=True).lower()
    marker = " ".join(value for value in (row_id, header_text) if value)
    if not marker:
        return None, False

    if "1st period" in marker or "first period" in marker or row_id in {"p1", "1st", "first"}:
        return 1, False
    if "2nd period" in marker or "second period" in marker or row_id in {"p2", "2nd", "second"}:
        return 2, False
    if "3rd period" in marker or "third period" in marker or row_id in {"p3", "3rd", "third"}:
        return 3, False

    if "shootout" in marker or row_id in {"so", "shootout"}:
        return None, True

    if "ot" in marker or "overtime" in marker:
        match = ot_pattern.search(marker)
        if match:
            for group in match.groups():
                if group:
                    ot_number = parse_int(group)
                    if ot_number:
                        return 3 + ot_number, False
        return 4, False

    return None, False


def normalize_pbp_team_abbr(
    team_text: str | None,
    league_code: str,
    away_abbr: str | None,
    home_abbr: str | None,
) -> str | None:
    """Normalize PBP team abbreviations."""
    if not team_text:
        return None
    candidate = team_text.strip()
    if not candidate:
        return None
    if away_abbr and candidate.upper() == away_abbr.upper():
        return away_abbr
    if home_abbr and candidate.upper() == home_abbr.upper():
        return home_abbr
    _, abbr = normalize_team_name(league_code, candidate)
    return abbr


def extract_score(score_text: str | None, score_pattern: SCORE_PATTERN_TYPE) -> tuple[int | None, int | None]:
    """Extract away/home score values from a string."""
    if not score_text:
        return None, None
    match = score_pattern.match(score_text.strip())
    if not match:
        return None, None
    away_score = parse_int(match.group(1))
    home_score = parse_int(match.group(2))
    return away_score, home_score


def parse_pbp_row(
    row: BeautifulSoup,
    *,
    period: int,
    away_abbr: str | None,
    home_abbr: str | None,
    play_index: int,
    league_code: str,
    score_pattern: SCORE_PATTERN_TYPE,
) -> NormalizedPlay | None:
    """Parse a single NHL play-by-play row."""
    cells = row.find_all("td")
    if not cells:
        return None

    game_clock = cells[0].text.strip() or None

    if len(cells) == 2:
        description = cells[1].text.strip()
        return NormalizedPlay(
            play_index=play_index,
            quarter=period,
            game_clock=game_clock,
            play_type=None,
            team_abbreviation=None,
            player_id=None,
            player_name=None,
            description=description,
            home_score=None,
            away_score=None,
            raw_data={"full_description": description},
        )

    data_stats = {
        (cell.get("data-stat") or "").strip(): cell.text.strip()
        for cell in cells
        if cell.get("data-stat")
    }
    cell_texts = [cell.text.strip() for cell in cells]

    event_text = (
        data_stats.get("event")
        or data_stats.get("event_type")
        or data_stats.get("event_type_id")
        or (cell_texts[1] if len(cell_texts) > 1 else "")
    )
    team_text = (
        data_stats.get("team")
        or data_stats.get("team_id")
        or data_stats.get("team_abbr")
        or (cell_texts[2] if len(cell_texts) > 2 else "")
    )
    description_text = (
        data_stats.get("description")
        or data_stats.get("detail")
        or data_stats.get("details")
        or (cell_texts[3] if len(cell_texts) > 3 else "")
    )

    score_text = data_stats.get("score")
    if not score_text:
        for value in cell_texts[1:]:
            if score_pattern.match(value):
                score_text = value
                break

    away_score, home_score = extract_score(score_text, score_pattern)
    team_abbr = normalize_pbp_team_abbr(team_text, league_code, away_abbr, home_abbr)

    description = description_text or None
    play_type = event_text or None

    return NormalizedPlay(
        play_index=play_index,
        quarter=period,
        game_clock=game_clock,
        play_type=play_type,
        team_abbreviation=team_abbr,
        player_id=None,
        player_name=None,
        description=description,
        home_score=home_score,
        away_score=away_score,
        raw_data={
            "event": event_text,
            "team": team_text,
            "description": description_text,
            "score": score_text,
            "cells": cell_texts,
            "data_stats": data_stats,
        },
    )
