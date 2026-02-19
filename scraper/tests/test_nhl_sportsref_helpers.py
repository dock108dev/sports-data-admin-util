"""Tests for NHL Hockey Reference parsing helpers."""

from __future__ import annotations

import re
from unittest.mock import patch

from bs4 import BeautifulSoup

from sports_scraper.models import NormalizedPlay
from sports_scraper.scrapers.nhl_sportsref_helpers import (
    extract_score,
    normalize_pbp_team_abbr,
    parse_pbp_period_marker,
    parse_pbp_row,
    parse_scorebox_abbreviations,
    parse_scorebox_team,
)

# Re-usable patterns (mirroring what the real scraper constructs)
SCORE_PATTERN = re.compile(r"(\d+)\s*[-–]\s*(\d+)")
OT_PATTERN = re.compile(r"(\d+)\s*(?:st|nd|rd|th)?\s*ot|ot\s*(\d+)", re.IGNORECASE)


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


def _tag(html: str, name: str = "tr"):
    """Parse HTML and return the first tag of the given type (not the soup object)."""
    return BeautifulSoup(html, "html.parser").find(name)


# ---------------------------------------------------------------------------
# parse_scorebox_abbreviations
# ---------------------------------------------------------------------------
class TestParseScoreboxAbbreviations:
    @patch("sports_scraper.scrapers.nhl_sportsref_helpers.normalize_team_name")
    def test_no_scorebox(self, mock_norm):
        soup = _soup("<div>no scorebox</div>")
        assert parse_scorebox_abbreviations(soup, "NHL") == (None, None)
        mock_norm.assert_not_called()

    @patch("sports_scraper.scrapers.nhl_sportsref_helpers.normalize_team_name")
    def test_fewer_than_two_team_divs(self, mock_norm):
        soup = _soup('<div class="scorebox"><div>only one</div></div>')
        assert parse_scorebox_abbreviations(soup, "NHL") == (None, None)

    @patch("sports_scraper.scrapers.nhl_sportsref_helpers.normalize_team_name")
    def test_itemprop_links(self, mock_norm):
        mock_norm.side_effect = [("Boston Bruins", "BOS"), ("Toronto Maple Leafs", "TOR")]
        soup = _soup(
            '<div class="scorebox">'
            '<div><a itemprop="name">Bruins</a></div>'
            '<div><a itemprop="name">Leafs</a></div>'
            "</div>"
        )
        away, home = parse_scorebox_abbreviations(soup, "NHL")
        assert away == "BOS"
        assert home == "TOR"

    @patch("sports_scraper.scrapers.nhl_sportsref_helpers.normalize_team_name")
    def test_strong_a_fallback(self, mock_norm):
        mock_norm.return_value = ("Boston Bruins", "BOS")
        soup = _soup(
            '<div class="scorebox">'
            "<div><strong><a>Bruins</a></strong></div>"
            "<div><strong><a>Bruins</a></strong></div>"
            "</div>"
        )
        away, home = parse_scorebox_abbreviations(soup, "NHL")
        assert away == "BOS"
        assert home == "BOS"

    @patch("sports_scraper.scrapers.nhl_sportsref_helpers.normalize_team_name")
    def test_no_link_returns_none(self, mock_norm):
        soup = _soup(
            '<div class="scorebox">'
            "<div><span>no link</span></div>"
            "<div><span>no link</span></div>"
            "</div>"
        )
        assert parse_scorebox_abbreviations(soup, "NHL") == (None, None)


