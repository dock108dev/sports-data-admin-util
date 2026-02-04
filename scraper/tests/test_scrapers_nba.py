"""Tests for scrapers/nba_sportsref.py module."""

from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure the scraper package is importable
REPO_ROOT = Path(__file__).resolve().parents[2]
SCRAPER_ROOT = REPO_ROOT / "scraper"
if str(SCRAPER_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRAPER_ROOT))

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://user:pass@localhost:5432/test_db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("ENVIRONMENT", "development")


class TestNBASportsReferenceScraperModuleImports:
    """Tests for NBA scraper module imports."""

    def test_module_imports(self):
        """Module can be imported without errors."""
        from sports_scraper.scrapers import nba_sportsref
        assert hasattr(nba_sportsref, 'NBASportsReferenceScraper')

    def test_scraper_class_exists(self):
        """Scraper class exists and can be referenced."""
        from sports_scraper.scrapers.nba_sportsref import NBASportsReferenceScraper
        assert NBASportsReferenceScraper is not None

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_scraper_attributes(self, mock_client, mock_cache):
        """Scraper has NBA-specific attributes."""
        from sports_scraper.scrapers.nba_sportsref import NBASportsReferenceScraper
        scraper = NBASportsReferenceScraper()
        assert scraper.sport == "nba"
        assert scraper.league_code == "NBA"


class TestNBASportsReferenceScraperUrls:
    """Tests for URL generation methods."""

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_scoreboard_url_format(self, mock_client, mock_cache):
        """Scoreboard URL has correct format."""
        from sports_scraper.scrapers.nba_sportsref import NBASportsReferenceScraper
        scraper = NBASportsReferenceScraper()
        url = scraper.scoreboard_url(date(2024, 1, 15))
        assert "month=1" in url
        assert "day=15" in url
        assert "year=2024" in url

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_scoreboard_url_different_dates(self, mock_client, mock_cache):
        """Scoreboard URL works for different dates."""
        from sports_scraper.scrapers.nba_sportsref import NBASportsReferenceScraper
        scraper = NBASportsReferenceScraper()

        url1 = scraper.scoreboard_url(date(2024, 12, 25))
        assert "month=12" in url1
        assert "day=25" in url1

        url2 = scraper.scoreboard_url(date(2023, 6, 1))
        assert "month=6" in url2
        assert "year=2023" in url2


class TestNBAExtractTeamStats:
    """Tests for _extract_team_stats method."""

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_returns_empty_dict_when_table_not_found(self, mock_client, mock_cache):
        """Returns empty dict when table not found."""
        from bs4 import BeautifulSoup
        from sports_scraper.scrapers.nba_sportsref import NBASportsReferenceScraper
        scraper = NBASportsReferenceScraper()
        soup = BeautifulSoup("<html></html>", "lxml")
        result = scraper._extract_team_stats(soup, "BOS")
        assert result == {}

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_extracts_stats_from_basic_table(self, mock_client, mock_cache):
        """Extracts stats from box-{ABBR}-game-basic table."""
        from bs4 import BeautifulSoup
        from sports_scraper.scrapers.nba_sportsref import NBASportsReferenceScraper
        scraper = NBASportsReferenceScraper()
        html = '''
        <html>
        <table id="box-BOS-game-basic">
            <tfoot>
                <tr>
                    <td data-stat="pts">110</td>
                    <td data-stat="trb">45</td>
                    <td data-stat="ast">25</td>
                </tr>
            </tfoot>
        </table>
        </html>
        '''
        soup = BeautifulSoup(html, "lxml")
        result = scraper._extract_team_stats(soup, "BOS")
        assert isinstance(result, dict)


