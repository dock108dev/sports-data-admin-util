"""Sports admin router bundle."""

from fastapi import APIRouter

from . import diagnostics, games, jobs, scraper_runs, story, teams

router = APIRouter(prefix="/api/admin/sports", tags=["sports-data"])
router.include_router(scraper_runs.router)
router.include_router(games.router)
router.include_router(teams.router)
router.include_router(jobs.router)
router.include_router(diagnostics.router)
router.include_router(story.router)

__all__ = ["router"]
