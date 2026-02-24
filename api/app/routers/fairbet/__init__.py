"""FairBet router bundle."""

from fastapi import APIRouter

from . import odds, parlay

router = APIRouter(prefix="/api/fairbet", tags=["fairbet"])
router.include_router(odds.router)
router.include_router(parlay.router)

__all__ = ["router"]
