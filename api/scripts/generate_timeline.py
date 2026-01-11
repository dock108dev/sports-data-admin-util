from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.config import settings
from app.db import get_async_session
from app.logging_config import configure_logging
from app.services.timeline_generator import TimelineGenerationError, generate_timeline_artifact

logger = logging.getLogger(__name__)


async def _run(game_id: int, timeline_version: str) -> None:
    async with get_async_session() as session:
        await generate_timeline_artifact(session, game_id, timeline_version=timeline_version)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a finalized NBA timeline artifact.")
    parser.add_argument("game_id", type=int, help="Game ID for the finalized NBA game.")
    parser.add_argument(
        "--timeline-version",
        default="v1",
        help="Timeline artifact version identifier.",
    )
    return parser.parse_args()


def main() -> None:
    configure_logging(
        service="sports-data-admin-cli",
        environment=settings.environment,
        log_level=settings.log_level,
    )
    args = _parse_args()

    logger.info(
        "timeline_generation_cli_started",
        extra={"game_id": args.game_id, "timeline_version": args.timeline_version},
    )
    try:
        asyncio.run(_run(args.game_id, args.timeline_version))
    except TimelineGenerationError as exc:
        logger.error(
            "timeline_generation_cli_failed",
            extra={
                "game_id": args.game_id,
                "timeline_version": args.timeline_version,
                "error": str(exc),
            },
        )
        raise SystemExit(1) from exc
    except Exception:
        logger.exception(
            "timeline_generation_cli_failed",
            extra={"game_id": args.game_id, "timeline_version": args.timeline_version},
        )
        raise SystemExit(1)

    logger.info(
        "timeline_generation_cli_completed",
        extra={"game_id": args.game_id, "timeline_version": args.timeline_version},
    )


if __name__ == "__main__":
    main()