# ---------------------------------------------------------------------------
# parse_scorebox_team
# ---------------------------------------------------------------------------
class TestParseScoreboxTeam:
    @patch("sports_scraper.scrapers.nhl_sportsref_helpers.normalize_team_name")
    def test_itemprop_link(self, mock_norm):
        mock_norm.return_value = ("Boston Bruins", "BOS")
        div = _soup(
            '<div><a itemprop="name">Bruins</a><div class="score">3</div></div>'
        )
        result = parse_scorebox_team(div, "NHL")
        assert result is not None
        identity, score = result
        assert score == 3
        assert identity.abbreviation == "BOS"

    @patch("sports_scraper.scrapers.nhl_sportsref_helpers.normalize_team_name")
    def test_strong_a_fallback(self, mock_norm):
        mock_norm.return_value = ("Toronto Maple Leafs", "TOR")
        div = _soup(
            '<div><strong><a>Leafs</a></strong><div class="score">5</div></div>'
        )
        result = parse_scorebox_team(div, "NHL")
        assert result is not None
        _, score = result
        assert score == 5

    def test_no_link_returns_none(self):
        div = _soup("<div><span>no link</span></div>")
        assert parse_scorebox_team(div, "NHL") is None

    @patch("sports_scraper.scrapers.nhl_sportsref_helpers.normalize_team_name")
    def test_no_score_div(self, mock_norm):
        mock_norm.return_value = ("Boston Bruins", "BOS")
        div = _soup('<div><a itemprop="name">Bruins</a></div>')
        assert parse_scorebox_team(div, "NHL") is None

    @patch("sports_scraper.scrapers.nhl_sportsref_helpers.normalize_team_name")
    def test_invalid_score(self, mock_norm):
        mock_norm.return_value = ("Boston Bruins", "BOS")
        div = _soup(
            '<div><a itemprop="name">Bruins</a><div class="score">abc</div></div>'
        )
        assert parse_scorebox_team(div, "NHL") is None


# ---------------------------------------------------------------------------
# parse_pbp_period_marker
# ---------------------------------------------------------------------------
class TestParsePbpPeriodMarker:
    def test_1st_period_text(self):
        row = _tag('<tr id=""><td>1st Period</td></tr>')
        period, shootout = parse_pbp_period_marker(row, OT_PATTERN)
        assert period == 1
        assert shootout is False

    def test_2nd_period_text(self):
        row = _tag('<tr id=""><td>2nd Period</td></tr>')
        assert parse_pbp_period_marker(row, OT_PATTERN) == (2, False)

    def test_3rd_period_text(self):
        row = _tag('<tr id=""><td>3rd Period</td></tr>')
        assert parse_pbp_period_marker(row, OT_PATTERN) == (3, False)

    def test_row_id_p1(self):
        row = _tag('<tr id="p1"><td></td></tr>')
        assert parse_pbp_period_marker(row, OT_PATTERN) == (1, False)

    def test_row_id_2nd(self):
        row = _tag('<tr id="2nd"><td></td></tr>')
        assert parse_pbp_period_marker(row, OT_PATTERN) == (2, False)

    def test_row_id_third(self):
        row = _tag('<tr id="third"><td></td></tr>')
        assert parse_pbp_period_marker(row, OT_PATTERN) == (3, False)

    def test_shootout(self):
        row = _tag('<tr id=""><td>Shootout</td></tr>')
        period, shootout = parse_pbp_period_marker(row, OT_PATTERN)
        assert period is None
        assert shootout is True

    def test_shootout_row_id(self):
        row = _tag('<tr id="so"><td></td></tr>')
        assert parse_pbp_period_marker(row, OT_PATTERN) == (None, True)

    def test_ot_without_number(self):
        row = _tag('<tr id=""><td>Overtime</td></tr>')
        period, shootout = parse_pbp_period_marker(row, OT_PATTERN)
        assert period == 4
        assert shootout is False

    def test_ot_with_number(self):
        row = _tag('<tr id=""><td>2nd OT</td></tr>')
        period, shootout = parse_pbp_period_marker(row, OT_PATTERN)
        assert period == 5
        assert shootout is False

    def test_empty_marker(self):
        row = _tag("<tr><td></td></tr>")
        assert parse_pbp_period_marker(row, OT_PATTERN) == (None, False)

    def test_first_period_word(self):
        row = _tag('<tr id="first"><td></td></tr>')
        assert parse_pbp_period_marker(row, OT_PATTERN) == (1, False)

    def test_second_period_word(self):
        row = _tag('<tr id=""><td>Second Period</td></tr>')
        assert parse_pbp_period_marker(row, OT_PATTERN) == (2, False)

    def test_third_period_word(self):
        row = _tag('<tr id=""><td>Third Period</td></tr>')
        assert parse_pbp_period_marker(row, OT_PATTERN) == (3, False)

    def test_unrecognized_text(self):
        row = _tag('<tr id=""><td>Something Else</td></tr>')
        assert parse_pbp_period_marker(row, OT_PATTERN) == (None, False)


