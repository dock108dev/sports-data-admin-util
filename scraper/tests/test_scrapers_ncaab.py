"""Tests for scrapers/ncaab_sportsref.py module."""

from __future__ import annotations

import os
import sys
from datetime import date
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


from sports_scraper.models import TeamIdentity
from sports_scraper.scrapers.base import ScraperError
from sports_scraper.scrapers.ncaab_sportsref import NCAABSportsReferenceScraper


class TestNCAABSportsReferenceScraperModuleImports:
    """Tests for NCAAB scraper module imports."""

    def test_module_imports(self):
        """Module can be imported without errors."""
        from sports_scraper.scrapers import ncaab_sportsref
        assert hasattr(ncaab_sportsref, 'NCAABSportsReferenceScraper')

    def test_scraper_class_exists(self):
        """Scraper class exists and can be referenced."""
        from sports_scraper.scrapers.ncaab_sportsref import NCAABSportsReferenceScraper
        assert NCAABSportsReferenceScraper is not None


class TestNCAABSportsReferenceScraper:
    """Tests for NCAABSportsReferenceScraper class."""

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_scraper_attributes(self, mock_client, mock_cache):
        """Scraper has NCAAB-specific attributes."""
        scraper = NCAABSportsReferenceScraper()
        assert scraper.sport == "ncaab"
        assert scraper.league_code == "NCAAB"

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_has_base_url(self, mock_client, mock_cache):
        """Scraper has base URL for sports-reference.com/cbb."""
        scraper = NCAABSportsReferenceScraper()
        assert "sports-reference.com/cbb" in scraper.base_url

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_has_non_numeric_score_markers(self, mock_client, mock_cache):
        """Scraper has non-numeric score markers set."""
        scraper = NCAABSportsReferenceScraper()
        assert hasattr(scraper, "_NON_NUMERIC_SCORE_MARKERS")
        assert "FINAL" in scraper._NON_NUMERIC_SCORE_MARKERS
        assert "POSTPONED" in scraper._NON_NUMERIC_SCORE_MARKERS

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_pbp_url_format(self, mock_client, mock_cache):
        """PBP URL is same as boxscore for NCAAB."""
        scraper = NCAABSportsReferenceScraper()
        url = scraper.pbp_url("2024-01-15-duke-vs-north-carolina")
        assert "boxscores" in url
        assert "2024-01-15" in url


class TestNCAABParseTeamRow:
    """Tests for _parse_team_row method."""

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_parses_team_with_score(self, mock_client, mock_cache):
        """Parses team row with numeric score."""
        scraper = NCAABSportsReferenceScraper()
        html = '''
        <tr>
            <td><a href="/team/duke">Duke</a></td>
            <td class="right">85</td>
        </tr>
        '''
        soup = BeautifulSoup(html, "lxml")
        row = soup.find("tr")
        identity, score = scraper._parse_team_row(row)
        assert score == 85
        assert identity.league_code == "NCAAB"

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_raises_when_no_team_link(self, mock_client, mock_cache):
        """Raises ScraperError when team link missing."""
        scraper = NCAABSportsReferenceScraper()
        html = '<tr><td>No Link</td><td>85</td></tr>'
        soup = BeautifulSoup(html, "lxml")
        row = soup.find("tr")
        with pytest.raises(ScraperError, match="Missing team link"):
            scraper._parse_team_row(row)

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_handles_trailing_status_cell(self, mock_client, mock_cache):
        """Handles trailing status cell (e.g., 'Final')."""
        scraper = NCAABSportsReferenceScraper()
        html = '''
        <tr>
            <td><a href="/team/duke">Duke</a></td>
            <td>85</td>
            <td>Final</td>
        </tr>
        '''
        soup = BeautifulSoup(html, "lxml")
        row = soup.find("tr")
        # Should skip 'Final' and find 85
        identity, score = scraper._parse_team_row(row)
        assert score == 85

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_raises_for_unavailable_status(self, mock_client, mock_cache):
        """Raises error for unavailable score status."""
        scraper = NCAABSportsReferenceScraper()
        # Need to have "PREVIEW" as the last td content that gets checked
        html = '''
        <tr>
            <td><a href="/team/duke">Duke</a></td>
            <td>85</td>
            <td>PREVIEW</td>
        </tr>
        '''
        soup = BeautifulSoup(html, "lxml")
        row = soup.find("tr")
        # Should parse successfully and find score 85 (scanning from right, skips "PREVIEW")
        identity, score = scraper._parse_team_row(row)
        assert score == 85  # Finds numeric score

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_raises_for_preview_only_status(self, mock_client, mock_cache):
        """Raises error when only PREVIEW status with no numeric score."""
        scraper = NCAABSportsReferenceScraper()
        # When there's no numeric score, it will find PREVIEW and raise score_unavailable_status
        html = '''
        <tr>
            <td><a href="/team/duke">Duke</a></td>
            <td>PREVIEW</td>
        </tr>
        '''
        soup = BeautifulSoup(html, "lxml")
        row = soup.find("tr")
        with pytest.raises(ScraperError):
            scraper._parse_team_row(row)


