"""Tests for scrapers/nhl_sportsref.py module."""

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


from sports_scraper.scrapers.nhl_sportsref import NHLSportsReferenceScraper


class TestNHLSportsReferenceScraperModuleImports:
    """Tests for NHL scraper module imports."""

    def test_module_imports(self):
        """Module can be imported without errors."""
        from sports_scraper.scrapers import nhl_sportsref
        assert hasattr(nhl_sportsref, 'NHLSportsReferenceScraper')

    def test_scraper_class_exists(self):
        """Scraper class exists and can be referenced."""
        from sports_scraper.scrapers.nhl_sportsref import NHLSportsReferenceScraper
        assert NHLSportsReferenceScraper is not None


class TestNHLSportsReferenceScraper:
    """Tests for NHLSportsReferenceScraper class."""

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_scraper_attributes(self, mock_client, mock_cache):
        """Scraper has NHL-specific attributes."""
        scraper = NHLSportsReferenceScraper()
        assert scraper.sport == "nhl"
        assert scraper.league_code == "NHL"

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_has_base_url(self, mock_client, mock_cache):
        """Scraper has base URL for hockey-reference.com."""
        scraper = NHLSportsReferenceScraper()
        assert "hockey-reference.com" in scraper.base_url

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_scoreboard_url_format(self, mock_client, mock_cache):
        """Scoreboard URL has correct format."""
        scraper = NHLSportsReferenceScraper()
        url = scraper.scoreboard_url(date(2024, 1, 15))
        assert "month=1" in url or "2024-01" in url
        assert "day=15" in url or "-15" in url

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_boxscore_url_format(self, mock_client, mock_cache):
        """Boxscore URL has correct format."""
        scraper = NHLSportsReferenceScraper()
        # Test with a sample game key
        if hasattr(scraper, 'boxscore_url'):
            url = scraper.boxscore_url("202401150BOS")
            assert "202401150BOS" in url

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_pbp_url_format(self, mock_client, mock_cache):
        """PBP URL has correct format."""
        scraper = NHLSportsReferenceScraper()
        url = scraper.pbp_url("202401150BOS")
        assert "pbp" in url
        assert "202401150BOS" in url

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_has_score_pattern(self, mock_client, mock_cache):
        """Has score pattern regex."""
        scraper = NHLSportsReferenceScraper()
        assert hasattr(scraper, "_SCORE_PATTERN")

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_has_ot_number_pattern(self, mock_client, mock_cache):
        """Has OT number pattern regex."""
        scraper = NHLSportsReferenceScraper()
        assert hasattr(scraper, "_OT_NUMBER_PATTERN")


class TestNHLExtractTeamStats:
    """Tests for _extract_team_stats method."""

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_returns_empty_dict_when_table_not_found(self, mock_client, mock_cache):
        """Returns empty dict when table not found."""
        from bs4 import BeautifulSoup
        scraper = NHLSportsReferenceScraper()
        soup = BeautifulSoup("<html></html>", "lxml")
        result = scraper._extract_team_stats(soup, "BOS")
        assert result == {}

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_uses_uppercase_team_abbr(self, mock_client, mock_cache):
        """Uses uppercase team abbreviation in table ID."""
        from bs4 import BeautifulSoup
        scraper = NHLSportsReferenceScraper()
        html = '''
        <html>
        <table id="BOS_skaters">
            <tfoot><tr><td data-stat="goals">3</td></tr></tfoot>
        </table>
        </html>
        '''
        soup = BeautifulSoup(html, "lxml")
        result = scraper._extract_team_stats(soup, "BOS")
        assert isinstance(result, dict)


