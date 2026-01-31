"""FairBet router bundle."""

from fastapi import APIRouter

from . import odds

router = APIRouter(prefix="/api/fairbet", tags=["fairbet"])
router.include_router(odds.router)

__all__ = ["router"]
