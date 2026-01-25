"""NHL player parsing regression tests.

These tests ensure that NHL player parsing correctly handles:
- <td data-stat="player"> cells (correct data rows)
- <th data-stat="player"> cells (header rows, should be skipped)
- Skater vs goalie role separation
- Empty Net rows in goalie tables

If these tests fail, it indicates a regression in player parsing logic
that could cause 100% player data loss (the original bug).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# Ensure the scraper package is importable when running from repo root without installing it.
REPO_ROOT = Path(__file__).resolve().parents[2]
SCRAPER_ROOT = REPO_ROOT / "scraper"
if str(SCRAPER_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRAPER_ROOT))

# The scraper settings are loaded at import time and require DATABASE_URL.
# For these pure unit tests, a dummy local URL is sufficient.
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost:5432/test_db")

from bs4 import BeautifulSoup

from sports_scraper.models import TeamIdentity
from sports_scraper.scrapers.nhl_sportsref import NHLSportsReferenceScraper


class StubNHLScraper(NHLSportsReferenceScraper):
    """Test stub that doesn't make network requests."""

    def __init__(self) -> None:
        # Skip parent __init__ to avoid network setup
        self.sport = "nhl"
        self.league_code = "NHL"


# Realistic HTML snippet with <td data-stat="player"> (correct format)
VALID_SKATERS_HTML = """
<table id="BOS_skaters">
  <thead>
    <tr>
      <th data-stat="player">Player</th>
      <th data-stat="goals">G</th>
      <th data-stat="assists">A</th>
      <th data-stat="points">PTS</th>
      <th data-stat="shots">S</th>
      <th data-stat="time_on_ice">TOI</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td data-stat="player"><a href="/players/m/marchabr01.html">Brad Marchand</a></td>
      <td data-stat="goals">1</td>
      <td data-stat="assists">2</td>
      <td data-stat="points">3</td>
      <td data-stat="shots">4</td>
      <td data-stat="time_on_ice">18:45</td>
    </tr>
    <tr>
      <td data-stat="player"><a href="/players/p/pastrda01.html">David Pastrnak</a></td>
      <td data-stat="goals">2</td>
      <td data-stat="assists">1</td>
      <td data-stat="points">3</td>
      <td data-stat="shots">6</td>
      <td data-stat="time_on_ice">20:12</td>
    </tr>
    <tr>
      <td data-stat="player"><a href="/players/b/bergpa01.html">Patrice Bergeron</a></td>
      <td data-stat="goals">0</td>
      <td data-stat="assists">1</td>
      <td data-stat="points">1</td>
      <td data-stat="shots">3</td>
      <td data-stat="time_on_ice">19:30</td>
    </tr>
  </tbody>
</table>
"""

VALID_GOALIES_HTML = """
<table id="BOS_goalies">
  <thead>
    <tr>
      <th data-stat="player">Player</th>
      <th data-stat="saves">SV</th>
      <th data-stat="goals_against">GA</th>
      <th data-stat="shots_against">SA</th>
      <th data-stat="save_pct">SV%</th>
      <th data-stat="time_on_ice">TOI</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td data-stat="player"><a href="/players/s/swaymje01.html">Jeremy Swayman</a></td>
      <td data-stat="saves">28</td>
      <td data-stat="goals_against">2</td>
      <td data-stat="shots_against">30</td>
      <td data-stat="save_pct">.933</td>
      <td data-stat="time_on_ice">58:45</td>
    </tr>
    <tr>
      <td data-stat="player">Empty Net</td>
      <td data-stat="saves"></td>
      <td data-stat="goals_against">1</td>
      <td data-stat="shots_against">1</td>
      <td data-stat="save_pct"></td>
      <td data-stat="time_on_ice">1:15</td>
    </tr>
  </tbody>
</table>
"""

@pytest.fixture
def scraper() -> StubNHLScraper:
    return StubNHLScraper()


@pytest.fixture
def team_identity() -> TeamIdentity:
    return TeamIdentity(
        league_code="NHL",
        name="Boston Bruins",
        short_name="Boston",
        abbreviation="BOS",
        external_ref="BOS",
    )