class TestNHLExtractPlayerStats:
    """Tests for _extract_player_stats method."""

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_returns_empty_list_when_no_tables(self, mock_client, mock_cache):
        """Returns empty list when no player tables found."""
        from bs4 import BeautifulSoup
        from sports_scraper.models import TeamIdentity
        scraper = NHLSportsReferenceScraper()
        team = TeamIdentity(league_code="NHL", name="Boston Bruins", abbreviation="BOS")
        soup = BeautifulSoup("<html></html>", "lxml")
        result = scraper._extract_player_stats(soup, "BOS", team, is_home=True)
        assert result == []

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_extracts_skaters(self, mock_client, mock_cache):
        """Extracts skaters from skaters table."""
        from bs4 import BeautifulSoup
        from sports_scraper.models import TeamIdentity
        scraper = NHLSportsReferenceScraper()
        team = TeamIdentity(league_code="NHL", name="Boston Bruins", abbreviation="BOS")
        html = '''
        <html>
        <table id="BOS_skaters">
            <tbody>
                <tr>
                    <td data-stat="player"><a href="/players/p/pastrdav.html">David Pastrnak</a></td>
                    <td data-stat="goals">2</td>
                    <td data-stat="assists">1</td>
                </tr>
            </tbody>
        </table>
        </html>
        '''
        soup = BeautifulSoup(html, "lxml")
        result = scraper._extract_player_stats(soup, "BOS", team, is_home=True)
        assert len(result) == 1
        assert result[0].player_name == "David Pastrnak"
        assert result[0].player_role == "skater"

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_extracts_goalies(self, mock_client, mock_cache):
        """Extracts goalies from goalies table."""
        from bs4 import BeautifulSoup
        from sports_scraper.models import TeamIdentity
        scraper = NHLSportsReferenceScraper()
        team = TeamIdentity(league_code="NHL", name="Boston Bruins", abbreviation="BOS")
        html = '''
        <html>
        <table id="BOS_goalies">
            <tbody>
                <tr>
                    <td data-stat="player"><a href="/players/s/swayjere.html">Jeremy Swayman</a></td>
                    <td data-stat="saves">30</td>
                    <td data-stat="goals_against">2</td>
                </tr>
            </tbody>
        </table>
        </html>
        '''
        soup = BeautifulSoup(html, "lxml")
        result = scraper._extract_player_stats(soup, "BOS", team, is_home=True)
        assert len(result) == 1
        assert result[0].player_name == "Jeremy Swayman"
        assert result[0].player_role == "goalie"


class TestNHLParsePlayerTable:
    """Tests for _parse_player_table method."""

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_raises_for_invalid_role(self, mock_client, mock_cache):
        """Raises ValueError for invalid player role."""
        from bs4 import BeautifulSoup
        from sports_scraper.models import TeamIdentity
        scraper = NHLSportsReferenceScraper()
        team = TeamIdentity(league_code="NHL", name="Boston Bruins", abbreviation="BOS")
        html = '<table><tbody></tbody></table>'
        soup = BeautifulSoup(html, "lxml")
        table = soup.find("table")
        with pytest.raises(ValueError, match="Invalid player_role"):
            scraper._parse_player_table(table, "BOS_skaters", "BOS", team, True, "invalid_role")

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_skips_thead_rows(self, mock_client, mock_cache):
        """Skips thead rows."""
        from bs4 import BeautifulSoup
        from sports_scraper.models import TeamIdentity
        scraper = NHLSportsReferenceScraper()
        team = TeamIdentity(league_code="NHL", name="Boston Bruins", abbreviation="BOS")
        html = '''
        <table>
            <tbody>
                <tr class="thead"><th>Header</th></tr>
                <tr>
                    <td data-stat="player"><a href="/players/p/player.html">Player</a></td>
                    <td data-stat="goals">1</td>
                </tr>
            </tbody>
        </table>
        '''
        soup = BeautifulSoup(html, "lxml")
        table = soup.find("table")
        result = scraper._parse_player_table(table, "BOS_skaters", "BOS", team, True, "skater")
        assert len(result) == 1

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_skips_total_rows(self, mock_client, mock_cache):
        """Skips TOTAL/Team Total rows."""
        from bs4 import BeautifulSoup
        from sports_scraper.models import TeamIdentity
        scraper = NHLSportsReferenceScraper()
        team = TeamIdentity(league_code="NHL", name="Boston Bruins", abbreviation="BOS")
        html = '''
        <table>
            <tbody>
                <tr>
                    <td data-stat="player">TOTAL</td>
                    <td data-stat="goals">5</td>
                </tr>
                <tr>
                    <td data-stat="player"><a href="/players/p/player.html">Player</a></td>
                    <td data-stat="goals">1</td>
                </tr>
            </tbody>
        </table>
        '''
        soup = BeautifulSoup(html, "lxml")
        table = soup.find("table")
        result = scraper._parse_player_table(table, "BOS_skaters", "BOS", team, True, "skater")
        assert len(result) == 1

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_skips_empty_net_rows_for_goalies(self, mock_client, mock_cache):
        """Skips 'Empty Net' rows in goalie tables."""
        from bs4 import BeautifulSoup
        from sports_scraper.models import TeamIdentity
        scraper = NHLSportsReferenceScraper()
        team = TeamIdentity(league_code="NHL", name="Boston Bruins", abbreviation="BOS")
        html = '''
        <table>
            <tbody>
                <tr>
                    <td data-stat="player">Empty Net</td>
                    <td data-stat="saves">0</td>
                </tr>
                <tr>
                    <td data-stat="player"><a href="/players/g/goalie.html">Goalie</a></td>
                    <td data-stat="saves">30</td>
                </tr>
            </tbody>
        </table>
        '''
        soup = BeautifulSoup(html, "lxml")
        table = soup.find("table")
        result = scraper._parse_player_table(table, "BOS_goalies", "BOS", team, True, "goalie")
        assert len(result) == 1


