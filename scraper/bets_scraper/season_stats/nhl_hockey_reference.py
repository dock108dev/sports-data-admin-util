"""NHL season stats scraper powered by Hockey Reference."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable
from urllib.parse import urlparse

from bs4 import BeautifulSoup, Comment, Tag

from ..logging import logger
from ..models import NormalizedPlayerSeasonStats, NormalizedTeamSeasonStats, TeamIdentity
from ..normalization import normalize_team_name
from ..scrapers.base import BaseSportsReferenceScraper
from ..utils.parsing import (
    extract_all_stats_from_row,
    parse_float,
    parse_int,
    parse_time_to_minutes,
)


@dataclass(frozen=True)
class _ParsedTeam:
    name: str
    abbreviation: str | None


class NHLHockeyReferenceSeasonStatsScraper(BaseSportsReferenceScraper):
    """Fetch NHL team + player season stats from Hockey Reference."""

    sport = "nhl"
    league_code = "NHL"
    base_url = "https://www.hockey-reference.com/leagues/"

    def team_stats_url(self, season: int) -> str:
        return f"{self.base_url}NHL_{season}.html"

    def skater_stats_url(self, season: int) -> str:
        return f"{self.base_url}NHL_{season}_skaters.html"

    def goalie_stats_url(self, season: int) -> str:
        return f"{self.base_url}NHL_{season}_goalies.html"

    def _find_table(self, soup: BeautifulSoup, table_id: str, alternate_ids: Iterable[str] | None = None) -> Tag | None:
        table = soup.find("table", id=table_id)
        if table:
            return table

        if alternate_ids:
            for alt_id in alternate_ids:
                table = soup.find("table", id=alt_id)
                if table:
                    logger.debug("season_stats_table_found_alternate", primary_id=table_id, found_id=alt_id)
                    return table

        # Hockey-Reference often ships tables inside HTML comments.
        for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
            if table_id not in comment:
                continue
            comment_soup = BeautifulSoup(comment, "lxml")
            table = comment_soup.find("table", id=table_id)
            if table:
                logger.debug("season_stats_table_found_in_comment", table_id=table_id)
                return table
        return None

    @staticmethod
    def _parse_team_link(cell: Tag) -> _ParsedTeam | None:
        link = cell.find("a")
        if not link:
            return None
        team_name = link.text.strip()
        href = link.get("href", "")
        abbreviation = None
        if href:
            parts = urlparse(href).path.split("/")
            if len(parts) >= 3:
                abbreviation = parts[2].upper()
        return _ParsedTeam(name=team_name, abbreviation=abbreviation)

    @staticmethod
    def _first_stat(raw_stats: dict[str, str], *keys: str) -> str | None:
        for key in keys:
            value = raw_stats.get(key)
            if value not in (None, "", "-"):
                return value
        return None

    def fetch_team_stats(self, season: int, season_type: str = "regular") -> list[NormalizedTeamSeasonStats]:
        url = self.team_stats_url(season)
        soup = self.fetch_html(url)
        table = self._find_table(soup, "stats", alternate_ids=["team_stats", "all_team_stats"])
        if not table:
            logger.warning("nhl_team_stats_table_not_found", url=url, season=season)
            return []

        tbody = table.find("tbody")
        if not tbody:
            logger.warning("nhl_team_stats_tbody_not_found", url=url, season=season)
            return []

        payloads: list[NormalizedTeamSeasonStats] = []
        for row in tbody.find_all("tr"):
            if "thead" in (row.get("class") or []):
                continue

            team_cell = row.find("th", {"data-stat": "team_name"}) or row.find("th", {"data-stat": "team"})
            if not team_cell:
                continue

            parsed_team = self._parse_team_link(team_cell)
            if not parsed_team or "average" in parsed_team.name.lower():
                continue

            canonical_name, abbreviation = normalize_team_name(self.league_code, parsed_team.name)
            team_identity = TeamIdentity(
                league_code=self.league_code,
                name=canonical_name,
                short_name=canonical_name,
                abbreviation=abbreviation,
                external_ref=abbreviation.upper() if abbreviation else None,
            )

            raw_stats = extract_all_stats_from_row(row)
            games_played = parse_int(self._first_stat(raw_stats, "games_played", "gp", "g"))
            wins = parse_int(self._first_stat(raw_stats, "wins", "w"))
            losses = parse_int(self._first_stat(raw_stats, "losses", "l"))
            overtime_losses = parse_int(self._first_stat(raw_stats, "ot_losses", "otl"))
            points = parse_int(self._first_stat(raw_stats, "points", "pts"))
            goals_for = parse_int(self._first_stat(raw_stats, "goals_for", "gf"))
            goals_against = parse_int(self._first_stat(raw_stats, "goals_against", "ga"))
            goal_diff = parse_int(self._first_stat(raw_stats, "goal_diff", "diff"))
            shots_for = parse_int(self._first_stat(raw_stats, "shots", "shots_for", "s"))
            shots_against = parse_int(self._first_stat(raw_stats, "shots_against", "sa"))
            penalty_minutes = parse_int(self._first_stat(raw_stats, "pen_min", "pim"))
            power_play_pct = parse_float(self._first_stat(raw_stats, "pp_pct", "power_play_pct"))
            penalty_kill_pct = parse_float(self._first_stat(raw_stats, "pk_pct", "penalty_kill_pct"))

            payloads.append(
                NormalizedTeamSeasonStats(
                    team=team_identity,
                    season=season,
                    season_type=season_type,
                    games_played=games_played,
                    wins=wins,
                    losses=losses,
                    overtime_losses=overtime_losses,
                    points=points,
                    goals_for=goals_for,
                    goals_against=goals_against,
                    goal_diff=goal_diff,
                    shots_for=shots_for,
                    shots_against=shots_against,
                    penalty_minutes=penalty_minutes,
                    power_play_pct=power_play_pct,
                    penalty_kill_pct=penalty_kill_pct,
                    raw_stats=raw_stats,
                )
            )

        logger.info("nhl_team_season_stats_parsed", season=season, count=len(payloads))
        return payloads

    def _parse_player_table(
        self,
        table: Tag,
        season: int,
        season_type: str,
        player_type: str,
    ) -> list[NormalizedPlayerSeasonStats]:
        tbody = table.find("tbody")
        if not tbody:
            return []

        payloads: list[NormalizedPlayerSeasonStats] = []
        for row in tbody.find_all("tr"):
            if "thead" in (row.get("class") or []):
                continue

            player_cell = row.find("th", {"data-stat": "player"})
            if not player_cell:
                continue
            player_link = player_cell.find("a")
            if not player_link:
                continue
            player_name = player_link.text.strip()
            href = player_link.get("href", "")
            player_id = href.split("/")[-1].replace(".html", "") if href else player_name

            raw_stats = extract_all_stats_from_row(row)
            team_abbr = self._first_stat(raw_stats, "team_id", "team", "tm")
            if team_abbr:
                team_abbr = team_abbr.strip().upper()
            team_identity = None
            # Skater tables include a TOT row for multi-team seasons; keep that row without a team link.
            if team_abbr and team_abbr.upper() != "TOT":
                canonical_name, abbreviation = normalize_team_name(self.league_code, team_abbr)
                team_identity = TeamIdentity(
                    league_code=self.league_code,
                    name=canonical_name,
                    short_name=canonical_name,
                    abbreviation=abbreviation,
                    external_ref=abbreviation.upper() if abbreviation else None,
                )

            position = self._first_stat(raw_stats, "pos", "position")
            games_played = parse_int(self._first_stat(raw_stats, "games_played", "gp", "g"))
            goals = parse_int(self._first_stat(raw_stats, "goals", "g"))
            assists = parse_int(self._first_stat(raw_stats, "assists", "a"))
            points = parse_int(self._first_stat(raw_stats, "points", "pts"))
            toi = parse_time_to_minutes(self._first_stat(raw_stats, "toi_avg", "toi"))

            payloads.append(
                NormalizedPlayerSeasonStats(
                    player_id=player_id,
                    player_name=player_name,
                    team=team_identity,
                    team_abbreviation=team_abbr,
                    season=season,
                    season_type=season_type,
                    position=position,
                    games_played=games_played,
                    goals=goals,
                    assists=assists,
                    points=points,
                    time_on_ice=toi,
                    player_type=player_type,
                    raw_stats=raw_stats,
                )
            )

        return payloads

    def fetch_player_stats(self, season: int, season_type: str = "regular") -> list[NormalizedPlayerSeasonStats]:
        skater_url = self.skater_stats_url(season)
        goalie_url = self.goalie_stats_url(season)

        skater_soup = self.fetch_html(skater_url)
        goalie_soup = self.fetch_html(goalie_url)

        skater_table = self._find_table(skater_soup, "skaters", alternate_ids=["skaters_stats", "all_skaters"])
        goalie_table = self._find_table(goalie_soup, "goalies", alternate_ids=["goalies_stats", "all_goalies"])

        payloads: list[NormalizedPlayerSeasonStats] = []
        if skater_table:
            payloads.extend(self._parse_player_table(skater_table, season, season_type, "skater"))
        else:
            logger.warning("nhl_skater_stats_table_not_found", season=season)

        if goalie_table:
            payloads.extend(self._parse_player_table(goalie_table, season, season_type, "goalie"))
        else:
            logger.warning("nhl_goalie_stats_table_not_found", season=season)

        logger.info("nhl_player_season_stats_parsed", season=season, count=len(payloads))
        return payloads