class TestNHLPlayerCellDetection:
    """Tests for correct HTML cell detection (<td> vs <th>)."""

    def test_td_player_cells_are_parsed(self, scraper: StubNHLScraper, team_identity: TeamIdentity) -> None:
        """CRITICAL: <td data-stat="player"> cells MUST be parsed.

        This is the correct format used by Hockey Reference for player data rows.
        If this test fails, 100% of player data will be lost.
        """
        soup = BeautifulSoup(VALID_SKATERS_HTML, "lxml")
        table = soup.find("table", id="BOS_skaters")

        players = scraper._parse_player_table(
            table=table,
            table_id="BOS_skaters",
            team_abbr="BOS",
            team_identity=team_identity,
            is_home=True,
            player_role="skater",
        )

        # REGRESSION GUARD: Must parse all 3 skaters
        assert len(players) == 3, f"Expected 3 skaters, got {len(players)} - REGRESSION DETECTED"

        # Verify player details
        player_names = [p.player_name for p in players]
        assert "Brad Marchand" in player_names
        assert "David Pastrnak" in player_names
        assert "Patrice Bergeron" in player_names

        # Verify role is set correctly
        for player in players:
            assert player.player_role == "skater", f"Expected role 'skater', got '{player.player_role}'"


class TestNHLSkaterParsing:
    """Tests for skater-specific parsing."""

    def test_skater_count_not_zero(self, scraper: StubNHLScraper, team_identity: TeamIdentity) -> None:
        """REGRESSION GUARD: Parsed skater count must NOT be zero.

        If this test fails, skater data is being silently dropped.
        """
        soup = BeautifulSoup(VALID_SKATERS_HTML, "lxml")
        table = soup.find("table", id="BOS_skaters")

        players = scraper._parse_player_table(
            table=table,
            table_id="BOS_skaters",
            team_abbr="BOS",
            team_identity=team_identity,
            is_home=True,
            player_role="skater",
        )

        skater_count = len(players)
        assert skater_count > 0, "REGRESSION: Zero skaters parsed - check <td> vs <th> selector"

    def test_skater_stats_are_extracted(self, scraper: StubNHLScraper, team_identity: TeamIdentity) -> None:
        """Verify skater-specific stats are extracted correctly."""
        soup = BeautifulSoup(VALID_SKATERS_HTML, "lxml")
        table = soup.find("table", id="BOS_skaters")

        players = scraper._parse_player_table(
            table=table,
            table_id="BOS_skaters",
            team_abbr="BOS",
            team_identity=team_identity,
            is_home=True,
            player_role="skater",
        )

        marchand = next(p for p in players if p.player_name == "Brad Marchand")
        assert marchand.goals == 1
        assert marchand.assists == 2
        assert marchand.points == 3
        assert marchand.shots_on_goal == 4
        assert marchand.minutes is not None  # TOI should be parsed

        # Goalie stats should be None for skaters
        assert marchand.saves is None
        assert marchand.goals_against is None
        assert marchand.shots_against is None