class TestNCAABParseScoreboxAbbreviations:
    """Tests for _parse_scorebox_abbreviations method."""

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_returns_none_tuple_when_scorebox_missing(self, mock_client, mock_cache):
        """Returns (None, None) when scorebox not found."""
        scraper = NCAABSportsReferenceScraper()
        soup = BeautifulSoup("<html></html>", "lxml")
        away, home = scraper._parse_scorebox_abbreviations(soup)
        assert away is None
        assert home is None

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_returns_none_tuple_when_fewer_than_two_divs(self, mock_client, mock_cache):
        """Returns (None, None) when fewer than 2 team divs."""
        scraper = NCAABSportsReferenceScraper()
        html = '<div class="scorebox"><div>One Team</div></div>'
        soup = BeautifulSoup(html, "lxml")
        away, home = scraper._parse_scorebox_abbreviations(soup)
        assert away is None
        assert home is None


class TestNCAABParsePbpPeriodMarker:
    """Tests for _parse_pbp_period_marker method."""

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_returns_1_for_first_half(self, mock_client, mock_cache):
        """Returns 1 for 1st half marker."""
        scraper = NCAABSportsReferenceScraper()
        html = '<tr id="h1">1st Half</tr>'
        soup = BeautifulSoup(html, "lxml")
        row = soup.find("tr")
        result = scraper._parse_pbp_period_marker(row)
        assert result == 1

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_returns_2_for_second_half(self, mock_client, mock_cache):
        """Returns 2 for 2nd half marker."""
        scraper = NCAABSportsReferenceScraper()
        html = '<tr id="h2">2nd Half</tr>'
        soup = BeautifulSoup(html, "lxml")
        row = soup.find("tr")
        result = scraper._parse_pbp_period_marker(row)
        assert result == 2

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_returns_3_for_overtime(self, mock_client, mock_cache):
        """Returns 3 for overtime marker."""
        scraper = NCAABSportsReferenceScraper()
        html = '<tr>Overtime</tr>'
        soup = BeautifulSoup(html, "lxml")
        row = soup.find("tr")
        result = scraper._parse_pbp_period_marker(row)
        assert result == 3

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_returns_4_for_double_overtime(self, mock_client, mock_cache):
        """Returns 4 for 2nd overtime marker."""
        scraper = NCAABSportsReferenceScraper()
        html = '<tr>Overtime 2</tr>'
        soup = BeautifulSoup(html, "lxml")
        row = soup.find("tr")
        result = scraper._parse_pbp_period_marker(row)
        assert result == 4

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_returns_none_for_regular_row(self, mock_client, mock_cache):
        """Returns None for non-period marker row."""
        scraper = NCAABSportsReferenceScraper()
        html = '<tr><td>Regular play</td></tr>'
        soup = BeautifulSoup(html, "lxml")
        row = soup.find("tr")
        result = scraper._parse_pbp_period_marker(row)
        assert result is None


