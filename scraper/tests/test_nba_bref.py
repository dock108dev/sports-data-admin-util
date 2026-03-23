"""Tests for NBA Basketball Reference scraper and helpers."""

from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRAPER_ROOT = REPO_ROOT / "scraper"
if str(SCRAPER_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRAPER_ROOT))

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://user:pass@localhost:5432/test_db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("ENVIRONMENT", "development")

from bs4 import BeautifulSoup

from sports_scraper.models import TeamIdentity
from sports_scraper.scrapers.nba_bref import NBABasketballReferenceScraper
from sports_scraper.scrapers.nba_bref_helpers import (
    _classify_play,
    _detect_period_from_text,
    _parse_minutes,
    extract_player_stats,
    extract_team_stats,
    parse_pbp_table,
)


# ── Sample HTML fixtures ──


SAMPLE_SCOREBOARD_HTML = """
<html><body>
<div class="game_summary">
  <table class="teams">
    <tr><td><a href="/teams/NYK/2025.html">New York Knicks</a></td><td>109</td></tr>
    <tr><td><a href="/teams/BOS/2025.html">Boston Celtics</a></td><td>132</td></tr>
  </table>
  <p class="links"><a href="/boxscores/202410220BOS.html">Box Score</a></p>
</div>
<div class="game_summary">
  <table class="teams">
    <tr><td><a href="/teams/MIN/2025.html">Minnesota Timberwolves</a></td><td>110</td></tr>
    <tr><td><a href="/teams/LAL/2025.html">Los Angeles Lakers</a></td><td>103</td></tr>
  </table>
  <p class="links"><a href="/boxscores/202410220LAL.html">Box Score</a></p>
</div>
</body></html>
"""


SAMPLE_BOXSCORE_HTML = """
<html><body>
<div class="scorebox">
  <div><strong><a href="/teams/NYK/2025.html" itemprop="name">New York Knicks</a></strong></div>
  <div><strong><a href="/teams/BOS/2025.html" itemprop="name">Boston Celtics</a></strong></div>
</div>
<table id="box-NYK-game-basic">
  <thead><tr><th>Starters</th><th data-stat="mp">MP</th><th data-stat="fg">FG</th><th data-stat="fga">FGA</th><th data-stat="fg_pct">FG%</th><th data-stat="fg3">3P</th><th data-stat="fg3a">3PA</th><th data-stat="fg3_pct">3P%</th><th data-stat="ft">FT</th><th data-stat="fta">FTA</th><th data-stat="ft_pct">FT%</th><th data-stat="orb">ORB</th><th data-stat="drb">DRB</th><th data-stat="trb">TRB</th><th data-stat="ast">AST</th><th data-stat="stl">STL</th><th data-stat="blk">BLK</th><th data-stat="tov">TOV</th><th data-stat="pf">PF</th><th data-stat="pts">PTS</th><th data-stat="plus_minus">+/-</th></tr></thead>
  <tbody>
    <tr><th data-stat="player"><a href="/players/b/bridgmi01.html">Mikal Bridges</a></th><td data-stat="mp">34:37</td><td data-stat="fg">5</td><td data-stat="fga">18</td><td data-stat="fg_pct">.278</td><td data-stat="fg3">2</td><td data-stat="fg3a">8</td><td data-stat="fg3_pct">.250</td><td data-stat="ft">0</td><td data-stat="fta">0</td><td data-stat="ft_pct"></td><td data-stat="orb">0</td><td data-stat="drb">5</td><td data-stat="trb">5</td><td data-stat="ast">3</td><td data-stat="stl">0</td><td data-stat="blk">0</td><td data-stat="tov">1</td><td data-stat="pf">2</td><td data-stat="pts">12</td><td data-stat="plus_minus">-33</td></tr>
    <tr><th data-stat="player"><a href="/players/t/townska01.html">Karl-Anthony Towns</a></th><td data-stat="mp">28:15</td><td data-stat="fg">7</td><td data-stat="fga">12</td><td data-stat="fg_pct">.583</td><td data-stat="fg3">1</td><td data-stat="fg3a">3</td><td data-stat="fg3_pct">.333</td><td data-stat="ft">1</td><td data-stat="fta">1</td><td data-stat="ft_pct">1.000</td><td data-stat="orb">2</td><td data-stat="drb">10</td><td data-stat="trb">12</td><td data-stat="ast">0</td><td data-stat="stl">0</td><td data-stat="blk">3</td><td data-stat="tov">2</td><td data-stat="pf">4</td><td data-stat="pts">16</td><td data-stat="plus_minus">-25</td></tr>
    <tr><th data-stat="player">Did Not Play</th></tr>
  </tbody>
  <tfoot>
    <tr><td data-stat="player">Team Totals</td><td data-stat="mp">240</td><td data-stat="fg">37</td><td data-stat="fga">89</td><td data-stat="fg_pct">.416</td><td data-stat="fg3">12</td><td data-stat="fg3a">37</td><td data-stat="fg3_pct">.324</td><td data-stat="ft">23</td><td data-stat="fta">28</td><td data-stat="ft_pct">.821</td><td data-stat="orb">7</td><td data-stat="drb">30</td><td data-stat="trb">37</td><td data-stat="ast">22</td><td data-stat="stl">5</td><td data-stat="blk">4</td><td data-stat="tov">15</td><td data-stat="pf">20</td><td data-stat="pts">109</td><td data-stat="plus_minus"></td></tr>
  </tfoot>
</table>
<table id="box-BOS-game-basic">
  <thead><tr><th>Starters</th><th data-stat="mp">MP</th><th data-stat="pts">PTS</th><th data-stat="trb">TRB</th><th data-stat="ast">AST</th></tr></thead>
  <tbody>
    <tr><th data-stat="player"><a href="/players/t/tatMDJ01.html">Jayson Tatum</a></th><td data-stat="mp">32:00</td><td data-stat="pts">37</td><td data-stat="trb">10</td><td data-stat="ast">5</td></tr>
  </tbody>
  <tfoot>
    <tr><td data-stat="player">Team Totals</td><td data-stat="mp">240</td><td data-stat="pts">132</td><td data-stat="trb">52</td><td data-stat="ast">30</td></tr>
  </tfoot>
</table>
</body></html>
"""


