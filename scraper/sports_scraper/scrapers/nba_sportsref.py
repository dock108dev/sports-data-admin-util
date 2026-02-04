"""NBA scraper powered by Basketball Reference.

Provides boxscore scraping for NBA games. Play-by-play data is fetched
via the official NBA API (see live/nba.py).
"""

from __future__ import annotations

from datetime import date
from typing import Sequence
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..logging import logger
from ..models import (
    GameIdentification,
    NormalizedGame,
    NormalizedPlayerBoxscore,
    NormalizedTeamBoxscore,
    TeamIdentity,
)
from ..normalization import normalize_team_name
from ..utils.datetime_utils import date_to_utc_datetime
from ..utils import (
    extract_all_stats_from_row,
    get_stat_from_row,
    parse_float,
    parse_int,
)
from .base import BaseSportsReferenceScraper, ScraperError

# Sports Reference uses different abbreviations for some NBA teams
# Map from our canonical abbreviations to Sports Reference abbreviations
SPORTSREF_ABBR_MAP: dict[str, str] = {
    "CHA": "CHO",  # Charlotte Hornets
    "BKN": "BRK",  # Brooklyn Nets
}


def _to_sportsref_abbr(abbr: str) -> str:
    """Convert canonical team abbreviation to Sports Reference abbreviation."""
    return SPORTSREF_ABBR_MAP.get(abbr.upper(), abbr.upper())