# ---------------------------------------------------------------------------
# normalize_pbp_team_abbr
# ---------------------------------------------------------------------------
class TestNormalizePbpTeamAbbr:
    def test_none_input(self):
        assert normalize_pbp_team_abbr(None, "NHL", "BOS", "TOR") is None

    def test_empty_string(self):
        assert normalize_pbp_team_abbr("", "NHL", "BOS", "TOR") is None

    def test_whitespace_only(self):
        assert normalize_pbp_team_abbr("   ", "NHL", "BOS", "TOR") is None

    def test_away_match(self):
        assert normalize_pbp_team_abbr("bos", "NHL", "BOS", "TOR") == "BOS"

    def test_home_match(self):
        assert normalize_pbp_team_abbr("tor", "NHL", "BOS", "TOR") == "TOR"

    @patch("sports_scraper.scrapers.nhl_sportsref_helpers.normalize_team_name")
    def test_fallback_to_normalize_team_name(self, mock_norm):
        mock_norm.return_value = ("Montreal Canadiens", "MTL")
        result = normalize_pbp_team_abbr("Montreal", "NHL", "BOS", "TOR")
        assert result == "MTL"
        mock_norm.assert_called_once_with("NHL", "Montreal")

    def test_away_abbr_none(self):
        # When away_abbr is None, should skip away match and try home
        assert normalize_pbp_team_abbr("TOR", "NHL", None, "TOR") == "TOR"

    def test_home_abbr_none(self):
        assert normalize_pbp_team_abbr("BOS", "NHL", "BOS", None) == "BOS"


# ---------------------------------------------------------------------------
# extract_score
# ---------------------------------------------------------------------------
class TestExtractScore:
    def test_none_input(self):
        assert extract_score(None, SCORE_PATTERN) == (None, None)

    def test_empty_string(self):
        assert extract_score("", SCORE_PATTERN) == (None, None)

    def test_pattern_match(self):
        assert extract_score("3-2", SCORE_PATTERN) == (3, 2)

    def test_pattern_match_with_spaces(self):
        assert extract_score("  3 - 2  ", SCORE_PATTERN) == (3, 2)

    def test_no_match(self):
        assert extract_score("abc", SCORE_PATTERN) == (None, None)

    def test_en_dash(self):
        assert extract_score("4–1", SCORE_PATTERN) == (4, 1)


