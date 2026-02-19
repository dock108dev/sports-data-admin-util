"""NCAA basketball scraper using sports-reference.com/cbb."""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import date
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..logging import logger
from ..models import (
    GameIdentification,
    NormalizedGame,
    NormalizedPlay,
    NormalizedPlayByPlay,
    NormalizedPlayerBoxscore,
    NormalizedTeamBoxscore,
    TeamIdentity,
)
from ..normalization import normalize_team_name
from ..utils.datetime_utils import date_to_utc_datetime
from ..utils.parsing import parse_int
from .base import BaseSportsReferenceScraper, ScraperError
from .ncaab_sportsref_helpers import extract_player_stats, extract_team_stats


class NCAABSportsReferenceScraper(BaseSportsReferenceScraper):
    sport = "ncaab"
    league_code = "NCAAB"
    base_url = "https://www.sports-reference.com/cbb/boxscores/"
    _NON_NUMERIC_SCORE_MARKERS = {
        "FINAL",
        "FINAL/OT",
        "FINAL/2OT",
        "FINAL/3OT",
        "OT",
        "PREVIEW",
        "POSTPONED",
        "CANCELED",
        "CANCELLED",
        "UPCOMING",
        "TBA",
        "TBD",
        "PPD",
    }

    _OT_NUMBER_PATTERN = re.compile(r"(?:ot|overtime)\s*(\d+)|(\d+)\s*(?:ot|overtime)")

    def pbp_url(self, source_game_key: str) -> str:
        """NCAAB PBP is embedded in the main boxscore page, not in a separate /pbp/ directory."""
        return f"https://www.sports-reference.com/cbb/boxscores/{source_game_key}.html"

    def _parse_team_row(self, row) -> tuple[TeamIdentity, int]:
        """
        NCAA basketball scoreboards occasionally append a trailing status cell
        (e.g., \"Final\" or \"Final/OT\"). Instead of assuming the last <td>
        contains the numeric score, scan cells from right to left until we find
        the first value that can be parsed as an integer.
        """
        team_link = row.find("a")
        if not team_link:
            raise ScraperError("Missing team link")
        team_name = team_link.text.strip()
        canonical_name, abbreviation = normalize_team_name(self.league_code, team_name)

        score = None
        score_text: str | None = None
        for cell in reversed(row.find_all("td")):
            score_text = cell.text.strip()
            score = parse_int(score_text)
            if score is not None:
                break

        if score is None:
            status_hint = (score_text or "unknown").upper()
            if status_hint in self._NON_NUMERIC_SCORE_MARKERS:
                raise ScraperError(f"score_unavailable_status:{status_hint}")
            raise ScraperError(f"invalid_score_value:{score_text or 'unknown'}")

        identity = TeamIdentity(
            league_code=self.league_code,
            name=canonical_name,
            short_name=canonical_name,
            abbreviation=abbreviation,
            external_ref=abbreviation.upper() if abbreviation else None,
        )
        return identity, score

    def _parse_scorebox_abbreviations(self, soup: BeautifulSoup) -> tuple[str | None, str | None]:
        """Extract away/home abbreviations from the scorebox."""
        scorebox = soup.find("div", class_="scorebox")
        if not scorebox:
            return None, None

        team_divs = scorebox.find_all("div", recursive=False)
        if len(team_divs) < 2:
            return None, None

        def parse_abbr(div: BeautifulSoup) -> str | None:
            team_link = div.find("a", itemprop="name")
            if not team_link:
                strong = div.find("strong")
                team_link = strong.find("a") if strong else None
            if not team_link:
                return None
            team_name = team_link.text.strip()
            _, abbr = normalize_team_name(self.league_code, team_name)
            return abbr

        away_abbr = parse_abbr(team_divs[0])
        home_abbr = parse_abbr(team_divs[1])
        return away_abbr, home_abbr

    def _parse_pbp_period_marker(self, row: BeautifulSoup) -> int | None:
        """Parse PBP header rows into a normalized period number.

        NCAAB uses halves plus overtime. We map:
        - 1st half => period 1
        - 2nd half => period 2
        - OT => period 3 (or higher for OT2/OT3/etc.)
        """
        row_id = (row.get("id") or "").strip().lower()
        header_text = row.get_text(" ", strip=True).lower()
        marker = " ".join(value for value in (row_id, header_text) if value)
        if not marker:
            return None

        if "1st half" in marker or "first half" in marker or row_id in {"h1", "1st", "first"}:
            return 1
        if "2nd half" in marker or "second half" in marker or row_id in {"h2", "2nd", "second"}:
            return 2

        if "ot" in marker or "overtime" in marker:
            match = self._OT_NUMBER_PATTERN.search(marker)
            if match:
                for group in match.groups():
                    if group:
                        ot_number = parse_int(group)
                        if ot_number:
                            return 2 + ot_number
            return 3

        if row_id.startswith("q") and len(row_id) == 2 and row_id[1].isdigit():
            return int(row_id[1])

        return None

    def _parse_pbp_row(
        self,
        row: BeautifulSoup,
        period: int,
        away_abbr: str | None,
        home_abbr: str | None,
        play_index: int,
    ) -> NormalizedPlay | None:
        """Parse a single NCAAB play-by-play row."""
        cells = row.find_all("td")
        if not cells:
            return None

        game_clock = cells[0].text.strip() or None

        # Colspan rows are neutral plays (e.g. jump ball, end of half).
        if len(cells) == 2:
            description = cells[1].text.strip()
            return NormalizedPlay(
                play_index=play_index,
                quarter=period,
                game_clock=game_clock,
                play_type=None,
                team_abbreviation=None,
                player_id=None,
                player_name=None,
                description=description,
                home_score=None,
                away_score=None,
                raw_data={"full_description": description},
            )

        # Some CBB PBP pages use 4 columns (Time | Away | Score | Home).
        if len(cells) >= 6:
            away_action = cells[1].text.strip()
            score_text = cells[3].text.strip()
            home_action = cells[5].text.strip()
        elif len(cells) >= 4:
            away_action = cells[1].text.strip()
            score_text = cells[2].text.strip()
            home_action = cells[3].text.strip()
        else:
            return None

        description_parts = []
        if away_action:
            description_parts.append(away_action)
        if home_action:
            description_parts.append(home_action)
        description = " | ".join(description_parts) if description_parts else None

        team_abbr = None
        if away_action:
            team_abbr = away_abbr
        elif home_action:
            team_abbr = home_abbr

        away_score = None
        home_score = None
        if score_text and "-" in score_text:
            parts = score_text.split("-")
            if len(parts) == 2:
                away_score = parse_int(parts[0].strip())
                home_score = parse_int(parts[1].strip())

        return NormalizedPlay(
            play_index=play_index,
            quarter=period,
            game_clock=game_clock,
            play_type=None,
            team_abbreviation=team_abbr,
            player_id=None,
            player_name=None,
            description=description,
            home_score=home_score,
            away_score=away_score,
            raw_data={"away_action": away_action, "home_action": home_action, "score": score_text},
        )

    def _extract_team_stats(self, soup: BeautifulSoup, team_identity: TeamIdentity, is_home: bool) -> dict:
        """Extract team totals from NCAAB boxscore tables."""
        return extract_team_stats(soup, team_identity, is_home)

    def _extract_player_stats(
        self, soup: BeautifulSoup, team_identity: TeamIdentity, is_home: bool
    ) -> list[NormalizedPlayerBoxscore]:
        """Extract player stats from NCAAB boxscore page."""
        return extract_player_stats(soup, team_identity, is_home)

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

    def _is_probable_womens_game(
        self,
        href: str,
        source_game_key: str,
        home_team: str,
        away_team: str,
        *,
        is_gender_f: bool = False,
    ) -> tuple[bool, str]:
        """
        Heuristically detect women's games that may appear in the men's scoreboard.
        
        Sports Reference women's pages often include markers like \"-women\"
        or slugs that start with \"w\". We skip these early to avoid persisting
        women's games into the men's NCAAB universe.
        """
        href_lower = href.lower()
        reasons: list[str] = []

        if is_gender_f:
            reasons.append("gender_f_class")
        if "women" in href_lower:
            reasons.append("href_contains_women")
        if "/w-" in href_lower or "-w-" in href_lower:
            reasons.append("href_contains_w_dash")
        if href_lower.endswith("_w.html") or "_w." in href_lower:
            reasons.append("href_suffix_w")
        if source_game_key and not source_game_key[0].isdigit():
            reasons.append("game_key_not_numeric")
        if source_game_key.startswith("w"):
            reasons.append("game_key_starts_with_w")
        if source_game_key.endswith("_w") or source_game_key.endswith("-w"):
            reasons.append("game_key_suffix_w")
        if "women" in home_team.lower() or "women" in away_team.lower():
            reasons.append("team_name_contains_women")

        return (len(reasons) > 0, ",".join(reasons))

    # _season_from_date now inherited from base class

    def fetch_games_for_date(self, day: date) -> Sequence[NormalizedGame]:
        soup = self.fetch_html(self.scoreboard_url(day))
        game_divs = soup.select("div.game_summary")
        logger.info(
            "ncaab_fetch_games_start",
            day=str(day),
            game_divs_count=len(game_divs),
        )
        games: list[NormalizedGame] = []
        skipped_count = 0
        error_count = 0
        for div in game_divs:
            div_classes = div.get("class", [])
            is_gender_f = "gender-f" in div_classes
            team_rows = div.select("table.teams tr")
            if len(team_rows) < 2:
                logger.debug(
                    "ncaab_game_skipped_insufficient_rows",
                    day=str(day),
                    team_rows_count=len(team_rows),
                )
                skipped_count += 1
                continue
            try:
                away_identity, away_score = self._parse_team_row(team_rows[0])
                home_identity, home_score = self._parse_team_row(team_rows[1])
            except ScraperError as exc:
                message = str(exc)
                if message.startswith("score_unavailable_status:"):
                    logger.debug(
                        "ncaab_game_pending",
                        day=str(day),
                        status=message.split(":", 1)[1],
                    )
                    skipped_count += 1
                    continue
                # Treat any invalid/non-numeric score or parse issue as a skipped game, not fatal
                logger.warning(
                    "ncaab_game_parse_error",
                    day=str(day),
                    error=message,
                    exc_info=True,
                )
                skipped_count += 1
                continue

            # Try multiple selectors for boxscore link (HTML structure may vary)
            boxscore_link = (
                div.select_one("p.links a[href*='/boxscores/']") or
                div.select_one("p.links a[href*='boxscores']") or
                div.select_one("a[href*='/boxscores/']") or
                div.select_one("a[href*='boxscores']")
            )
            if not boxscore_link:
                # Log more details about what we found
                links_section = div.select_one("p.links")
                all_links = div.select("a[href]")
                logger.debug(
                    "ncaab_game_skipped_no_boxscore_link",
                    day=str(day),
                    home_team=home_identity.name,
                    away_team=away_identity.name,
                    has_links_section=links_section is not None,
                    links_section_text=links_section.get_text()[:100] if links_section else None,
                    all_links_count=len(all_links),
                    sample_links=[a.get("href", "")[:50] for a in all_links[:3]],
                )
                skipped_count += 1
                continue
            boxscore_href = boxscore_link["href"]
            source_game_key = boxscore_href.split("/")[-1].replace(".html", "")

            is_womens, reason = self._is_probable_womens_game(
                boxscore_href,
                source_game_key,
                home_identity.name,
                away_identity.name,
                is_gender_f=is_gender_f,
            )
            if is_womens:
                logger.info(
                    "ncaab_womens_boxscore_skipped",
                    day=str(day),
                    href=boxscore_href,
                    source_game_key=source_game_key,
                    home_team=home_identity.name,
                    away_team=away_identity.name,
                    reason=reason,
                    gender_f=is_gender_f,
                )
                skipped_count += 1
                continue

            boxscore_url = urljoin(self.base_url, boxscore_href)
            box_soup = self.fetch_html(boxscore_url)

            away_stats = self._extract_team_stats(box_soup, away_identity, is_home=False)
            home_stats = self._extract_team_stats(box_soup, home_identity, is_home=True)

            # Extract player-level stats for both teams
            away_players = self._extract_player_stats(box_soup, away_identity, is_home=False)
            home_players = self._extract_player_stats(box_soup, home_identity, is_home=True)

            total_players = len(away_players) + len(home_players)
            logger.debug(
                "ncaab_game_player_extraction_summary",
                day=str(day),
                home_team=home_identity.name,
                away_team=away_identity.name,
                away_players_count=len(away_players),
                home_players_count=len(home_players),
                total_players=total_players,
                source_game_key=source_game_key,
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
        logger.info(
            "ncaab_fetch_games_complete",
            day=str(day),
            game_divs_count=len(game_divs),
            games_parsed=len(games),
            games_skipped=skipped_count,
            games_error=error_count,
            )
        return games

    def fetch_play_by_play(self, source_game_key: str, game_date: date) -> NormalizedPlayByPlay:
        """Play-by-play is not available from Sports Reference for NCAAB.

        Sports Reference CBB boxscore pages do not include a play-by-play table for many games,
        so we explicitly mark this ingestion path as unsupported to avoid silent no-op runs.
        """
        url = self.pbp_url(source_game_key)
        logger.warning("pbp_unavailable_sportsref", league=self.league_code, game_key=source_game_key, url=url)
        raise NotImplementedError("NCAAB play-by-play is unavailable from Sports Reference.")
