"""NHL scraper powered by Hockey Reference."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Sequence
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..logging import logger
from ..models import (
    GameIdentification,
    NormalizedGame,
    NormalizedPlayerBoxscore,
    NormalizedPlayByPlay,
    NormalizedTeamBoxscore,
    TeamIdentity,
)
from ..utils.parsing import extract_all_stats_from_row, get_stat_from_row, parse_float, parse_int
from .base import BaseSportsReferenceScraper, ScraperError
from .nhl_sportsref_helpers import (
    parse_pbp_period_marker,
    parse_pbp_row,
    parse_scorebox_abbreviations,
    parse_scorebox_team,
)


class NHLSportsReferenceScraper(BaseSportsReferenceScraper):
    sport = "nhl"
    league_code = "NHL"
    base_url = "https://www.hockey-reference.com/boxscores/"
    _OT_NUMBER_PATTERN = re.compile(r"(?:ot|overtime)\s*(\d+)|(\d+)\s*(?:ot|overtime)")
    _SCORE_PATTERN = re.compile(r"^(\d+)\s*-\s*(\d+)$")

    # _parse_team_row now inherited from base class

    def pbp_url(self, source_game_key: str) -> str:
        return f"https://www.hockey-reference.com/boxscores/pbp/{source_game_key}.html"

    def _extract_team_stats(self, soup: BeautifulSoup, team_abbr: str) -> dict:
        """Extract team stats from boxscore table."""
        from ..utils.html_parsing import extract_team_stats_from_table, find_table_by_id
        
        # Hockey Reference uses UPPERCASE team abbreviations in table IDs
        table_id = f"box-{team_abbr.upper()}-game-basic"
        table = find_table_by_id(soup, table_id)
        
        if not table:
            logger.warning("team_stats_table_not_found", table_id=table_id, team_abbr=team_abbr)
            return {}
        
        return extract_team_stats_from_table(table, team_abbr, table_id)

    def _extract_player_stats(
        self, soup: BeautifulSoup, team_abbr: str, team_identity: TeamIdentity, is_home: bool
    ) -> list[NormalizedPlayerBoxscore]:
        """Parse individual player rows from box-{TEAM}-game-basic table."""
        from ..utils.html_parsing import find_player_table
        
        # Hockey Reference uses UPPERCASE team abbreviations in table IDs
        table_id = f"box-{team_abbr.upper()}-game-basic"
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
            row_classes = row.get("class", [])
            if "thead" in row_classes:
                skipped_thead += 1
                continue

            player_cell = row.find("th", {"data-stat": "player"})
            if not player_cell:
                skipped_no_player_cell += 1
                continue

            player_link = player_cell.find("a")
            if not player_link:
                skipped_no_player_link += 1
                continue

            player_name = player_link.text.strip()
            href = player_link.get("href", "")
            player_id = href.split("/")[-1].replace(".html", "") if href else player_name

            raw_stats = extract_all_stats_from_row(row)

            players.append(
                NormalizedPlayerBoxscore(
                    player_id=player_id,
                    player_name=player_name,
                    team=team_identity,
                    minutes=parse_float(get_stat_from_row(row, "toi")),  # Time on ice
                    points=parse_int(get_stat_from_row(row, "pts")),
                    rebounds=None,  # Not applicable to hockey
                    assists=parse_int(get_stat_from_row(row, "a")),
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
            rebounds=None,  # Not applicable to hockey
            assists=parse_int(stats.get("a")),
            turnovers=None,  # Not tracked in hockey boxscores
            raw_stats=stats,
        )

    # _season_from_date now inherited from base class

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
                game_date=datetime.combine(day, datetime.min.time()),
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

    def fetch_play_by_play(self, source_game_key: str, game_date: date) -> NormalizedPlayByPlay:
        """Fetch and parse play-by-play for a single game.

        Hockey Reference PBP pages are expected to include a single table with id="pbp".
        Period headers are identified from thead rows and mapped to sequential periods
        (1-3 regulation, 4+ overtime, shootout handled as the next period).
        """
        url = self.pbp_url(source_game_key)
        soup = self.fetch_html(url, game_date=game_date)

        away_abbr, home_abbr = parse_scorebox_abbreviations(soup, self.league_code)

        plays: list[NormalizedPlay] = []
        play_index = 0

        table = soup.find("table", id="pbp")
        if not table:
            logger.warning("pbp_table_not_found", game_key=source_game_key)
            return NormalizedPlayByPlay(source_game_key=source_game_key, plays=plays)

        current_period = 0
        for row in table.find_all("tr"):
            row_classes = row.get("class", [])
            if "thead" in row_classes:
                period_marker, is_shootout = parse_pbp_period_marker(row, self._OT_NUMBER_PATTERN)
                if is_shootout:
                    current_period = max(current_period, 3) + 1
                    continue
                if period_marker:
                    current_period = period_marker
                continue

            if current_period == 0:
                continue

            play = parse_pbp_row(
                row,
                period=current_period,
                away_abbr=away_abbr,
                home_abbr=home_abbr,
                play_index=play_index,
                league_code=self.league_code,
                score_pattern=self._SCORE_PATTERN,
            )
            if play:
                plays.append(play)
                play_index += 1

        logger.info(
            "pbp_parsed",
            game_key=source_game_key,
            game_date=str(game_date),
            plays=len(plays),
        )

        return NormalizedPlayByPlay(source_game_key=source_game_key, plays=plays)

    def fetch_single_boxscore(self, source_game_key: str, game_date: date) -> NormalizedGame | None:
        """Fetch boxscore for a single game by its source key.
        
        Used for backfilling player stats on existing games.
        source_game_key format: e.g., "202410220BOS"
        """
        boxscore_url = f"https://www.hockey-reference.com/boxscores/{source_game_key}.html"
        logger.info("fetching_single_boxscore", url=boxscore_url, game_key=source_game_key, game_date=str(game_date))

        try:
            soup = self.fetch_html(boxscore_url, game_date=game_date)
        except Exception as e:
            logger.error("single_boxscore_fetch_failed", game_key=source_game_key, error=str(e))
            return None

        scorebox = soup.find("div", class_="scorebox")
        if not scorebox:
            logger.warning("scorebox_not_found", game_key=source_game_key)
            return None

        team_divs = scorebox.find_all("div", recursive=False)
        if len(team_divs) < 2:
            logger.warning("team_divs_not_found", game_key=source_game_key, found=len(team_divs))
            return None

        away_result = parse_scorebox_team(team_divs[0], self.league_code)
        home_result = parse_scorebox_team(team_divs[1], self.league_code)

        if not away_result or not home_result:
            logger.warning("could_not_parse_scorebox_teams", game_key=source_game_key)
            return None

        away_identity, away_score = away_result
        home_identity, home_score = home_result

        away_stats = self._extract_team_stats(soup, away_identity.abbreviation or "")
        home_stats = self._extract_team_stats(soup, home_identity.abbreviation or "")

        away_players = self._extract_player_stats(
            soup, away_identity.abbreviation or "", away_identity, is_home=False
        )
        home_players = self._extract_player_stats(
            soup, home_identity.abbreviation or "", home_identity, is_home=True
        )

        identity = GameIdentification(
            league_code=self.league_code,
            season=self._season_from_date(game_date),
            season_type="regular",
            game_date=datetime.combine(game_date, datetime.min.time()),
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