# ---------------------------------------------------------------------------
# parse_pbp_row
# ---------------------------------------------------------------------------
class TestParsePbpRow:
    def test_no_cells(self):
        row = _tag("<tr></tr>")
        result = parse_pbp_row(
            row, period=1, away_abbr="BOS", home_abbr="TOR",
            play_index=0, league_code="NHL", score_pattern=SCORE_PATTERN,
        )
        assert result is None

    def test_two_cell_row(self):
        row = _tag("<tr><td>10:00</td><td>Period start</td></tr>")
        result = parse_pbp_row(
            row, period=1, away_abbr="BOS", home_abbr="TOR",
            play_index=0, league_code="NHL", score_pattern=SCORE_PATTERN,
        )
        assert result is not None
        assert isinstance(result, NormalizedPlay)
        assert result.play_index == 0
        assert result.quarter == 1
        assert result.game_clock == "10:00"
        assert result.description == "Period start"
        assert result.team_abbreviation is None

    @patch("sports_scraper.scrapers.nhl_sportsref_helpers.normalize_pbp_team_abbr")
    def test_full_row_with_data_stats(self, mock_norm):
        mock_norm.return_value = "BOS"
        row = _tag(
            "<tr>"
            '<td data-stat="time">05:00</td>'
            '<td data-stat="event">Goal</td>'
            '<td data-stat="team">BOS</td>'
            '<td data-stat="description">Power play goal</td>'
            '<td data-stat="score">1-0</td>'
            "</tr>"
        )
        result = parse_pbp_row(
            row, period=2, away_abbr="BOS", home_abbr="TOR",
            play_index=5, league_code="NHL", score_pattern=SCORE_PATTERN,
        )
        assert result is not None
        assert result.play_type == "Goal"
        assert result.description == "Power play goal"
        assert result.away_score == 1
        assert result.home_score == 0
        assert result.quarter == 2
        assert result.play_index == 5

    @patch("sports_scraper.scrapers.nhl_sportsref_helpers.normalize_pbp_team_abbr")
    def test_fallback_to_cell_texts(self, mock_norm):
        mock_norm.return_value = "TOR"
        row = _tag(
            "<tr>"
            "<td>12:00</td>"
            "<td>Shot</td>"
            "<td>TOR</td>"
            "<td>Wrist shot saved</td>"
            "</tr>"
        )
        result = parse_pbp_row(
            row, period=1, away_abbr="BOS", home_abbr="TOR",
            play_index=3, league_code="NHL", score_pattern=SCORE_PATTERN,
        )
        assert result is not None
        assert result.play_type == "Shot"
        assert result.description == "Wrist shot saved"
        assert result.team_abbreviation == "TOR"

    @patch("sports_scraper.scrapers.nhl_sportsref_helpers.normalize_pbp_team_abbr")
    def test_score_from_cell_texts(self, mock_norm):
        mock_norm.return_value = "BOS"
        row = _tag(
            "<tr>"
            "<td>08:00</td>"
            "<td>2-1</td>"
            "<td>BOS</td>"
            "<td>Even strength goal</td>"
            "</tr>"
        )
        result = parse_pbp_row(
            row, period=3, away_abbr="BOS", home_abbr="TOR",
            play_index=10, league_code="NHL", score_pattern=SCORE_PATTERN,
        )
        assert result is not None
        assert result.away_score == 2
        assert result.home_score == 1

    @patch("sports_scraper.scrapers.nhl_sportsref_helpers.normalize_pbp_team_abbr")
    def test_empty_game_clock(self, mock_norm):
        mock_norm.return_value = None
        row = _tag(
            "<tr>"
            "<td></td>"
            "<td>Faceoff</td>"
            "<td></td>"
            "<td>Center ice</td>"
            "</tr>"
        )
        result = parse_pbp_row(
            row, period=1, away_abbr="BOS", home_abbr="TOR",
            play_index=0, league_code="NHL", score_pattern=SCORE_PATTERN,
        )
        assert result is not None
        assert result.game_clock is None

    @patch("sports_scraper.scrapers.nhl_sportsref_helpers.normalize_pbp_team_abbr")
    def test_raw_data_populated(self, mock_norm):
        mock_norm.return_value = "BOS"
        row = _tag(
            "<tr>"
            '<td data-stat="time">01:00</td>'
            '<td data-stat="event">Hit</td>'
            '<td data-stat="team">BOS</td>'
            '<td data-stat="description">Body check</td>'
            "</tr>"
        )
        result = parse_pbp_row(
            row, period=1, away_abbr="BOS", home_abbr="TOR",
            play_index=1, league_code="NHL", score_pattern=SCORE_PATTERN,
        )
        assert result is not None
        assert "event" in result.raw_data
        assert "cells" in result.raw_data
        assert "data_stats" in result.raw_data
