from __future__ import annotations

import os
import sys
from pathlib import Path
from datetime import date

# Ensure the scraper package is importable when running from repo root without installing it.
REPO_ROOT = Path(__file__).resolve().parents[2]
SCRAPER_ROOT = REPO_ROOT / "scraper"
if str(SCRAPER_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRAPER_ROOT))

# The scraper settings are loaded at import time and require DATABASE_URL.
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost:5432/test_db")

from bets_scraper.scrapers.ncaab_sportsref import NCAABSportsReferenceScraper


class StubNCAABSportsReferenceScraper(NCAABSportsReferenceScraper):
    def __init__(self, html: str) -> None:
        super().__init__()
        self._html = html

    def fetch_html(self, url: str, game_date=None):  # type: ignore[override]
        from bs4 import BeautifulSoup

        return BeautifulSoup(self._html, "lxml")


def test_ncaab_fetch_game_stubs_for_date_extracts_source_game_key_without_boxscore_fetch() -> None:
    html = """
    <html>
      <body>
        <div class="game_summary">
          <table class="teams">
            <tr>
              <th><a href="/cbb/schools/duke/">Duke</a></th>
              <td class="right">70</td>
              <td class="right">Final</td>
            </tr>
            <tr>
              <th><a href="/cbb/schools/north-carolina/">North Carolina</a></th>
              <td class="right">68</td>
              <td class="right">Final</td>
            </tr>
          </table>
          <p class="links">
            <a href="/cbb/boxscores/202512010unc.html">Box Score</a>
          </p>
        </div>
      </body>
    </html>
    """
    scraper = StubNCAABSportsReferenceScraper(html)
    stubs = list(scraper.fetch_game_stubs_for_date(date(2025, 12, 1)))

    assert len(stubs) == 1
    stub = stubs[0]
    assert stub.identity.source_game_key == "202512010unc"
    assert stub.home_score == 68
    assert stub.away_score == 70


def test_ncaab_pbp_table_can_be_inside_html_comment() -> None:
    html = """
    <html>
      <body>
        <div class="scorebox">
          <div><strong><a itemprop="name">Duke</a></strong></div>
          <div><strong><a itemprop="name">North Carolina</a></strong></div>
        </div>
        <!--
        <table id="pbp">
          <tr class="thead"><th colspan="6">1st Half</th></tr>
          <tr>
            <td data-stat="time">20:00</td>
            <td data-stat="event">Jump Ball</td>
            <td data-stat="team">DUKE</td>
            <td data-stat="description">Start</td>
            <td data-stat="score">0-0</td>
          </tr>
        </table>
        -->
      </body>
    </html>
    """
    scraper = StubNCAABSportsReferenceScraper(html)
    pbp = scraper.fetch_play_by_play("202512010unc", date(2025, 12, 1))

    assert len(pbp.plays) == 1
    assert pbp.plays[0].quarter == 1
    assert pbp.plays[0].game_clock == "20:00"

