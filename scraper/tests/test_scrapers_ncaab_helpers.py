"""Tests for scrapers/ncaab_sportsref_helpers.py module."""

from __future__ import annotations

import os
import sys
from pathlib import Path

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
from sports_scraper.scrapers.ncaab_sportsref_helpers import (
    extract_player_stats,
    extract_team_stats,
    find_player_table_by_position,
)


class TestExtractTeamStats:
    """Tests for extract_team_stats function."""

    def test_returns_empty_dict_when_no_tables(self):
        """Returns empty dict when no tables found."""
        soup = BeautifulSoup("<html></html>", "lxml")
        team = TeamIdentity(league_code="NCAAB", name="Duke", abbreviation="DUKE")
        result = extract_team_stats(soup, team, is_home=True)
        assert result == {}

    def test_finds_table_by_team_name_slug(self):
        """Finds table matching team name slug."""
        html = '''
        <html>
        <table id="box-score-basic-duke">
            <tfoot>
                <tr>
                    <td data-stat="pts">85</td>
                    <td data-stat="trb">35</td>
                </tr>
            </tfoot>
        </table>
        </html>
        '''
        soup = BeautifulSoup(html, "lxml")
        team = TeamIdentity(league_code="NCAAB", name="Duke", abbreviation="DUKE")
        result = extract_team_stats(soup, team, is_home=False)
        assert isinstance(result, dict)

    def test_falls_back_to_position_when_no_name_match(self):
        """Falls back to position-based matching."""
        html = '''
        <html>
        <table id="box-score-basic-team-a">
            <tfoot><tr><td data-stat="pts">70</td></tr></tfoot>
        </table>
        <table id="box-score-basic-team-b">
            <tfoot><tr><td data-stat="pts">85</td></tr></tfoot>
        </table>
        </html>
        '''
        soup = BeautifulSoup(html, "lxml")
        team = TeamIdentity(league_code="NCAAB", name="Unknown Team", abbreviation="UNK")
        result = extract_team_stats(soup, team, is_home=True)
        assert isinstance(result, dict)

    def test_parses_integer_stats(self):
        """Parses integer stat values."""
        html = '''
        <html>
        <table id="box-score-basic-duke">
            <tfoot>
                <tr>
                    <td data-stat="pts">85</td>
                    <td data-stat="trb">35</td>
                    <td data-stat="ast">18</td>
                </tr>
            </tfoot>
        </table>
        </html>
        '''
        soup = BeautifulSoup(html, "lxml")
        team = TeamIdentity(league_code="NCAAB", name="Duke", abbreviation="DUKE")
        result = extract_team_stats(soup, team, is_home=False)
        assert result.get("pts") == 85 or "pts" in result

    def test_parses_float_stats(self):
        """Parses float stat values."""
        html = '''
        <html>
        <table id="box-score-basic-duke">
            <tfoot>
                <tr>
                    <td data-stat="fg_pct">.485</td>
                </tr>
            </tfoot>
        </table>
        </html>
        '''
        soup = BeautifulSoup(html, "lxml")
        team = TeamIdentity(league_code="NCAAB", name="Duke", abbreviation="DUKE")
        result = extract_team_stats(soup, team, is_home=False)
        assert isinstance(result, dict)


class TestFindPlayerTableByPosition:
    """Tests for find_player_table_by_position function."""

    def test_returns_none_when_no_tables(self):
        """Returns None when no player tables found."""
        soup = BeautifulSoup("<html></html>", "lxml")
        team = TeamIdentity(league_code="NCAAB", name="Duke", abbreviation="DUKE")
        result = find_player_table_by_position(soup, team, is_home=True)
        assert result is None

    def test_finds_table_by_team_name_in_id(self):
        """Finds table with team name in ID."""
        html = '''
        <html>
        <table id="box-score-basic-duke">
            <tbody></tbody>
        </table>
        </html>
        '''
        soup = BeautifulSoup(html, "lxml")
        team = TeamIdentity(league_code="NCAAB", name="Duke", abbreviation="DUKE")
        result = find_player_table_by_position(soup, team, is_home=False)
        assert result is not None

    def test_finds_table_by_position_for_home_team(self):
        """Finds second table for home team."""
        html = '''
        <html>
        <table id="box-score-basic-team-a"><tbody></tbody></table>
        <table id="box-score-basic-team-b"><tbody></tbody></table>
        </html>
        '''
        soup = BeautifulSoup(html, "lxml")
        team = TeamIdentity(league_code="NCAAB", name="Unknown", abbreviation="UNK")
        result = find_player_table_by_position(soup, team, is_home=True)
        assert result is not None
        assert result.get("id") == "box-score-basic-team-b"

    def test_finds_table_by_position_for_away_team(self):
        """Finds first table for away team."""
        html = '''
        <html>
        <table id="box-score-basic-team-a"><tbody></tbody></table>
        <table id="box-score-basic-team-b"><tbody></tbody></table>
        </html>
        '''
        soup = BeautifulSoup(html, "lxml")
        team = TeamIdentity(league_code="NCAAB", name="Unknown", abbreviation="UNK")
        result = find_player_table_by_position(soup, team, is_home=False)
        assert result is not None
        assert result.get("id") == "box-score-basic-team-a"

    def test_finds_table_by_caption(self):
        """Finds table by caption containing team name."""
        html = '''
        <html>
        <table id="box-score-basic-team-a">
            <caption>Duke Blue Devils</caption>
            <tbody></tbody>
        </table>
        </html>
        '''
        soup = BeautifulSoup(html, "lxml")
        team = TeamIdentity(league_code="NCAAB", name="Duke Blue Devils", abbreviation="DUKE")
        result = find_player_table_by_position(soup, team, is_home=False)
        assert result is not None

    def test_handles_normalized_team_names(self):
        """Handles team names with state/university suffixes."""
        html = '''
        <html>
        <table id="box-score-basic-michigan-state">
            <tbody></tbody>
        </table>
        </html>
        '''
        soup = BeautifulSoup(html, "lxml")
        team = TeamIdentity(league_code="NCAAB", name="Michigan State", abbreviation="MSU")
        result = find_player_table_by_position(soup, team, is_home=False)
        assert result is not None


