from __future__ import annotations

import os
import sys
from pathlib import Path

# Ensure the scraper package is importable when running from repo root without installing it.
REPO_ROOT = Path(__file__).resolve().parents[2]
SCRAPER_ROOT = REPO_ROOT / "scraper"
if str(SCRAPER_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRAPER_ROOT))

# The scraper settings are loaded at import time and require DATABASE_URL.
# For these pure unit tests, a dummy local URL is sufficient.
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost:5432/test_db")

from sports_scraper.scrapers.nhl_sportsref import NHLSportsReferenceScraper


class StubNHLSportsReferenceScraper(NHLSportsReferenceScraper):
    def __init__(self, html: str) -> None:
        super().__init__()
        self._html = html

    def fetch_html(self, url: str, game_date=None):  # type: ignore[override]
        from bs4 import BeautifulSoup

        return BeautifulSoup(self._html, "lxml")


def test_nhl_pbp_parsing_with_shootout_period() -> None:
    html = """
    <html>
      <body>
        <div class="scorebox">
          <div><strong><a itemprop="name">New York Rangers</a></strong></div>
          <div><strong><a itemprop="name">New Jersey Devils</a></strong></div>
        </div>
        <table id="pbp">
          <tr class="thead"><th colspan="6">1st Period</th></tr>
          <tr>
            <td data-stat="time">20:00</td>
            <td data-stat="event">Faceoff</td>
            <td data-stat="team">NYR</td>
            <td data-stat="description">Opening faceoff</td>
            <td data-stat="score">0-0</td>
          </tr>
          <tr class="thead"><th colspan="6">Shootout</th></tr>
          <tr>
            <td data-stat="time">00:00</td>
            <td data-stat="event">Shot</td>
            <td data-stat="team">NYR</td>
            <td data-stat="description">NYR shootout attempt</td>
            <td data-stat="score">1-0</td>
          </tr>
        </table>
      </body>
    </html>
    """
    scraper = StubNHLSportsReferenceScraper(html)
    payload = scraper.fetch_play_by_play("202310100NYR", game_date=None)

    assert len(payload.plays) == 2

    first_play = payload.plays[0]
    assert first_play.quarter == 1
    assert first_play.game_clock == "20:00"
    assert first_play.play_type == "Faceoff"
    assert first_play.team_abbreviation == "NYR"
    assert first_play.description == "Opening faceoff"
    assert first_play.away_score == 0
    assert first_play.home_score == 0

    shootout_play = payload.plays[1]
    assert shootout_play.quarter == 4
    assert shootout_play.play_type == "Shot"
    assert shootout_play.description == "NYR shootout attempt"
    assert shootout_play.home_score == 0
    assert shootout_play.away_score == 1