SAMPLE_PBP_HTML = """
<html><body>
<div id="all_pbp">
<table id="pbp">
  <tbody>
    <tr id="q1"><td colspan="6"><b>1st Quarter</b></td></tr>
    <tr><td>12:00.0</td><td>Jump ball: K. Towns vs. A. Horford</td><td></td><td></td><td></td><td></td></tr>
    <tr><td>11:48.0</td><td></td><td></td><td>2-0</td><td>J. Tatum makes 2-pt shot from 15 ft</td><td></td></tr>
    <tr><td>11:30.0</td><td>M. Bridges misses 3-pt shot from 27 ft</td><td></td><td></td><td></td><td></td></tr>
    <tr><td>11:22.0</td><td></td><td></td><td></td><td>D. White defensive rebound</td><td></td></tr>
    <tr id="q2"><td colspan="6"><b>2nd Quarter</b></td></tr>
    <tr><td>12:00.0</td><td></td><td></td><td>30-25</td><td>J. Brown makes free throw 1 of 2</td><td></td></tr>
  </tbody>
</table>
</div>
</body></html>
"""


# ── Helper tests ──


class TestParseMinutes:
    def test_mm_ss_format(self):
        assert _parse_minutes("36:12") == 36.2

    def test_mm_ss_zero_seconds(self):
        assert _parse_minutes("28:00") == 28.0

    def test_plain_number(self):
        assert _parse_minutes("40") == 40.0

    def test_none(self):
        assert _parse_minutes(None) is None

    def test_empty(self):
        assert _parse_minutes("") is None