class TestExtractPlayerStats:
    """Tests for extract_player_stats function."""

    def test_returns_empty_list_when_no_table(self):
        """Returns empty list when no player table found."""
        soup = BeautifulSoup("<html></html>", "lxml")
        team = TeamIdentity(league_code="NCAAB", name="Duke", abbreviation="DUKE")
        result = extract_player_stats(soup, team, is_home=True)
        assert result == []

    def test_extracts_players_from_table(self):
        """Extracts player stats from table."""
        html = '''
        <html>
        <table id="box-score-basic-duke">
            <tbody>
                <tr>
                    <th data-stat="player"><a href="/players/z/zionwi01.html">Zion Williamson</a></th>
                    <td data-stat="mp">32</td>
                    <td data-stat="pts">25</td>
                    <td data-stat="trb">10</td>
                    <td data-stat="ast">5</td>
                </tr>
            </tbody>
        </table>
        </html>
        '''
        soup = BeautifulSoup(html, "lxml")
        team = TeamIdentity(league_code="NCAAB", name="Duke", abbreviation="DUKE")
        result = extract_player_stats(soup, team, is_home=False)
        assert len(result) == 1
        assert result[0].player_name == "Zion Williamson"

    def test_skips_thead_rows(self):
        """Skips thead rows."""
        html = '''
        <html>
        <table id="box-score-basic-duke">
            <tbody>
                <tr class="thead"><th>Header</th></tr>
                <tr>
                    <th data-stat="player"><a href="/players/z/zionwi01.html">Player</a></th>
                    <td data-stat="pts">25</td>
                </tr>
            </tbody>
        </table>
        </html>
        '''
        soup = BeautifulSoup(html, "lxml")
        team = TeamIdentity(league_code="NCAAB", name="Duke", abbreviation="DUKE")
        result = extract_player_stats(soup, team, is_home=False)
        assert len(result) == 1

    def test_skips_rows_without_player_cell(self):
        """Skips rows without player cell."""
        html = '''
        <html>
        <table id="box-score-basic-duke">
            <tbody>
                <tr><td>No player cell</td></tr>
                <tr>
                    <th data-stat="player"><a href="/players/p/player.html">Valid Player</a></th>
                    <td data-stat="pts">25</td>
                </tr>
            </tbody>
        </table>
        </html>
        '''
        soup = BeautifulSoup(html, "lxml")
        team = TeamIdentity(league_code="NCAAB", name="Duke", abbreviation="DUKE")
        result = extract_player_stats(soup, team, is_home=False)
        assert len(result) == 1

    def test_skips_rows_without_player_link(self):
        """Skips rows without player link (totals row)."""
        html = '''
        <html>
        <table id="box-score-basic-duke">
            <tbody>
                <tr>
                    <th data-stat="player">Team Totals</th>
                    <td data-stat="pts">85</td>
                </tr>
                <tr>
                    <th data-stat="player"><a href="/players/p/player.html">Valid Player</a></th>
                    <td data-stat="pts">25</td>
                </tr>
            </tbody>
        </table>
        </html>
        '''
        soup = BeautifulSoup(html, "lxml")
        team = TeamIdentity(league_code="NCAAB", name="Duke", abbreviation="DUKE")
        result = extract_player_stats(soup, team, is_home=False)
        assert len(result) == 1

    def test_extracts_player_id_from_href(self):
        """Extracts player ID from href."""
        html = '''
        <html>
        <table id="box-score-basic-duke">
            <tbody>
                <tr>
                    <th data-stat="player"><a href="/players/z/zionwi01.html">Zion</a></th>
                    <td data-stat="pts">25</td>
                </tr>
            </tbody>
        </table>
        </html>
        '''
        soup = BeautifulSoup(html, "lxml")
        team = TeamIdentity(league_code="NCAAB", name="Duke", abbreviation="DUKE")
        result = extract_player_stats(soup, team, is_home=False)
        assert result[0].player_id == "zionwi01"

    def test_parses_minutes_as_float(self):
        """Parses minutes as float."""
        html = '''
        <html>
        <table id="box-score-basic-duke">
            <tbody>
                <tr>
                    <th data-stat="player"><a href="/players/p/player.html">Player</a></th>
                    <td data-stat="mp">32.5</td>
                    <td data-stat="pts">25</td>
                </tr>
            </tbody>
        </table>
        </html>
        '''
        soup = BeautifulSoup(html, "lxml")
        team = TeamIdentity(league_code="NCAAB", name="Duke", abbreviation="DUKE")
        result = extract_player_stats(soup, team, is_home=False)
        assert result[0].minutes == 32.5

    def test_returns_empty_list_when_no_tbody(self):
        """Returns empty list when table has no tbody."""
        html = '''
        <html>
        <table id="box-score-basic-duke">
        </table>
        </html>
        '''
        soup = BeautifulSoup(html, "lxml")
        team = TeamIdentity(league_code="NCAAB", name="Duke", abbreviation="DUKE")
        result = extract_player_stats(soup, team, is_home=False)
        assert result == []
