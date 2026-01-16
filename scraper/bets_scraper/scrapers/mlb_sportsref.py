"""MLB scraper powered by Baseball Reference."""

from __future__ import annotations

from datetime import date
from typing import Sequence

from ..utils.datetime_utils import date_to_utc_datetime
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
from ..utils import extract_all_stats_from_row
from .base import BaseSportsReferenceScraper, ScraperError


class MLBSportsReferenceScraper(BaseSportsReferenceScraper):
    sport = "mlb"
    league_code = "MLB"
    base_url = "https://www.baseball-reference.com/boxes/"

    # _parse_team_row now inherited from base class

    def _extract_team_stats(self, soup: BeautifulSoup, team_abbr: str) -> dict:
        """Extract team stats from boxscore table."""
        from ..utils.html_parsing import extract_team_stats_from_table
        
        # Baseball Reference uses team abbreviation in table IDs (CSS selector format)
        table_id = f"{team_abbr.upper()}_batting"
        table = soup.select_one(f"#{table_id}")
        
        if not table:
            logger.warning("team_stats_table_not_found", table_id=table_id, team_abbr=team_abbr)
            return {}
        
        return extract_team_stats_from_table(table, team_abbr, table_id)

    def _extract_player_stats(
        self, soup: BeautifulSoup, team_abbr: str, team_identity: TeamIdentity, is_home: bool
    ) -> list[NormalizedPlayerBoxscore]:
        """Parse individual player rows from batting and pitching tables."""
        players: list[NormalizedPlayerBoxscore] = []
        
        # MLB has separate tables for batting and pitching
        table_types = ["batting", "pitching"]
        
        
        for table_type in table_types:
            table_id = f"{team_abbr.upper()}_{table_type}"
            # MLB uses CSS selector format (#id)
            table = soup.select_one(f"#{table_id}")
            
            if not table:
                continue
            
            logger.debug("player_stats_table_found", table_id=table_id, team=team_abbr, type=table_type)
            
            tbody = table.find("tbody")
            if not tbody:
                continue
            
            for row in tbody.find_all("tr"):
                if row.get("class") and "thead" in row.get("class", []):
                    continue
                
                player_cell = row.find("th", {"data-stat": "player"})
                if not player_cell:
                    continue
                
                player_link = player_cell.find("a")
                if not player_link:
                    continue
                
                player_name = player_link.text.strip()
                href = player_link.get("href", "")
                player_id = href.split("/")[-1].replace(".shtml", "") if href else player_name
                
                raw_stats = extract_all_stats_from_row(row)
                raw_stats["_table_type"] = table_type
                
                players.append(
                    NormalizedPlayerBoxscore(
                        player_id=player_id,
                        player_name=player_name,
                        team=team_identity,
                        minutes=None,
                        points=None,
                        rebounds=None,
                        assists=None,
                        raw_stats=raw_stats,
                    )
                )
        
        logger.info(
            "player_stats_extraction_complete",
            team=team_abbr,
            is_home=is_home,
            parsed_players=len(players),
        )
        
        return players

    def _build_team_boxscore(self, identity: TeamIdentity, is_home: bool, score: int, stats: dict) -> NormalizedTeamBoxscore:
        return NormalizedTeamBoxscore(
            team=identity,
            is_home=is_home,
            points=score,
            rebounds=None,
            assists=None,
            turnovers=None,
            raw_stats=stats,
        )

    # _season_from_date now inherited from base class

    def scoreboard_url(self, day: date) -> str:
        # Baseball Reference uses a different URL format
        return f"{self.base_url}?month={day.month}&day={day.day}&year={day.year}"

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

            boxscore_link = div.select_one("p.links a[href*='/boxes/']")
            if not boxscore_link:
                raise ScraperError("Missing boxscore link")
            boxscore_url = urljoin(self.base_url, boxscore_link["href"])
            # Extract game key from URL like /boxes/NYY/NYY202410010.shtml
            source_game_key = boxscore_link["href"].split("/")[-1].replace(".shtml", "")
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
        
        source_game_key format: e.g., "NYY202410010" (team abbreviation + date)
        """
        # Extract team abbreviation from game key (first 3 chars)
        team_abbr = source_game_key[:3]
        boxscore_url = f"https://www.baseball-reference.com/boxes/{team_abbr}/{source_game_key}.shtml"
        
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

        def parse_scorebox_team(div) -> tuple[TeamIdentity, int] | None:
            team_link = div.find("a", itemprop="name")
            if not team_link:
                strong = div.find("strong")
                team_link = strong.find("a") if strong else None
            if not team_link:
                return None

            team_name = team_link.text.strip()
            # Normalize team name to canonical form
            canonical_name, abbreviation = normalize_team_name(self.league_code, team_name)

            score_div = div.find("div", class_="score")
            if not score_div:
                return None
            
            try:
                score = int(score_div.text.strip())
            except ValueError:
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