class TestNBAExtractPlayerStats:
    """Tests for _extract_player_stats method."""

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_returns_empty_list_when_no_table(self, mock_client, mock_cache):
        """Returns empty list when table not found."""
        from bs4 import BeautifulSoup
        from sports_scraper.scrapers.nba_sportsref import NBASportsReferenceScraper
        from sports_scraper.models import TeamIdentity
        scraper = NBASportsReferenceScraper()
        team = TeamIdentity(league_code="NBA", name="Boston Celtics", abbreviation="BOS")
        soup = BeautifulSoup("<html></html>", "lxml")
        result = scraper._extract_player_stats(soup, "BOS", team, is_home=True)
        assert result == []

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_extracts_players_from_table(self, mock_client, mock_cache):
        """Extracts players from basic table."""
        from bs4 import BeautifulSoup
        from sports_scraper.scrapers.nba_sportsref import NBASportsReferenceScraper
        from sports_scraper.models import TeamIdentity
        scraper = NBASportsReferenceScraper()
        team = TeamIdentity(league_code="NBA", name="Boston Celtics", abbreviation="BOS")
        html = '''
        <html>
        <table id="box-BOS-game-basic">
            <tbody>
                <tr>
                    <th data-stat="player"><a href="/players/t/tatumja01.html">Jayson Tatum</a></th>
                    <td data-stat="mp">35:20</td>
                    <td data-stat="pts">30</td>
                    <td data-stat="trb">10</td>
                    <td data-stat="ast">5</td>
                </tr>
            </tbody>
        </table>
        </html>
        '''
        soup = BeautifulSoup(html, "lxml")
        result = scraper._extract_player_stats(soup, "BOS", team, is_home=True)
        assert len(result) == 1
        assert result[0].player_name == "Jayson Tatum"
        assert result[0].points == 30

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_skips_thead_rows(self, mock_client, mock_cache):
        """Skips thead rows."""
        from bs4 import BeautifulSoup
        from sports_scraper.scrapers.nba_sportsref import NBASportsReferenceScraper
        from sports_scraper.models import TeamIdentity
        scraper = NBASportsReferenceScraper()
        team = TeamIdentity(league_code="NBA", name="Boston Celtics", abbreviation="BOS")
        html = '''
        <html>
        <table id="box-BOS-game-basic">
            <tbody>
                <tr class="thead"><th>Header</th></tr>
                <tr>
                    <th data-stat="player"><a href="/players/t/tatumja01.html">Jayson Tatum</a></th>
                    <td data-stat="pts">30</td>
                </tr>
            </tbody>
        </table>
        </html>
        '''
        soup = BeautifulSoup(html, "lxml")
        result = scraper._extract_player_stats(soup, "BOS", team, is_home=True)
        assert len(result) == 1


class TestNBABuildTeamBoxscore:
    """Tests for _build_team_boxscore method."""

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_builds_boxscore_with_stats(self, mock_client, mock_cache):
        """Builds team boxscore with parsed stats."""
        from sports_scraper.scrapers.nba_sportsref import NBASportsReferenceScraper
        from sports_scraper.models import TeamIdentity
        scraper = NBASportsReferenceScraper()
        team = TeamIdentity(league_code="NBA", name="Boston Celtics", abbreviation="BOS")
        stats = {"trb": "45", "ast": "25", "tov": "12"}
        boxscore = scraper._build_team_boxscore(team, is_home=True, score=110, stats=stats)
        assert boxscore.points == 110
        assert boxscore.rebounds == 45
        assert boxscore.assists == 25
        assert boxscore.turnovers == 12


class TestNBAFetchSingleBoxscore:
    """Tests for fetch_single_boxscore method."""

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_returns_none_on_fetch_error(self, mock_client, mock_cache):
        """Returns None when fetch fails."""
        from bs4 import BeautifulSoup
        from sports_scraper.scrapers.nba_sportsref import NBASportsReferenceScraper
        from unittest.mock import MagicMock
        scraper = NBASportsReferenceScraper()
        scraper.fetch_html = MagicMock(side_effect=Exception("Network error"))

        result = scraper.fetch_single_boxscore("202410220BOS", date(2024, 10, 22))
        assert result is None

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_returns_none_when_scorebox_missing(self, mock_client, mock_cache):
        """Returns None when scorebox not found."""
        from bs4 import BeautifulSoup
        from sports_scraper.scrapers.nba_sportsref import NBASportsReferenceScraper
        from unittest.mock import MagicMock
        scraper = NBASportsReferenceScraper()
        scraper.fetch_html = MagicMock(return_value=BeautifulSoup("<html></html>", "lxml"))

        result = scraper.fetch_single_boxscore("202410220BOS", date(2024, 10, 22))
        assert result is None


class TestNBASportsrefAbbrMap:
    """Tests for SPORTSREF_ABBR_MAP and _to_sportsref_abbr."""

    def test_sportsref_abbr_map_exists(self):
        """SPORTSREF_ABBR_MAP exists with expected entries."""
        from sports_scraper.scrapers.nba_sportsref import SPORTSREF_ABBR_MAP
        assert "CHA" in SPORTSREF_ABBR_MAP
        assert "BKN" in SPORTSREF_ABBR_MAP
        assert SPORTSREF_ABBR_MAP["CHA"] == "CHO"
        assert SPORTSREF_ABBR_MAP["BKN"] == "BRK"

    def test_to_sportsref_abbr_converts_known(self):
        """_to_sportsref_abbr converts known abbreviations."""
        from sports_scraper.scrapers.nba_sportsref import _to_sportsref_abbr
        assert _to_sportsref_abbr("CHA") == "CHO"
        assert _to_sportsref_abbr("BKN") == "BRK"

    def test_to_sportsref_abbr_returns_uppercase_unknown(self):
        """_to_sportsref_abbr returns uppercase for unknown abbreviations."""
        from sports_scraper.scrapers.nba_sportsref import _to_sportsref_abbr
        assert _to_sportsref_abbr("bos") == "BOS"
        assert _to_sportsref_abbr("LAL") == "LAL"


