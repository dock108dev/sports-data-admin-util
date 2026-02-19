"""Tests for HTML parsing utility functions."""

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

from sports_scraper.utils.html_parsing import (
    extract_all_stats_from_row,
    extract_team_stats_from_table,
    find_table_by_id,
    get_stat_from_row,
    get_table_ids_on_page,
)

# Sample HTML for testing
SAMPLE_TABLE_HTML = """
<html>
<body>
<table id="box-basic">
    <thead>
        <tr><th>Player</th><th>PTS</th><th>REB</th></tr>
    </thead>
    <tbody>
        <tr>
            <td data-stat="player">John Doe</td>
            <td data-stat="pts">25</td>
            <td data-stat="trb">10</td>
        </tr>
        <tr>
            <td data-stat="player">Jane Smith</td>
            <td data-stat="pts">18</td>
            <td data-stat="trb">5</td>
        </tr>
    </tbody>
    <tfoot>
        <tr>
            <td data-stat="player">Team Total</td>
            <td data-stat="pts">43</td>
            <td data-stat="trb">15</td>
            <td data-stat="ast">8</td>
        </tr>
    </tfoot>
</table>
<table id="box-advanced">
    <tbody>
        <tr>
            <td data-stat="player">Player A</td>
            <td data-stat="ortg">110</td>
        </tr>
    </tbody>
</table>
</body>
</html>
"""


class TestGetStatFromRow:
    """Tests for get_stat_from_row function."""

    def test_get_existing_stat(self):
        soup = BeautifulSoup(SAMPLE_TABLE_HTML, "html.parser")
        row = soup.find("tbody").find("tr")
        result = get_stat_from_row(row, "pts")
        assert result == "25"

    def test_get_stat_different_field(self):
        soup = BeautifulSoup(SAMPLE_TABLE_HTML, "html.parser")
        row = soup.find("tbody").find("tr")
        result = get_stat_from_row(row, "trb")
        assert result == "10"

    def test_get_nonexistent_stat(self):
        soup = BeautifulSoup(SAMPLE_TABLE_HTML, "html.parser")
        row = soup.find("tbody").find("tr")
        result = get_stat_from_row(row, "nonexistent")
        assert result is None

    def test_get_player_name(self):
        soup = BeautifulSoup(SAMPLE_TABLE_HTML, "html.parser")
        row = soup.find("tbody").find("tr")
        result = get_stat_from_row(row, "player")
        assert result == "John Doe"

    def test_empty_cell_returns_none(self):
        html = '<tr><td data-stat="pts"></td></tr>'
        soup = BeautifulSoup(html, "html.parser")
        row = soup.find("tr")
        result = get_stat_from_row(row, "pts")
        assert result is None

    def test_whitespace_only_cell_returns_none(self):
        html = '<tr><td data-stat="pts">   </td></tr>'
        soup = BeautifulSoup(html, "html.parser")
        row = soup.find("tr")
        result = get_stat_from_row(row, "pts")
        assert result is None


class TestExtractAllStatsFromRow:
    """Tests for extract_all_stats_from_row function."""

    def test_extract_all_stats(self):
        soup = BeautifulSoup(SAMPLE_TABLE_HTML, "html.parser")
        row = soup.find("tbody").find("tr")
        result = extract_all_stats_from_row(row)
        assert result["player"] == "John Doe"
        assert result["pts"] == "25"
        assert result["trb"] == "10"

    def test_excludes_empty_values(self):
        html = '<tr><td data-stat="pts">25</td><td data-stat="reb"></td></tr>'
        soup = BeautifulSoup(html, "html.parser")
        row = soup.find("tr")
        result = extract_all_stats_from_row(row)
        assert "pts" in result
        assert "reb" not in result

    def test_multiple_rows(self):
        soup = BeautifulSoup(SAMPLE_TABLE_HTML, "html.parser")
        rows = soup.find("tbody").find_all("tr")
        result1 = extract_all_stats_from_row(rows[0])
        result2 = extract_all_stats_from_row(rows[1])
        assert result1["player"] == "John Doe"
        assert result2["player"] == "Jane Smith"

    def test_row_without_data_stat(self):
        html = '<tr><td>No data-stat</td></tr>'
        soup = BeautifulSoup(html, "html.parser")
        row = soup.find("tr")
        result = extract_all_stats_from_row(row)
        assert result == {}