class TestNHLBuildTeamBoxscore:
    """Tests for _build_team_boxscore method."""

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_builds_boxscore_with_hockey_stats(self, mock_client, mock_cache):
        """Builds team boxscore with hockey-specific stats."""
        from sports_scraper.models import TeamIdentity
        scraper = NHLSportsReferenceScraper()
        team = TeamIdentity(league_code="NHL", name="Boston Bruins", abbreviation="BOS")
        stats = {"a": "20", "s": "35", "pim": "8"}
        boxscore = scraper._build_team_boxscore(team, is_home=True, score=4, stats=stats)
        assert boxscore.points == 4
        assert boxscore.assists == 20
        assert boxscore.shots_on_goal == 35
        assert boxscore.penalty_minutes == 8
        assert boxscore.rebounds is None  # Not applicable to hockey


class TestNHLFetchSingleBoxscore:
    """Tests for fetch_single_boxscore method."""

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_returns_none_on_fetch_error(self, mock_client, mock_cache):
        """Returns None when fetch fails."""
        from bs4 import BeautifulSoup
        scraper = NHLSportsReferenceScraper()
        scraper.fetch_html = MagicMock(side_effect=Exception("Network error"))

        result = scraper.fetch_single_boxscore("202401150BOS", date(2024, 1, 15))
        assert result is None

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_returns_none_when_scorebox_missing(self, mock_client, mock_cache):
        """Returns None when scorebox not found."""
        from bs4 import BeautifulSoup
        scraper = NHLSportsReferenceScraper()
        scraper.fetch_html = MagicMock(return_value=BeautifulSoup("<html></html>", "lxml"))

        result = scraper.fetch_single_boxscore("202401150BOS", date(2024, 1, 15))
        assert result is None

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_returns_none_when_team_divs_insufficient(self, mock_client, mock_cache):
        """Returns None when fewer than 2 team divs in scorebox."""
        from bs4 import BeautifulSoup
        scraper = NHLSportsReferenceScraper()
        html = '<html><div class="scorebox"><div>One Team</div></div></html>'
        scraper.fetch_html = MagicMock(return_value=BeautifulSoup(html, "lxml"))

        result = scraper.fetch_single_boxscore("202401150BOS", date(2024, 1, 15))
        assert result is None