class TestClassifyPlay:
    def test_three_pointer(self):
        assert _classify_play("J. Tatum makes 3-pt shot") == "3pt"

    def test_two_pointer(self):
        assert _classify_play("J. Tatum makes 2-pt shot from 15 ft") == "2pt"

    def test_free_throw(self):
        assert _classify_play("J. Brown makes free throw 1 of 2") == "ft"

    def test_miss(self):
        assert _classify_play("M. Bridges misses 3-pt shot") == "miss"

    def test_rebound(self):
        assert _classify_play("D. White defensive rebound") == "rebound"

    def test_turnover(self):
        assert _classify_play("K. Towns bad pass turnover") == "turnover"

    def test_foul(self):
        assert _classify_play("M. Bridges personal foul") == "foul"

    def test_substitution(self):
        assert _classify_play("J. Sims enters the game for K. Towns") == "substitution"

    def test_timeout(self):
        assert _classify_play("Boston timeout") == "timeout"

    def test_unknown(self):
        assert _classify_play("some other play") is None


class TestDetectPeriodFromText:
    def test_first_quarter(self):
        assert _detect_period_from_text("1st Quarter") == 1

    def test_fourth_quarter(self):
        assert _detect_period_from_text("4th quarter") == 4

    def test_overtime(self):
        assert _detect_period_from_text("Overtime") == 5

    def test_second_overtime(self):
        assert _detect_period_from_text("2nd Overtime") == 6

    def test_unrelated(self):
        assert _detect_period_from_text("something else") is None


# ── Team stats extraction ──


class TestExtractTeamStats:
    def test_extract_from_tfoot(self):
        soup = BeautifulSoup(SAMPLE_BOXSCORE_HTML, "lxml")
        stats = extract_team_stats(soup, "NYK")
        assert stats["fg"] == 37
        assert stats["fga"] == 89
        assert stats["pts"] == 109
        assert stats["trb"] == 37
        assert stats["ast"] == 22

    def test_missing_table(self):
        soup = BeautifulSoup("<html></html>", "lxml")
        stats = extract_team_stats(soup, "XYZ")
        assert stats == {}


# ── Player stats extraction ──


class TestExtractPlayerStats:
    def test_extract_players(self):
        soup = BeautifulSoup(SAMPLE_BOXSCORE_HTML, "lxml")
        team = TeamIdentity(league_code="NBA", name="New York Knicks", abbreviation="NYK")
        players = extract_player_stats(soup, "NYK", team)
        assert len(players) == 2  # Bridges + Towns (DNP row skipped)

        bridges = players[0]
        assert bridges.player_name == "Mikal Bridges"
        assert bridges.player_id == "bridgmi01"
        assert bridges.points == 12
        assert bridges.rebounds == 5
        assert bridges.assists == 3
        assert bridges.minutes == 34.6  # 34:37 → 34.6

        towns = players[1]
        assert towns.player_name == "Karl-Anthony Towns"
        assert towns.points == 16
        assert towns.rebounds == 12

    def test_missing_table(self):
        soup = BeautifulSoup("<html></html>", "lxml")
        team = TeamIdentity(league_code="NBA", name="Test", abbreviation="TST")
        players = extract_player_stats(soup, "TST", team)
        assert players == []

    def test_bos_players(self):
        soup = BeautifulSoup(SAMPLE_BOXSCORE_HTML, "lxml")
        team = TeamIdentity(league_code="NBA", name="Boston Celtics", abbreviation="BOS")
        players = extract_player_stats(soup, "BOS", team)
        assert len(players) == 1
        assert players[0].player_name == "Jayson Tatum"
        assert players[0].points == 37


# ── PBP parsing ──


class TestParsePbpTable:
    def test_parse_plays(self):
        soup = BeautifulSoup(SAMPLE_PBP_HTML, "lxml")
        plays = parse_pbp_table(soup)
        assert len(plays) >= 4  # At least the non-header rows

        # First play should be jump ball (Q1)
        assert plays[0].quarter == 1
        assert plays[0].game_clock == "12:00"
        assert "jump ball" in plays[0].description.lower()

        # Second play — Tatum 2pt
        tatum_play = plays[1]
        assert tatum_play.quarter == 1
        assert tatum_play.game_clock == "11:48"
        assert tatum_play.play_type == "2pt"
        assert tatum_play.home_score == 0  # Score is away-home: 2-0
        assert tatum_play.away_score == 2

    def test_period_changes(self):
        soup = BeautifulSoup(SAMPLE_PBP_HTML, "lxml")
        plays = parse_pbp_table(soup)
        # Last play should be in Q2
        q2_plays = [p for p in plays if p.quarter == 2]
        assert len(q2_plays) >= 1
        assert q2_plays[0].play_type == "ft"

    def test_empty_page(self):
        soup = BeautifulSoup("<html></html>", "lxml")
        plays = parse_pbp_table(soup)
        assert plays == []

    def test_play_index_ordering(self):
        soup = BeautifulSoup(SAMPLE_PBP_HTML, "lxml")
        plays = parse_pbp_table(soup)
        indices = [p.play_index for p in plays]
        # Q1 plays should be 10000+, Q2 should be 20000+
        q1_indices = [i for i in indices if 10000 <= i < 20000]
        q2_indices = [i for i in indices if 20000 <= i < 30000]
        assert len(q1_indices) >= 1
        assert len(q2_indices) >= 1


