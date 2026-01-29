"""Tests for scrapers/nhl_sportsref_helpers.py module."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from bs4 import BeautifulSoup

# Ensure the scraper package is importable
REPO_ROOT = Path(__file__).resolve().parents[2]
SCRAPER_ROOT = REPO_ROOT / "scraper"
if str(SCRAPER_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRAPER_ROOT))

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://user:pass@localhost:5432/test_db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("ENVIRONMENT", "development")


from sports_scraper.scrapers.nhl_sportsref_helpers import (
    parse_scorebox_abbreviations,
    parse_scorebox_team,
    parse_pbp_period_marker,
    normalize_pbp_team_abbr,
    extract_score,
    parse_pbp_row,
)


class TestParseScoreboxAbbreviations:
    """Tests for parse_scorebox_abbreviations function."""

    def test_returns_none_tuple_when_no_scorebox(self):
        """Returns (None, None) when scorebox not found."""
        soup = BeautifulSoup("<html></html>", "lxml")
        away, home = parse_scorebox_abbreviations(soup, "NHL")
        assert away is None
        assert home is None

    def test_returns_none_tuple_when_fewer_than_two_divs(self):
        """Returns (None, None) when fewer than 2 team divs."""
        html = '<div class="scorebox"><div>One Team</div></div>'
        soup = BeautifulSoup(html, "lxml")
        away, home = parse_scorebox_abbreviations(soup, "NHL")
        assert away is None
        assert home is None

    def test_parses_team_links_with_itemprop(self):
        """Parses team links with itemprop="name"."""
        html = '''
        <div class="scorebox">
            <div><a itemprop="name" href="/teams/BOS/">Boston Bruins</a></div>
            <div><a itemprop="name" href="/teams/TBL/">Tampa Bay Lightning</a></div>
        </div>
        '''
        soup = BeautifulSoup(html, "lxml")
        away, home = parse_scorebox_abbreviations(soup, "NHL")
        assert away is not None
        assert home is not None

    def test_parses_team_links_in_strong_tags(self):
        """Parses team links nested in strong tags."""
        html = '''
        <div class="scorebox">
            <div><strong><a href="/teams/BOS/">Boston Bruins</a></strong></div>
            <div><strong><a href="/teams/TBL/">Tampa Bay Lightning</a></strong></div>
        </div>
        '''
        soup = BeautifulSoup(html, "lxml")
        away, home = parse_scorebox_abbreviations(soup, "NHL")
        assert away is not None
        assert home is not None


class TestParseScoreboxTeam:
    """Tests for parse_scorebox_team function."""

    def test_returns_none_when_no_team_link(self):
        """Returns None when no team link found."""
        html = '<div>No team link</div>'
        soup = BeautifulSoup(html, "lxml")
        div = soup.find("div")
        result = parse_scorebox_team(div, "NHL")
        assert result is None

    def test_returns_none_when_no_score_div(self):
        """Returns None when no score div found."""
        html = '<div><a itemprop="name">Boston Bruins</a></div>'
        soup = BeautifulSoup(html, "lxml")
        div = soup.find("div")
        result = parse_scorebox_team(div, "NHL")
        assert result is None

    def test_returns_none_for_invalid_score(self):
        """Returns None for non-numeric score."""
        html = '''
        <div>
            <a itemprop="name">Boston Bruins</a>
            <div class="score">N/A</div>
        </div>
        '''
        soup = BeautifulSoup(html, "lxml")
        div = soup.find("div")
        result = parse_scorebox_team(div, "NHL")
        assert result is None

    def test_parses_team_and_score(self):
        """Parses team identity and score."""
        html = '''
        <div>
            <a itemprop="name">Boston Bruins</a>
            <div class="score">4</div>
        </div>
        '''
        soup = BeautifulSoup(html, "lxml")
        div = soup.find("div")
        result = parse_scorebox_team(div, "NHL")
        assert result is not None
        identity, score = result
        assert score == 4
        assert identity.league_code == "NHL"


class TestParsePbpPeriodMarker:
    """Tests for parse_pbp_period_marker function."""

    def test_returns_1_for_first_period(self):
        """Returns 1 for 1st period marker."""
        OT_PATTERN = re.compile(r"(?:ot|overtime)\s*(\d+)|(\d+)\s*(?:ot|overtime)")
        html = '<tr id="p1">1st Period</tr>'
        soup = BeautifulSoup(html, "lxml")
        row = soup.find("tr")
        period, is_shootout = parse_pbp_period_marker(row, OT_PATTERN)
        assert period == 1
        assert is_shootout is False

    def test_returns_2_for_second_period(self):
        """Returns 2 for 2nd period marker."""
        OT_PATTERN = re.compile(r"(?:ot|overtime)\s*(\d+)|(\d+)\s*(?:ot|overtime)")
        html = '<tr id="p2">2nd Period</tr>'
        soup = BeautifulSoup(html, "lxml")
        row = soup.find("tr")
        period, is_shootout = parse_pbp_period_marker(row, OT_PATTERN)
        assert period == 2
        assert is_shootout is False

    def test_returns_3_for_third_period(self):
        """Returns 3 for 3rd period marker."""
        OT_PATTERN = re.compile(r"(?:ot|overtime)\s*(\d+)|(\d+)\s*(?:ot|overtime)")
        html = '<tr id="p3">3rd Period</tr>'
        soup = BeautifulSoup(html, "lxml")
        row = soup.find("tr")
        period, is_shootout = parse_pbp_period_marker(row, OT_PATTERN)
        assert period == 3
        assert is_shootout is False

    def test_returns_4_for_overtime(self):
        """Returns 4 for overtime marker."""
        OT_PATTERN = re.compile(r"(?:ot|overtime)\s*(\d+)|(\d+)\s*(?:ot|overtime)")
        html = '<tr>Overtime</tr>'
        soup = BeautifulSoup(html, "lxml")
        row = soup.find("tr")
        period, is_shootout = parse_pbp_period_marker(row, OT_PATTERN)
        assert period == 4
        assert is_shootout is False

    def test_returns_5_for_double_overtime(self):
        """Returns 5 for 2nd overtime."""
        OT_PATTERN = re.compile(r"(?:ot|overtime)\s*(\d+)|(\d+)\s*(?:ot|overtime)")
        html = '<tr>Overtime 2</tr>'
        soup = BeautifulSoup(html, "lxml")
        row = soup.find("tr")
        period, is_shootout = parse_pbp_period_marker(row, OT_PATTERN)
        assert period == 5
        assert is_shootout is False

    def test_returns_shootout_flag(self):
        """Returns True for shootout marker."""
        OT_PATTERN = re.compile(r"(?:ot|overtime)\s*(\d+)|(\d+)\s*(?:ot|overtime)")
        html = '<tr id="so">Shootout</tr>'
        soup = BeautifulSoup(html, "lxml")
        row = soup.find("tr")
        period, is_shootout = parse_pbp_period_marker(row, OT_PATTERN)
        assert is_shootout is True

    def test_returns_none_for_empty_row(self):
        """Returns None for row with no period marker."""
        OT_PATTERN = re.compile(r"(?:ot|overtime)\s*(\d+)|(\d+)\s*(?:ot|overtime)")
        html = '<tr></tr>'
        soup = BeautifulSoup(html, "lxml")
        row = soup.find("tr")
        period, is_shootout = parse_pbp_period_marker(row, OT_PATTERN)
        assert period is None
        assert is_shootout is False


class TestNormalizePbpTeamAbbr:
    """Tests for normalize_pbp_team_abbr function."""

    def test_returns_none_for_empty_text(self):
        """Returns None for empty text."""
        result = normalize_pbp_team_abbr("", "NHL", "BOS", "TBL")
        assert result is None

    def test_returns_none_for_none_text(self):
        """Returns None for None text."""
        result = normalize_pbp_team_abbr(None, "NHL", "BOS", "TBL")
        assert result is None

    def test_matches_away_team(self):
        """Matches away team abbreviation."""
        result = normalize_pbp_team_abbr("BOS", "NHL", "BOS", "TBL")
        assert result == "BOS"

    def test_matches_home_team(self):
        """Matches home team abbreviation."""
        result = normalize_pbp_team_abbr("TBL", "NHL", "BOS", "TBL")
        assert result == "TBL"

    def test_case_insensitive_match(self):
        """Matches case-insensitively."""
        result = normalize_pbp_team_abbr("bos", "NHL", "BOS", "TBL")
        assert result == "BOS"

    def test_normalizes_unknown_team(self):
        """Normalizes unknown team name."""
        result = normalize_pbp_team_abbr("Boston Bruins", "NHL", "BOS", "TBL")
        assert result is not None


class TestExtractScore:
    """Tests for extract_score function."""

    def test_returns_none_tuple_for_empty_string(self):
        """Returns (None, None) for empty string."""
        SCORE_PATTERN = re.compile(r"^(\d+)\s*-\s*(\d+)$")
        away, home = extract_score("", SCORE_PATTERN)
        assert away is None
        assert home is None

    def test_returns_none_tuple_for_none(self):
        """Returns (None, None) for None."""
        SCORE_PATTERN = re.compile(r"^(\d+)\s*-\s*(\d+)$")
        away, home = extract_score(None, SCORE_PATTERN)
        assert away is None
        assert home is None

    def test_extracts_score_from_valid_format(self):
        """Extracts scores from 'away-home' format."""
        SCORE_PATTERN = re.compile(r"^(\d+)\s*-\s*(\d+)$")
        away, home = extract_score("3-2", SCORE_PATTERN)
        assert away == 3
        assert home == 2

    def test_extracts_score_with_spaces(self):
        """Extracts scores with spaces around dash."""
        SCORE_PATTERN = re.compile(r"^(\d+)\s*-\s*(\d+)$")
        away, home = extract_score("3 - 2", SCORE_PATTERN)
        assert away == 3
        assert home == 2

    def test_returns_none_for_invalid_format(self):
        """Returns (None, None) for invalid format."""
        SCORE_PATTERN = re.compile(r"^(\d+)\s*-\s*(\d+)$")
        away, home = extract_score("invalid", SCORE_PATTERN)
        assert away is None
        assert home is None


class TestParsePbpRow:
    """Tests for parse_pbp_row function."""

    def test_returns_none_for_empty_row(self):
        """Returns None for row with no cells."""
        SCORE_PATTERN = re.compile(r"^(\d+)\s*-\s*(\d+)$")
        html = '<tr></tr>'
        soup = BeautifulSoup(html, "lxml")
        row = soup.find("tr")
        result = parse_pbp_row(
            row, period=1, away_abbr="BOS", home_abbr="TBL",
            play_index=0, league_code="NHL", score_pattern=SCORE_PATTERN
        )
        assert result is None

    def test_parses_colspan_row(self):
        """Parses colspan row (neutral play)."""
        SCORE_PATTERN = re.compile(r"^(\d+)\s*-\s*(\d+)$")
        html = '<tr><td>0:00</td><td colspan="5">Period Start</td></tr>'
        soup = BeautifulSoup(html, "lxml")
        row = soup.find("tr")
        result = parse_pbp_row(
            row, period=1, away_abbr="BOS", home_abbr="TBL",
            play_index=0, league_code="NHL", score_pattern=SCORE_PATTERN
        )
        assert result is not None
        assert result.quarter == 1
        assert "Period Start" in result.description

    def test_parses_standard_row_with_data_stats(self):
        """Parses standard row with data-stat attributes."""
        SCORE_PATTERN = re.compile(r"^(\d+)\s*-\s*(\d+)$")
        html = '''
        <tr>
            <td>15:00</td>
            <td data-stat="event">Goal</td>
            <td data-stat="team">BOS</td>
            <td data-stat="description">David Pastrnak scores</td>
            <td data-stat="score">1-0</td>
        </tr>
        '''
        soup = BeautifulSoup(html, "lxml")
        row = soup.find("tr")
        result = parse_pbp_row(
            row, period=1, away_abbr="BOS", home_abbr="TBL",
            play_index=1, league_code="NHL", score_pattern=SCORE_PATTERN
        )
        assert result is not None
        assert result.game_clock == "15:00"
        assert result.play_type == "Goal"
        assert result.team_abbreviation == "BOS"

    def test_extracts_score_from_row(self):
        """Extracts score from row."""
        SCORE_PATTERN = re.compile(r"^(\d+)\s*-\s*(\d+)$")
        html = '''
        <tr>
            <td>15:00</td>
            <td data-stat="event">Goal</td>
            <td data-stat="team">BOS</td>
            <td data-stat="description">Goal scored</td>
            <td data-stat="score">2-1</td>
        </tr>
        '''
        soup = BeautifulSoup(html, "lxml")
        row = soup.find("tr")
        result = parse_pbp_row(
            row, period=2, away_abbr="BOS", home_abbr="TBL",
            play_index=1, league_code="NHL", score_pattern=SCORE_PATTERN
        )
        assert result is not None
        assert result.away_score == 2
        assert result.home_score == 1

    def test_includes_raw_data(self):
        """Includes raw data in result."""
        SCORE_PATTERN = re.compile(r"^(\d+)\s*-\s*(\d+)$")
        html = '''
        <tr>
            <td>10:00</td>
            <td data-stat="event">Shot</td>
            <td data-stat="team">TBL</td>
            <td data-stat="description">Shot by Player</td>
        </tr>
        '''
        soup = BeautifulSoup(html, "lxml")
        row = soup.find("tr")
        result = parse_pbp_row(
            row, period=1, away_abbr="BOS", home_abbr="TBL",
            play_index=0, league_code="NHL", score_pattern=SCORE_PATTERN
        )
        assert result is not None
        assert "raw_data" in dir(result)
        assert result.raw_data is not None