class TestFindTableById:
    """Tests for find_table_by_id function."""

    def test_find_existing_table(self):
        soup = BeautifulSoup(SAMPLE_TABLE_HTML, "html.parser")
        table = find_table_by_id(soup, "box-basic")
        assert table is not None
        assert table.get("id") == "box-basic"

    def test_find_table_by_alternate_id(self):
        soup = BeautifulSoup(SAMPLE_TABLE_HTML, "html.parser")
        table = find_table_by_id(soup, "nonexistent", alternate_ids=["box-advanced"])
        assert table is not None
        assert table.get("id") == "box-advanced"

    def test_return_none_for_nonexistent_table(self):
        soup = BeautifulSoup(SAMPLE_TABLE_HTML, "html.parser")
        table = find_table_by_id(soup, "nonexistent")
        assert table is None

    def test_return_none_when_no_alternates_match(self):
        soup = BeautifulSoup(SAMPLE_TABLE_HTML, "html.parser")
        table = find_table_by_id(soup, "nonexistent", alternate_ids=["also-nonexistent"])
        assert table is None

    def test_primary_id_takes_precedence(self):
        soup = BeautifulSoup(SAMPLE_TABLE_HTML, "html.parser")
        table = find_table_by_id(soup, "box-basic", alternate_ids=["box-advanced"])
        assert table.get("id") == "box-basic"


class TestExtractTeamStatsFromTable:
    """Tests for extract_team_stats_from_table function."""

    def test_extract_from_tfoot(self):
        soup = BeautifulSoup(SAMPLE_TABLE_HTML, "html.parser")
        table = soup.find("table", id="box-basic")
        result = extract_team_stats_from_table(table, "BOS", "box-basic")
        assert result["pts"] == "43"
        assert result["trb"] == "15"
        assert result["ast"] == "8"

    def test_excludes_player_field(self):
        soup = BeautifulSoup(SAMPLE_TABLE_HTML, "html.parser")
        table = soup.find("table", id="box-basic")
        result = extract_team_stats_from_table(table, "BOS", "box-basic")
        assert "player" not in result

    def test_table_without_tfoot(self):
        html = '<table id="test"><tbody><tr><td data-stat="pts">10</td></tr></tbody></table>'
        soup = BeautifulSoup(html, "html.parser")
        table = soup.find("table")
        result = extract_team_stats_from_table(table, "BOS", "test")
        assert result == {}

    def test_excludes_empty_values(self):
        html = '''
        <table id="test">
            <tfoot>
                <tr>
                    <td data-stat="pts">25</td>
                    <td data-stat="reb"></td>
                </tr>
            </tfoot>
        </table>
        '''
        soup = BeautifulSoup(html, "html.parser")
        table = soup.find("table")
        result = extract_team_stats_from_table(table, "BOS", "test")
        assert "pts" in result
        assert "reb" not in result



class TestGetTableIdsOnPage:
    """Tests for get_table_ids_on_page function."""

    def test_get_all_table_ids(self):
        soup = BeautifulSoup(SAMPLE_TABLE_HTML, "html.parser")
        ids = get_table_ids_on_page(soup)
        assert "box-basic" in ids
        assert "box-advanced" in ids

    def test_limit_results(self):
        soup = BeautifulSoup(SAMPLE_TABLE_HTML, "html.parser")
        ids = get_table_ids_on_page(soup, limit=1)
        assert len(ids) == 1

    def test_table_without_id(self):
        html = '<table><tr><td>No ID</td></tr></table>'
        soup = BeautifulSoup(html, "html.parser")
        ids = get_table_ids_on_page(soup)
        assert "no-id" in ids

    def test_empty_page(self):
        html = '<html><body></body></html>'
        soup = BeautifulSoup(html, "html.parser")
        ids = get_table_ids_on_page(soup)
        assert ids == []