class TestNHLGoalieParsing:
    """Tests for goalie-specific parsing."""

    def test_goalie_count_not_zero(self, scraper: StubNHLScraper, team_identity: TeamIdentity) -> None:
        """REGRESSION GUARD: Parsed goalie count must NOT be zero.

        If this test fails, goalie data is being silently dropped.
        """
        soup = BeautifulSoup(VALID_GOALIES_HTML, "lxml")
        table = soup.find("table", id="BOS_goalies")

        players = scraper._parse_player_table(
            table=table,
            table_id="BOS_goalies",
            team_abbr="BOS",
            team_identity=team_identity,
            is_home=True,
            player_role="goalie",
        )

        # Should parse 1 goalie (Empty Net row should be skipped)
        goalie_count = len(players)
        assert goalie_count > 0, "REGRESSION: Zero goalies parsed - check parsing logic"

    def test_empty_net_row_is_skipped(self, scraper: StubNHLScraper, team_identity: TeamIdentity) -> None:
        """Empty Net rows should be explicitly skipped, not parsed as goalies."""
        soup = BeautifulSoup(VALID_GOALIES_HTML, "lxml")
        table = soup.find("table", id="BOS_goalies")

        players = scraper._parse_player_table(
            table=table,
            table_id="BOS_goalies",
            team_abbr="BOS",
            team_identity=team_identity,
            is_home=True,
            player_role="goalie",
        )

        # Should only have 1 goalie (Swayman), Empty Net should be skipped
        assert len(players) == 1, f"Expected 1 goalie, got {len(players)} - Empty Net may not be skipped"

        goalie_names = [p.player_name for p in players]
        assert "Empty Net" not in goalie_names, "Empty Net row should be skipped"
        assert "Jeremy Swayman" in goalie_names

    def test_goalie_stats_are_extracted(self, scraper: StubNHLScraper, team_identity: TeamIdentity) -> None:
        """Verify goalie-specific stats are extracted correctly."""
        soup = BeautifulSoup(VALID_GOALIES_HTML, "lxml")
        table = soup.find("table", id="BOS_goalies")

        players = scraper._parse_player_table(
            table=table,
            table_id="BOS_goalies",
            team_abbr="BOS",
            team_identity=team_identity,
            is_home=True,
            player_role="goalie",
        )

        swayman = players[0]
        assert swayman.player_name == "Jeremy Swayman"
        assert swayman.player_role == "goalie"
        assert swayman.saves == 28
        assert swayman.goals_against == 2
        assert swayman.shots_against == 30
        assert swayman.minutes is not None  # TOI should be parsed

        # Skater stats should be None for goalies
        assert swayman.goals is None
        assert swayman.assists is None
        assert swayman.points is None
        assert swayman.shots_on_goal is None


class TestNHLRoleSeparation:
    """Tests for skater vs goalie role separation."""

    def test_player_role_is_required(self, scraper: StubNHLScraper, team_identity: TeamIdentity) -> None:
        """player_role must be set on all parsed players."""
        soup = BeautifulSoup(VALID_SKATERS_HTML, "lxml")
        table = soup.find("table", id="BOS_skaters")

        players = scraper._parse_player_table(
            table=table,
            table_id="BOS_skaters",
            team_abbr="BOS",
            team_identity=team_identity,
            is_home=True,
            player_role="skater",
        )

        for player in players:
            assert player.player_role is not None, f"player_role is None for {player.player_name}"
            assert player.player_role in ("skater", "goalie"), f"Invalid role: {player.player_role}"

    def test_invalid_role_raises_error(self, scraper: StubNHLScraper, team_identity: TeamIdentity) -> None:
        """Passing an invalid role should raise ValueError."""
        soup = BeautifulSoup(VALID_SKATERS_HTML, "lxml")
        table = soup.find("table", id="BOS_skaters")

        with pytest.raises(ValueError, match="Invalid player_role"):
            scraper._parse_player_table(
                table=table,
                table_id="BOS_skaters",
                team_abbr="BOS",
                team_identity=team_identity,
                is_home=True,
                player_role="invalid_role",
            )


class TestNHLExtractPlayerStats:
    """Integration tests for _extract_player_stats method."""

    def test_full_extraction_returns_both_skaters_and_goalies(
        self, scraper: StubNHLScraper, team_identity: TeamIdentity
    ) -> None:
        """_extract_player_stats should return both skaters and goalies."""
        html = f"""
        <html>
          <body>
            {VALID_SKATERS_HTML}
            {VALID_GOALIES_HTML}
          </body>
        </html>
        """
        soup = BeautifulSoup(html, "lxml")

        players = scraper._extract_player_stats(soup, "BOS", team_identity, is_home=True)

        skaters = [p for p in players if p.player_role == "skater"]
        goalies = [p for p in players if p.player_role == "goalie"]

        # REGRESSION GUARDS
        assert len(skaters) > 0, "REGRESSION: Zero skaters extracted"
        assert len(goalies) > 0, "REGRESSION: Zero goalies extracted"

        # Specific counts
        assert len(skaters) == 3, f"Expected 3 skaters, got {len(skaters)}"
        assert len(goalies) == 1, f"Expected 1 goalie (Empty Net skipped), got {len(goalies)}"