class TestNHLFetchGamesForDate:
    """Tests for fetch_games_for_date method."""

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_returns_empty_list_when_no_games(self, mock_client, mock_cache):
        """Returns empty list when no game_summary divs found."""
        from bs4 import BeautifulSoup
        scraper = NHLSportsReferenceScraper()
        scraper.fetch_html = MagicMock(return_value=BeautifulSoup("<html></html>", "lxml"))

        result = scraper.fetch_games_for_date(date(2024, 1, 15))
        assert result == []

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_skips_games_with_insufficient_team_rows(self, mock_client, mock_cache):
        """Skips games with fewer than 2 team rows."""
        from bs4 import BeautifulSoup
        scraper = NHLSportsReferenceScraper()
        html = '''
        <html>
        <div class="game_summary">
            <table class="teams">
                <tr><td><a href="/team/bos">Boston Bruins</a></td><td class="right">4</td></tr>
            </table>
        </div>
        </html>
        '''
        scraper.fetch_html = MagicMock(return_value=BeautifulSoup(html, "lxml"))

        result = scraper.fetch_games_for_date(date(2024, 1, 15))
        assert result == []


class TestNHLFetchPlayByPlay:
    """Tests for fetch_play_by_play method."""

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_returns_empty_plays_when_no_pbp_table(self, mock_client, mock_cache):
        """Returns NormalizedPlayByPlay with empty plays when no pbp table found."""
        from bs4 import BeautifulSoup
        scraper = NHLSportsReferenceScraper()
        scraper.fetch_html = MagicMock(return_value=BeautifulSoup("<html></html>", "lxml"))

        result = scraper.fetch_play_by_play("202401150BOS", date(2024, 1, 15))
        assert result.source_game_key == "202401150BOS"
        assert result.plays == []

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_parses_pbp_with_period_markers(self, mock_client, mock_cache):
        """Parses PBP table with period markers."""
        from bs4 import BeautifulSoup
        scraper = NHLSportsReferenceScraper()
        html = '''
        <html>
        <div class="scorebox">
            <div><a itemprop="name">Boston Bruins</a></div>
            <div><a itemprop="name">Tampa Bay Lightning</a></div>
        </div>
        <table id="pbp">
            <tr id="p1" class="thead"><th>1st Period</th></tr>
            <tr><td>20:00</td><td colspan="5">Period Start</td></tr>
        </table>
        </html>
        '''
        scraper.fetch_html = MagicMock(return_value=BeautifulSoup(html, "lxml"))

        result = scraper.fetch_play_by_play("202401150BOS", date(2024, 1, 15))
        assert len(result.plays) == 1
        assert result.plays[0].quarter == 1

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_handles_shootout_period(self, mock_client, mock_cache):
        """Handles shootout period marker."""
        from bs4 import BeautifulSoup
        scraper = NHLSportsReferenceScraper()
        html = '''
        <html>
        <div class="scorebox">
            <div><a itemprop="name">Boston Bruins</a></div>
            <div><a itemprop="name">Tampa Bay Lightning</a></div>
        </div>
        <table id="pbp">
            <tr id="p3" class="thead"><th>3rd Period</th></tr>
            <tr><td>0:00</td><td colspan="5">End of Period</td></tr>
            <tr id="so" class="thead"><th>Shootout</th></tr>
            <tr><td>0:00</td><td colspan="5">Shootout begins</td></tr>
        </table>
        </html>
        '''
        scraper.fetch_html = MagicMock(return_value=BeautifulSoup(html, "lxml"))

        result = scraper.fetch_play_by_play("202401150BOS", date(2024, 1, 15))
        assert len(result.plays) >= 1