class TestNBAFetchGamesForDate:
    """Tests for fetch_games_for_date method."""

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_returns_empty_list_when_no_games(self, mock_client, mock_cache):
        """Returns empty list when no game_summary divs found."""
        from bs4 import BeautifulSoup
        from sports_scraper.scrapers.nba_sportsref import NBASportsReferenceScraper
        scraper = NBASportsReferenceScraper()
        scraper.fetch_html = MagicMock(return_value=BeautifulSoup("<html></html>", "lxml"))

        result = scraper.fetch_games_for_date(date(2024, 10, 22))
        assert result == []

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_skips_games_with_insufficient_team_rows(self, mock_client, mock_cache):
        """Skips games with fewer than 2 team rows."""
        from bs4 import BeautifulSoup
        from sports_scraper.scrapers.nba_sportsref import NBASportsReferenceScraper
        scraper = NBASportsReferenceScraper()
        html = '''
        <html>
        <div class="game_summary">
            <table class="teams">
                <tr><td><a href="/team/bos">Boston Celtics</a></td><td class="right">110</td></tr>
            </table>
        </div>
        </html>
        '''
        scraper.fetch_html = MagicMock(return_value=BeautifulSoup(html, "lxml"))

        result = scraper.fetch_games_for_date(date(2024, 10, 22))
        assert result == []


class TestNBAFetchSingleBoxscoreSuccess:
    """Tests for successful fetch_single_boxscore flows."""

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_returns_none_when_team_divs_insufficient(self, mock_client, mock_cache):
        """Returns None when fewer than 2 team divs in scorebox."""
        from bs4 import BeautifulSoup
        from sports_scraper.scrapers.nba_sportsref import NBASportsReferenceScraper
        scraper = NBASportsReferenceScraper()
        html = '<html><div class="scorebox"><div>One Team</div></div></html>'
        scraper.fetch_html = MagicMock(return_value=BeautifulSoup(html, "lxml"))

        result = scraper.fetch_single_boxscore("202410220BOS", date(2024, 10, 22))
        assert result is None

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_returns_none_when_team_link_missing(self, mock_client, mock_cache):
        """Returns None when team link missing in scorebox."""
        from bs4 import BeautifulSoup
        from sports_scraper.scrapers.nba_sportsref import NBASportsReferenceScraper
        scraper = NBASportsReferenceScraper()
        html = '''
        <html>
        <div class="scorebox">
            <div><span>No Link Team</span><div class="score">100</div></div>
            <div><a itemprop="name">Lakers</a><div class="score">95</div></div>
        </div>
        </html>
        '''
        scraper.fetch_html = MagicMock(return_value=BeautifulSoup(html, "lxml"))

        result = scraper.fetch_single_boxscore("202410220BOS", date(2024, 10, 22))
        assert result is None

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_returns_none_when_score_div_missing(self, mock_client, mock_cache):
        """Returns None when score div missing."""
        from bs4 import BeautifulSoup
        from sports_scraper.scrapers.nba_sportsref import NBASportsReferenceScraper
        scraper = NBASportsReferenceScraper()
        html = '''
        <html>
        <div class="scorebox">
            <div><a itemprop="name">Boston Celtics</a></div>
            <div><a itemprop="name">Los Angeles Lakers</a><div class="score">95</div></div>
        </div>
        </html>
        '''
        scraper.fetch_html = MagicMock(return_value=BeautifulSoup(html, "lxml"))

        result = scraper.fetch_single_boxscore("202410220BOS", date(2024, 10, 22))
        assert result is None

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_returns_none_for_invalid_score(self, mock_client, mock_cache):
        """Returns None for non-numeric score value."""
        from bs4 import BeautifulSoup
        from sports_scraper.scrapers.nba_sportsref import NBASportsReferenceScraper
        scraper = NBASportsReferenceScraper()
        html = '''
        <html>
        <div class="scorebox">
            <div><a itemprop="name">Boston Celtics</a><div class="score">N/A</div></div>
            <div><a itemprop="name">Los Angeles Lakers</a><div class="score">95</div></div>
        </div>
        </html>
        '''
        scraper.fetch_html = MagicMock(return_value=BeautifulSoup(html, "lxml"))

        result = scraper.fetch_single_boxscore("202410220BOS", date(2024, 10, 22))
        assert result is None