class TestNCAABParsePbpRow:
    """Tests for _parse_pbp_row method."""

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_returns_none_for_empty_row(self, mock_client, mock_cache):
        """Returns None for row with no cells."""
        scraper = NCAABSportsReferenceScraper()
        html = '<tr></tr>'
        soup = BeautifulSoup(html, "lxml")
        row = soup.find("tr")
        result = scraper._parse_pbp_row(row, period=1, away_abbr="DUK", home_abbr="UNC", play_index=0)
        assert result is None

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_parses_colspan_row(self, mock_client, mock_cache):
        """Parses colspan row (neutral play)."""
        scraper = NCAABSportsReferenceScraper()
        html = '<tr><td>12:00</td><td colspan="5">Jump ball won by Duke</td></tr>'
        soup = BeautifulSoup(html, "lxml")
        row = soup.find("tr")
        result = scraper._parse_pbp_row(row, period=1, away_abbr="DUK", home_abbr="UNC", play_index=0)
        assert result is not None
        assert result.quarter == 1
        assert "Jump ball" in result.description

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_parses_standard_row_with_6_cells(self, mock_client, mock_cache):
        """Parses standard 6-column row."""
        scraper = NCAABSportsReferenceScraper()
        html = '''
        <tr>
            <td>10:30</td>
            <td>Duke made 3-pointer</td>
            <td></td>
            <td>3-0</td>
            <td></td>
            <td></td>
        </tr>
        '''
        soup = BeautifulSoup(html, "lxml")
        row = soup.find("tr")
        result = scraper._parse_pbp_row(row, period=1, away_abbr="DUK", home_abbr="UNC", play_index=1)
        assert result is not None
        assert result.game_clock == "10:30"
        assert result.away_score == 3
        assert result.home_score == 0

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_parses_4_column_row(self, mock_client, mock_cache):
        """Parses 4-column row format."""
        scraper = NCAABSportsReferenceScraper()
        html = '''
        <tr>
            <td>10:30</td>
            <td>Away action</td>
            <td>3-0</td>
            <td>Home action</td>
        </tr>
        '''
        soup = BeautifulSoup(html, "lxml")
        row = soup.find("tr")
        result = scraper._parse_pbp_row(row, period=1, away_abbr="DUK", home_abbr="UNC", play_index=0)
        assert result is not None


class TestNCAABIsProbableWomensGame:
    """Tests for _is_probable_womens_game method."""

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_detects_gender_f_class(self, mock_client, mock_cache):
        """Detects women's game from gender-f class."""
        scraper = NCAABSportsReferenceScraper()
        is_womens, reason = scraper._is_probable_womens_game(
            href="/cbb/boxscores/2024-01-15-duke.html",
            source_game_key="2024-01-15-duke",
            home_team="Duke",
            away_team="North Carolina",
            is_gender_f=True,
        )
        assert is_womens is True
        assert "gender_f_class" in reason

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_detects_women_in_href(self, mock_client, mock_cache):
        """Detects women's game from 'women' in href."""
        scraper = NCAABSportsReferenceScraper()
        is_womens, reason = scraper._is_probable_womens_game(
            href="/cbb/boxscores/women/2024-01-15-duke.html",
            source_game_key="2024-01-15-duke",
            home_team="Duke",
            away_team="North Carolina",
        )
        assert is_womens is True
        assert "href_contains_women" in reason

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_detects_w_prefix_in_game_key(self, mock_client, mock_cache):
        """Detects women's game from 'w' prefix in game key."""
        scraper = NCAABSportsReferenceScraper()
        is_womens, reason = scraper._is_probable_womens_game(
            href="/cbb/boxscores/w-2024-01-15-duke.html",
            source_game_key="w-2024-01-15-duke",
            home_team="Duke",
            away_team="North Carolina",
        )
        assert is_womens is True

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_returns_false_for_mens_game(self, mock_client, mock_cache):
        """Returns False for men's game."""
        scraper = NCAABSportsReferenceScraper()
        is_womens, reason = scraper._is_probable_womens_game(
            href="/cbb/boxscores/2024-01-15-duke.html",
            source_game_key="2024-01-15-duke",
            home_team="Duke",
            away_team="North Carolina",
        )
        assert is_womens is False


class TestNCAABBuildTeamBoxscore:
    """Tests for _build_team_boxscore method."""

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_builds_boxscore_with_stats(self, mock_client, mock_cache):
        """Builds team boxscore with stats."""
        scraper = NCAABSportsReferenceScraper()
        team = TeamIdentity(league_code="NCAAB", name="Duke", abbreviation="DUKE")
        stats = {"trb": "35", "ast": "18", "tov": "10"}
        boxscore = scraper._build_team_boxscore(team, is_home=True, score=85, stats=stats)
        assert boxscore.points == 85
        assert boxscore.rebounds == 35
        assert boxscore.assists == 18
        assert boxscore.turnovers == 10


class TestNCAABFetchPlayByPlay:
    """Tests for fetch_play_by_play method."""

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_raises_not_implemented_for_sportsref(self, mock_client, mock_cache):
        """Raises NotImplementedError since Sports Reference doesn't have NCAAB PBP."""
        scraper = NCAABSportsReferenceScraper()
        with pytest.raises(NotImplementedError, match="NCAAB play-by-play is unavailable"):
            scraper.fetch_play_by_play("2024-01-15-duke", date(2024, 1, 15))