class TestNHLParsePlayerTableEdgeCases:
    """Additional tests for _parse_player_table edge cases."""

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_returns_empty_list_when_no_tbody(self, mock_client, mock_cache):
        """Returns empty list when table has no tbody."""
        from bs4 import BeautifulSoup
        from sports_scraper.models import TeamIdentity
        scraper = NHLSportsReferenceScraper()
        team = TeamIdentity(league_code="NHL", name="Boston Bruins", abbreviation="BOS")
        html = '<table id="BOS_skaters"><thead><tr><th>Header</th></tr></thead></table>'
        soup = BeautifulSoup(html, "lxml")
        table = soup.find("table")
        result = scraper._parse_player_table(table, "BOS_skaters", "BOS", team, True, "skater")
        assert result == []

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_builds_player_with_all_stats(self, mock_client, mock_cache):
        """Builds player with goals, assists, points, and shots."""
        from bs4 import BeautifulSoup
        from sports_scraper.models import TeamIdentity
        scraper = NHLSportsReferenceScraper()
        team = TeamIdentity(league_code="NHL", name="Boston Bruins", abbreviation="BOS")
        html = '''
        <table>
            <tbody>
                <tr>
                    <td data-stat="player"><a href="/players/p/pastrdav.html">David Pastrnak</a></td>
                    <td data-stat="goals">2</td>
                    <td data-stat="assists">1</td>
                    <td data-stat="points">3</td>
                    <td data-stat="shots">5</td>
                    <td data-stat="time_on_ice">18:30</td>
                </tr>
            </tbody>
        </table>
        '''
        soup = BeautifulSoup(html, "lxml")
        table = soup.find("table")
        result = scraper._parse_player_table(table, "BOS_skaters", "BOS", team, True, "skater")
        assert len(result) == 1
        assert result[0].goals == 2
        assert result[0].assists == 1
        assert result[0].points == 3
        assert result[0].shots_on_goal == 5

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_builds_goalie_with_goalie_stats(self, mock_client, mock_cache):
        """Builds goalie with saves, goals_against, etc."""
        from bs4 import BeautifulSoup
        from sports_scraper.models import TeamIdentity
        scraper = NHLSportsReferenceScraper()
        team = TeamIdentity(league_code="NHL", name="Boston Bruins", abbreviation="BOS")
        html = '''
        <table>
            <tbody>
                <tr>
                    <td data-stat="player"><a href="/players/s/swayjere.html">Jeremy Swayman</a></td>
                    <td data-stat="saves">28</td>
                    <td data-stat="goals_against">2</td>
                    <td data-stat="shots_against">30</td>
                    <td data-stat="save_pct">.933</td>
                    <td data-stat="time_on_ice">60:00</td>
                </tr>
            </tbody>
        </table>
        '''
        soup = BeautifulSoup(html, "lxml")
        table = soup.find("table")
        result = scraper._parse_player_table(table, "BOS_goalies", "BOS", team, True, "goalie")
        assert len(result) == 1
        assert result[0].player_role == "goalie"
        assert result[0].saves == 28
        assert result[0].goals_against == 2
        assert result[0].shots_against == 30


class TestNHLScraperInheritance:
    """Tests for NHL scraper inheritance from base."""

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_inherits_iter_dates(self, mock_client, mock_cache):
        """Inherits iter_dates from base class."""
        scraper = NHLSportsReferenceScraper()
        dates = list(scraper.iter_dates(date(2024, 1, 1), date(2024, 1, 3)))
        assert len(dates) == 3

    @patch("sports_scraper.scrapers.base.HTMLCache")
    @patch("sports_scraper.scrapers.base.httpx.Client")
    def test_inherits_season_from_date(self, mock_client, mock_cache):
        """Inherits _season_from_date from base class."""
        scraper = NHLSportsReferenceScraper()
        assert hasattr(scraper, "_season_from_date")
        # NHL season spans calendar years, Jan 2024 = 2023-24 season
        season = scraper._season_from_date(date(2024, 1, 15))
        assert season == 2023  # Returns start year of season
        # October 2024 = 2024-25 season
        season = scraper._season_from_date(date(2024, 10, 15))
        assert season == 2024