class NBASportsReferenceScraper(BaseSportsReferenceScraper):
    sport = "nba"
    league_code = "NBA"
    base_url = "https://www.basketball-reference.com/boxscores/"

    def _extract_team_stats(self, soup: BeautifulSoup, team_abbr: str) -> dict:
        """Extract team stats from boxscore table."""
        from ..utils.html_parsing import extract_team_stats_from_table, find_table_by_id, get_table_ids_on_page

        # Sports Reference uses different abbreviations for some teams (CHO for Charlotte, BRK for Brooklyn)
        sportsref_abbr = _to_sportsref_abbr(team_abbr)
        table_id = f"box-{sportsref_abbr}-game-basic"
        table = find_table_by_id(soup, table_id)

        if not table:
            # Log all table IDs found on the page to help debug
            table_ids = get_table_ids_on_page(soup, limit=15)
            logger.warning(
                "team_stats_table_not_found",
                table_id=table_id,
                team_abbr=team_abbr,
                available_tables=table_ids,
            )
            return {}

        return extract_team_stats_from_table(table, team_abbr, table_id)

    def _extract_player_stats(
        self, soup: BeautifulSoup, team_abbr: str, team_identity: TeamIdentity, is_home: bool
    ) -> list[NormalizedPlayerBoxscore]:
        """Parse individual player rows from box-{TEAM}-game-basic table."""
        from ..utils.html_parsing import find_player_table

        # Sports Reference uses different abbreviations for some teams (CHO for Charlotte, BRK for Brooklyn)
        sportsref_abbr = _to_sportsref_abbr(team_abbr)
        table_id = f"box-{sportsref_abbr}-game-basic"
        table = find_player_table(soup, table_id)

        if not table:
            logger.warning("player_stats_table_not_found", table_id=table_id, team=team_abbr)
            return []

        logger.debug("player_stats_table_found", table_id=table_id, team=team_abbr)

        players: list[NormalizedPlayerBoxscore] = []
        tbody = table.find("tbody")
        if not tbody:
            logger.warning("player_stats_tbody_not_found", table_id=table_id, team=team_abbr)
            return players

        all_rows = tbody.find_all("tr")
        logger.debug("player_stats_rows_found", table_id=table_id, row_count=len(all_rows))

        skipped_thead = 0
        skipped_no_player_cell = 0
        skipped_no_player_link = 0
        parsed_count = 0

        for row in all_rows:
            # Skip section headers (rows with class="thead") and reserve rows
            row_classes = row.get("class", [])
            if "thead" in row_classes:
                skipped_thead += 1
                continue

            # Get player name and external ref from the th cell
            player_cell = row.find("th", {"data-stat": "player"})
            if not player_cell:
                skipped_no_player_cell += 1
                continue

            player_link = player_cell.find("a")
            if not player_link:
                # Skip "Team Totals" or "Reserves" header rows
                skipped_no_player_link += 1
                continue

            player_name = player_link.text.strip()
            # Extract player ID from href like "/players/t/tatumja01.html"
            href = player_link.get("href", "")
            player_id = href.split("/")[-1].replace(".html", "") if href else player_name

            # Build raw stats dict with all available columns
            raw_stats = extract_all_stats_from_row(row)

            players.append(
                NormalizedPlayerBoxscore(
                    player_id=player_id,
                    player_name=player_name,
                    team=team_identity,
                    minutes=parse_float(get_stat_from_row(row, "mp")),
                    points=parse_int(get_stat_from_row(row, "pts")),
                    rebounds=parse_int(get_stat_from_row(row, "trb")),
                    assists=parse_int(get_stat_from_row(row, "ast")),
                    raw_stats=raw_stats,
                )
            )
            parsed_count += 1

        logger.info(
            "player_stats_extraction_complete",
            team=team_abbr,
            is_home=is_home,
            total_rows=len(all_rows),
            skipped_thead=skipped_thead,
            skipped_no_player_cell=skipped_no_player_cell,
            skipped_no_player_link=skipped_no_player_link,
            parsed_players=parsed_count,
        )

        return players

    def _build_team_boxscore(self, identity: TeamIdentity, is_home: bool, score: int, stats: dict) -> NormalizedTeamBoxscore:
        return NormalizedTeamBoxscore(
            team=identity,
            is_home=is_home,
            points=score,
            rebounds=parse_int(stats.get("trb")),
            assists=parse_int(stats.get("ast")),
            turnovers=parse_int(stats.get("tov")),
            raw_stats=stats,
        )

    def fetch_games_for_date(self, day: date) -> Sequence[NormalizedGame]:
        soup = self.fetch_html(self.scoreboard_url(day), game_date=day)
        game_divs = soup.select("div.game_summary")
        games: list[NormalizedGame] = []
        for div in game_divs:
            team_rows = div.select("table.teams tr")
            if len(team_rows) < 2:
                continue
            away_identity, away_score = self._parse_team_row(team_rows[0])
            home_identity, home_score = self._parse_team_row(team_rows[1])

            boxscore_link = div.select_one("p.links a[href*='/boxscores/']")
            if not boxscore_link:
                raise ScraperError("Missing boxscore link")
            boxscore_url = urljoin(self.base_url, boxscore_link["href"])
            source_game_key = boxscore_link["href"].split("/")[-1].replace(".html", "")
            box_soup = self.fetch_html(boxscore_url, game_date=day)

            away_stats = self._extract_team_stats(box_soup, away_identity.abbreviation or "")
            home_stats = self._extract_team_stats(box_soup, home_identity.abbreviation or "")

            # Extract player-level stats for both teams
            away_players = self._extract_player_stats(
                box_soup, away_identity.abbreviation or "", away_identity, is_home=False
            )
            home_players = self._extract_player_stats(
                box_soup, home_identity.abbreviation or "", home_identity, is_home=True
            )

            identity = GameIdentification(
                league_code=self.league_code,
                season=self._season_from_date(day),
                season_type="regular",
                game_date=date_to_utc_datetime(day),
                home_team=home_identity,
                away_team=away_identity,
                source_game_key=source_game_key,
            )
            team_boxscores = [
                self._build_team_boxscore(away_identity, False, away_score, away_stats),
                self._build_team_boxscore(home_identity, True, home_score, home_stats),
            ]
            player_boxscores = away_players + home_players

            games.append(
                NormalizedGame(
                    identity=identity,
                    status="completed",
                    home_score=home_score,
                    away_score=away_score,
                    team_boxscores=team_boxscores,
                    player_boxscores=player_boxscores,
                )
            )
        return games

    def fetch_single_boxscore(self, source_game_key: str, game_date: date) -> NormalizedGame | None:
        """Fetch boxscore for a single game by its source key.

        Used for backfilling player stats on existing games.
        source_game_key format: e.g., "202410220BOS"
        """
        boxscore_url = f"https://www.basketball-reference.com/boxscores/{source_game_key}.html"
        logger.info("fetching_single_boxscore", url=boxscore_url, game_key=source_game_key, game_date=str(game_date))

        try:
            soup = self.fetch_html(boxscore_url, game_date=game_date)
        except Exception as e:
            logger.error("single_boxscore_fetch_failed", game_key=source_game_key, error=str(e))
            return None

        # Parse the scorebox to get team info
        scorebox = soup.find("div", class_="scorebox")
        if not scorebox:
            logger.warning("scorebox_not_found", game_key=source_game_key)
            return None

        # Get team divs - first is away, second is home
        team_divs = scorebox.find_all("div", recursive=False)
        if len(team_divs) < 2:
            logger.warning("team_divs_not_found", game_key=source_game_key, found=len(team_divs))
            return None

        def parse_scorebox_team(div) -> tuple[TeamIdentity, int] | None:
            """Parse team info from scorebox div."""
            team_link = div.find("a", itemprop="name")
            if not team_link:
                # Try alternate selector
                strong = div.find("strong")
                team_link = strong.find("a") if strong else None
            if not team_link:
                return None

            team_name = team_link.text.strip()
            # Normalize team name to canonical form
            canonical_name, abbreviation = normalize_team_name(self.league_code, team_name)

            # Find score - look for class "score" or "scores"
            score_div = div.find("div", class_="score")
            if not score_div:
                score_div = div.find("div", class_="scores")
            if not score_div:
                return None

            score = parse_int(score_div.text.strip())
            if score is None:
                return None

            identity = TeamIdentity(
                league_code=self.league_code,
                name=canonical_name,
                short_name=canonical_name,
                abbreviation=abbreviation,
                external_ref=abbreviation.upper(),
            )
            return identity, score

        away_result = parse_scorebox_team(team_divs[0])
        home_result = parse_scorebox_team(team_divs[1])

        if not away_result or not home_result:
            logger.warning("could_not_parse_scorebox_teams", game_key=source_game_key)
            return None

        away_identity, away_score = away_result
        home_identity, home_score = home_result

        logger.debug(
            "parsed_scorebox",
            game_key=source_game_key,
            away_team=away_identity.abbreviation,
            home_team=home_identity.abbreviation,
            away_score=away_score,
            home_score=home_score,
        )

        # Extract team stats
        away_stats = self._extract_team_stats(soup, away_identity.abbreviation or "")
        home_stats = self._extract_team_stats(soup, home_identity.abbreviation or "")

        # Extract player stats
        away_players = self._extract_player_stats(
            soup, away_identity.abbreviation or "", away_identity, is_home=False
        )
        home_players = self._extract_player_stats(
            soup, home_identity.abbreviation or "", home_identity, is_home=True
        )

        logger.info(
            "extracted_player_stats",
            game_key=source_game_key,
            away_players=len(away_players),
            home_players=len(home_players),
        )

        identity = GameIdentification(
            league_code=self.league_code,
            season=self._season_from_date(game_date),
            season_type="regular",
            game_date=date_to_utc_datetime(game_date),
            home_team=home_identity,
            away_team=away_identity,
            source_game_key=source_game_key,
        )

        team_boxscores = [
            self._build_team_boxscore(away_identity, False, away_score, away_stats),
            self._build_team_boxscore(home_identity, True, home_score, home_stats),
        ]
        player_boxscores = away_players + home_players

        return NormalizedGame(
            identity=identity,
            status="completed",
            home_score=home_score,
            away_score=away_score,
            team_boxscores=team_boxscores,
            player_boxscores=player_boxscores,
        )