# ── Scraper class tests ──


class TestNBABasketballReferenceScraper:
    def test_scoreboard_url(self):
        scraper = NBABasketballReferenceScraper()
        url = scraper.scoreboard_url(date(2024, 10, 22))
        assert url == "https://www.basketball-reference.com/boxscores/?month=10&day=22&year=2024"

    def test_pbp_url(self):
        scraper = NBABasketballReferenceScraper()
        url = scraper.pbp_url("202410220BOS")
        assert url == "https://www.basketball-reference.com/boxscores/pbp/202410220BOS.html"

    def test_parse_team_row(self):
        html = '<tr><td><a href="/teams/BOS/2025.html">Boston Celtics</a></td><td>132</td></tr>'
        row = BeautifulSoup(html, "lxml").find("tr")
        scraper = NBABasketballReferenceScraper()
        identity, score = scraper._parse_team_row(row)
        assert identity.name == "Boston Celtics"
        assert identity.abbreviation == "BOS"
        assert score == 132

    def test_parse_team_row_missing_link(self):
        html = "<tr><td>No Team</td><td>100</td></tr>"
        row = BeautifulSoup(html, "lxml").find("tr")
        scraper = NBABasketballReferenceScraper()
        try:
            scraper._parse_team_row(row)
            assert False, "Should have raised ScraperError"
        except Exception:
            pass

    def test_unwrap_commented_tables(self):
        html = """
        <html><body>
        <!-- <table id="box-BOS-game-basic"><tbody><tr><th data-stat="player"><a href="/p/test.html">Test Player</a></th></tr></tbody></table> -->
        </body></html>
        """
        soup = BeautifulSoup(html, "lxml")
        scraper = NBABasketballReferenceScraper()
        scraper._unwrap_commented_tables(soup)
        table = soup.find("table", id="box-BOS-game-basic")
        assert table is not None

    @patch.object(NBABasketballReferenceScraper, "fetch_html")
    def test_fetch_games_for_date(self, mock_fetch):
        """Test full game parsing with mocked HTML."""
        scoreboard_soup = BeautifulSoup(SAMPLE_SCOREBOARD_HTML, "lxml")
        boxscore_soup = BeautifulSoup(SAMPLE_BOXSCORE_HTML, "lxml")

        # First call is scoreboard, second is boxscore for game 1, third for game 2
        mock_fetch.side_effect = [scoreboard_soup, boxscore_soup, boxscore_soup]

        scraper = NBABasketballReferenceScraper()
        games = scraper.fetch_games_for_date(date(2024, 10, 22))

        assert len(games) == 2

        game1 = games[0]
        assert game1.identity.source_game_key == "202410220BOS"
        assert game1.home_score == 132
        assert game1.away_score == 109
        assert game1.identity.home_team.abbreviation == "BOS"
        assert game1.identity.away_team.abbreviation == "NYK"
        assert len(game1.team_boxscores) == 2
        assert len(game1.player_boxscores) >= 2

    def test_parse_scorebox_abbreviations(self):
        soup = BeautifulSoup(SAMPLE_BOXSCORE_HTML, "lxml")
        scraper = NBABasketballReferenceScraper()
        away, home = scraper._parse_scorebox_abbreviations(soup)
        assert away == "NYK"
        assert home == "BOS"
