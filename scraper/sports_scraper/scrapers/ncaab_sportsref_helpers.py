"""Helper functions for NCAAB sports-reference scraping."""

from __future__ import annotations

from bs4 import BeautifulSoup

from ..logging import logger
from ..models import NormalizedPlayerBoxscore, TeamIdentity
from ..utils.html_parsing import extract_team_stats_from_table
from ..utils import extract_all_stats_from_row, get_stat_from_row, parse_float, parse_int


def extract_team_stats(soup: BeautifulSoup, team_identity: TeamIdentity, is_home: bool) -> dict:
    """Extract team totals from NCAAB boxscore tables (no abbreviations provided)."""
    import re

    def _slugify(name: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
        return slug

    target_slug = _slugify(team_identity.name)
    alt_slug = target_slug.replace("-state", "").replace("-university", "").replace("st-", "")
    candidates = {target_slug, alt_slug}

    tables = [t for t in soup.find_all("table", id=True) if t.get("id", "").startswith("box-score-basic-")]
    matched_table = None
    for table in tables:
        table_id = table.get("id", "").lower()
        table_slug = table_id.split("box-score-basic-", 1)[1]
        if any(candidate and (candidate in table_slug or table_slug in candidate) for candidate in candidates):
            matched_table = table
            break

    if matched_table is None and tables:
        matched_table = tables[1] if (is_home and len(tables) > 1) else tables[0]

    if matched_table is None:
        logger.warning(
            "ncaab_team_stats_table_not_found",
            team=team_identity.name,
            is_home=is_home,
            available_tables=[t.get("id") for t in tables][:5],
        )
        return {}

    stats = extract_team_stats_from_table(matched_table, team_identity.name, matched_table.get("id", ""))

    parsed: dict[str, int | float | str] = {}
    for key, value in stats.items():
        if value in (None, ""):
            continue
        parsed_int = parse_int(value)
        if parsed_int is not None:
            parsed[key] = parsed_int
            continue
        parsed_float = parse_float(value)
        if parsed_float is not None:
            parsed[key] = parsed_float
            continue
        parsed[key] = value
    return parsed


def find_player_table_by_position(
    soup: BeautifulSoup, team_identity: TeamIdentity, is_home: bool
) -> BeautifulSoup.Tag | None:
    """Find player stats table for NCAAB when abbreviations are not available."""
    all_tables = soup.find_all("table", id=True)
    all_table_ids = [t.get("id", "") for t in all_tables if t.get("id")]
    player_tables = [t for t in all_tables if t.get("id", "").startswith("box-score-basic-")]

    logger.debug(
        "ncaab_player_table_search",
        team=team_identity.name,
        is_home=is_home,
        total_tables_with_ids=len(all_table_ids),
        player_tables_found=len(player_tables),
        player_table_ids=[t.get("id") for t in player_tables],
        sample_table_ids=all_table_ids[:10],
    )

    if not player_tables:
        logger.warning(
            "ncaab_player_table_not_found_by_pattern",
            team=team_identity.name,
            is_home=is_home,
            all_table_ids=all_table_ids[:20],
        )
        return None

    team_name_lower = team_identity.name.lower()
    team_name_normalized = team_name_lower.replace(" ", "_").replace("-", "_").replace(".", "").replace("'", "")
    team_name_no_suffix = (
        team_name_normalized.replace("_state", "").replace("_st", "").replace("_university", "").replace("_u", "")
    )

    for table in player_tables:
        table_id = table.get("id", "").lower()
        if "box-score-basic-" in table_id:
            table_team_name = table_id.split("box-score-basic-", 1)[1]
            if (
                team_name_normalized in table_team_name
                or table_team_name in team_name_normalized
                or team_name_no_suffix in table_team_name
                or table_team_name in team_name_no_suffix
                or team_name_lower.replace(" ", "") in table_team_name
                or table_team_name in team_name_lower.replace(" ", "")
            ):
                logger.debug(
                    "ncaab_player_table_found_by_id",
                    team=team_identity.name,
                    is_home=is_home,
                    table_id=table.get("id"),
                    table_team_name=table_team_name,
                    matched_pattern=team_name_normalized,
                )
                return table

    if len(player_tables) >= 2:
        table_index = 1 if is_home else 0
        if table_index < len(player_tables):
            table = player_tables[table_index]
            logger.debug(
                "ncaab_player_table_found_by_position",
                team=team_identity.name,
                is_home=is_home,
                table_id=table.get("id"),
                position=table_index,
            )
            return table

    for table in player_tables:
        caption = table.find("caption")
        if caption and team_identity.name.lower() in caption.get_text().lower():
            logger.debug(
                "ncaab_player_table_found_by_caption",
                team=team_identity.name,
                is_home=is_home,
                table_id=table.get("id"),
            )
            return table

        thead = table.find("thead")
        if thead:
            thead_text = thead.get_text().lower()
            if team_identity.name.lower() in thead_text:
                logger.debug(
                    "ncaab_player_table_found_by_thead",
                    team=team_identity.name,
                    is_home=is_home,
                    table_id=table.get("id"),
                )
                return table

    if player_tables:
        table_index = 1 if is_home else 0
        if table_index < len(player_tables):
            logger.debug(
                "ncaab_player_table_using_fallback_position",
                team=team_identity.name,
                is_home=is_home,
                table_id=player_tables[table_index].get("id"),
                total_tables=len(player_tables),
            )
            return player_tables[table_index]

    return None


def extract_player_stats(
    soup: BeautifulSoup, team_identity: TeamIdentity, is_home: bool
) -> list[NormalizedPlayerBoxscore]:
    """Extract player stats from NCAAB boxscore page."""
    table = find_player_table_by_position(soup, team_identity, is_home)

    if not table:
        logger.warning(
            "ncaab_player_stats_table_not_found",
            team=team_identity.name,
            is_home=is_home,
        )
        return []

    table_id = table.get("id", "unknown")
    logger.debug(
        "ncaab_player_stats_table_found",
        team=team_identity.name,
        is_home=is_home,
        table_id=table_id,
    )

    players: list[NormalizedPlayerBoxscore] = []
    tbody = table.find("tbody")
    if not tbody:
        logger.warning(
            "ncaab_player_stats_tbody_not_found",
            table_id=table_id,
            team=team_identity.name,
        )
        return players

    all_rows = tbody.find_all("tr")
    logger.debug(
        "ncaab_player_stats_rows_found",
        table_id=table_id,
        team=team_identity.name,
        row_count=len(all_rows),
    )

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
                minutes=parse_float(get_stat_from_row(row, "mp")),
                points=parse_int(get_stat_from_row(row, "pts")),
                rebounds=parse_int(get_stat_from_row(row, "trb")),
                assists=parse_int(get_stat_from_row(row, "ast")),
                raw_stats=raw_stats,
            )
        )
        parsed_count += 1

    logger.info(
        "ncaab_player_stats_extraction_complete",
        team=team_identity.name,
        is_home=is_home,
        total_rows=len(all_rows),
        skipped_thead=skipped_thead,
        skipped_no_player_cell=skipped_no_player_cell,
        skipped_no_player_link=skipped_no_player_link,
        parsed_players=parsed_count,
    )

    return players