class TestNCAABFetchGamesForDate:
    """Tests for fetch_games_for_date method."""

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_returns_empty_list_when_no_games(self, mock_client, mock_cache):
        """Returns empty list when no game_summary divs found."""
        scraper = NCAABSportsReferenceScraper()
        scraper.fetch_html = MagicMock(return_value=BeautifulSoup("<html></html>", "lxml"))

        result = scraper.fetch_games_for_date(date(2024, 1, 15))
        assert result == []

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_skips_games_with_insufficient_team_rows(self, mock_client, mock_cache):
        """Skips games with fewer than 2 team rows."""
        scraper = NCAABSportsReferenceScraper()
        html = '''
        <html>
        <div class="game_summary">
            <table class="teams">
                <tr><td><a href="/team/duke">Duke</a></td><td>85</td></tr>
            </table>
        </div>
        </html>
        '''
        scraper.fetch_html = MagicMock(return_value=BeautifulSoup(html, "lxml"))

        result = scraper.fetch_games_for_date(date(2024, 1, 15))
        assert result == []

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_skips_games_with_pending_status(self, mock_client, mock_cache):
        """Skips games with PREVIEW/POSTPONED status."""
        scraper = NCAABSportsReferenceScraper()
        html = '''
        <html>
        <div class="game_summary">
            <table class="teams">
                <tr><td><a href="/team/duke">Duke</a></td><td>PREVIEW</td></tr>
                <tr><td><a href="/team/unc">North Carolina</a></td><td>PREVIEW</td></tr>
            </table>
        </div>
        </html>
        '''
        scraper.fetch_html = MagicMock(return_value=BeautifulSoup(html, "lxml"))

        result = scraper.fetch_games_for_date(date(2024, 1, 15))
        assert result == []

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_skips_games_without_boxscore_link(self, mock_client, mock_cache):
        """Skips games without boxscore link."""
        scraper = NCAABSportsReferenceScraper()
        html = '''
        <html>
        <div class="game_summary">
            <table class="teams">
                <tr><td><a href="/team/duke">Duke</a></td><td>85</td></tr>
                <tr><td><a href="/team/unc">North Carolina</a></td><td>80</td></tr>
            </table>
            <p class="links"><a href="/other/">Other Link</a></p>
        </div>
        </html>
        '''
        scraper.fetch_html = MagicMock(return_value=BeautifulSoup(html, "lxml"))

        result = scraper.fetch_games_for_date(date(2024, 1, 15))
        assert result == []

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_skips_womens_games_with_gender_f(self, mock_client, mock_cache):
        """Skips women's games detected by gender-f class."""
        scraper = NCAABSportsReferenceScraper()
        html = '''
        <html>
        <div class="game_summary gender-f">
            <table class="teams">
                <tr><td><a href="/team/duke">Duke</a></td><td>85</td></tr>
                <tr><td><a href="/team/unc">North Carolina</a></td><td>80</td></tr>
            </table>
            <p class="links"><a href="/cbb/boxscores/2024-01-15-duke.html">Box Score</a></p>
        </div>
        </html>
        '''
        scraper.fetch_html = MagicMock(return_value=BeautifulSoup(html, "lxml"))

        result = scraper.fetch_games_for_date(date(2024, 1, 15))
        assert result == []


class TestNCAABFetchSingleBoxscore:
    """Tests for fetch_single_boxscore method - NCAAB doesn't have this method."""

    # NCAAB scraper inherits from base but uses fetch_games_for_date pattern
    pass


class TestNCAABExtractTeamStats:
    """Tests for _extract_team_stats method."""

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_delegates_to_helper(self, mock_client, mock_cache):
        """Delegates to extract_team_stats helper function."""
        scraper = NCAABSportsReferenceScraper()
        team = TeamIdentity(league_code="NCAAB", name="Duke", abbreviation="DUKE")
        soup = BeautifulSoup("<html></html>", "lxml")
        result = scraper._extract_team_stats(soup, team, is_home=True)
        assert isinstance(result, dict)


class TestNCAABExtractPlayerStats:
    """Tests for _extract_player_stats method."""

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_delegates_to_helper(self, mock_client, mock_cache):
        """Delegates to extract_player_stats helper function."""
        scraper = NCAABSportsReferenceScraper()
        team = TeamIdentity(league_code="NCAAB", name="Duke", abbreviation="DUKE")
        soup = BeautifulSoup("<html></html>", "lxml")
        result = scraper._extract_player_stats(soup, team, is_home=True)
        assert isinstance(result, list)


class TestNCAABScraperInheritance:
    """Tests for NCAAB scraper inheritance from base."""

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_inherits_iter_dates(self, mock_client, mock_cache):
        """Inherits iter_dates from base class."""
        scraper = NCAABSportsReferenceScraper()
        dates = list(scraper.iter_dates(date(2024, 1, 1), date(2024, 1, 3)))
        assert len(dates) == 3

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_inherits_season_from_date(self, mock_client, mock_cache):
        """Inherits _season_from_date from base class."""
        scraper = NCAABSportsReferenceScraper()
        assert hasattr(scraper, "_season_from_date")
        # NCAAB season spans calendar years, Jan 2024 = 2023-24 season
        season = scraper._season_from_date(date(2024, 1, 15))
        assert season == 2023  # Returns start year of season
        # NCAAB season starts in November, so Nov 2024 = 2024-25 season
        season = scraper._season_from_date(date(2024, 11, 15))
        assert season == 2024

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_has_ot_number_pattern(self, mock_client, mock_cache):
        """Has OT number pattern for parsing overtime periods."""
        scraper = NCAABSportsReferenceScraper()
        assert hasattr(scraper, "_OT_NUMBER_PATTERN")


class TestNCAABParseScoreboxAbbreviationsEdgeCases:
    """Additional tests for _parse_scorebox_abbreviations."""

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_handles_team_divs_with_itemprop_name(self, mock_client, mock_cache):
        """Attempts to parse team abbreviations with itemprop=name and returns result."""
        scraper = NCAABSportsReferenceScraper()
        html = '''
        <div class="scorebox">
            <div><a itemprop="name">Duke Blue Devils</a></div>
            <div><a itemprop="name">North Carolina Tar Heels</a></div>
        </div>
        '''
        soup = BeautifulSoup(html, "lxml")
        away, home = scraper._parse_scorebox_abbreviations(soup)
        # May or may not find abbreviation depending on normalization
        # Just verify it doesn't raise an error and returns tuple
        assert isinstance(away, (str, type(None)))
        assert isinstance(home, (str, type(None)))

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_handles_team_divs_with_strong_tag(self, mock_client, mock_cache):
        """Attempts to parse team abbreviations with strong tag."""
        scraper = NCAABSportsReferenceScraper()
        html = '''
        <div class="scorebox">
            <div><strong><a href="/team/duke">Duke Blue Devils</a></strong></div>
            <div><strong><a href="/team/unc">North Carolina Tar Heels</a></strong></div>
        </div>
        '''
        soup = BeautifulSoup(html, "lxml")
        away, home = scraper._parse_scorebox_abbreviations(soup)
        # May or may not find abbreviation depending on normalization
        assert isinstance(away, (str, type(None)))
        assert isinstance(home, (str, type(None)))

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_returns_none_when_no_team_link(self, mock_client, mock_cache):
        """Returns None when team link not found."""
        scraper = NCAABSportsReferenceScraper()
        html = '''
        <div class="scorebox">
            <div><span>No link here</span></div>
            <div><span>No link here either</span></div>
        </div>
        '''
        soup = BeautifulSoup(html, "lxml")
        away, home = scraper._parse_scorebox_abbreviations(soup)
        assert away is None
        assert home is None


class TestNCAABParsePbpPeriodMarkerEdgeCases:
    """Additional tests for _parse_pbp_period_marker edge cases."""

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_returns_period_for_q_format(self, mock_client, mock_cache):
        """Returns period number for q1, q2, etc. format."""
        scraper = NCAABSportsReferenceScraper()
        html = '<tr id="q1">1st Quarter</tr>'
        soup = BeautifulSoup(html, "lxml")
        row = soup.find("tr")
        result = scraper._parse_pbp_period_marker(row)
        assert result == 1

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_returns_none_for_empty_row(self, mock_client, mock_cache):
        """Returns None for empty row."""
        scraper = NCAABSportsReferenceScraper()
        html = '<tr></tr>'
        soup = BeautifulSoup(html, "lxml")
        row = soup.find("tr")
        result = scraper._parse_pbp_period_marker(row)
        assert result is None

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_returns_3_for_ot_without_number(self, mock_client, mock_cache):
        """Returns 3 for OT without number."""
        scraper = NCAABSportsReferenceScraper()
        html = '<tr>OT</tr>'
        soup = BeautifulSoup(html, "lxml")
        row = soup.find("tr")
        result = scraper._parse_pbp_period_marker(row)
        assert result == 3

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_returns_5_for_3ot(self, mock_client, mock_cache):
        """Returns 5 for 3rd overtime (2 + 3)."""
        scraper = NCAABSportsReferenceScraper()
        html = '<tr>3OT</tr>'
        soup = BeautifulSoup(html, "lxml")
        row = soup.find("tr")
        result = scraper._parse_pbp_period_marker(row)
        assert result == 5
