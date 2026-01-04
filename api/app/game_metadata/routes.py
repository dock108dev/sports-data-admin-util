"""API routes for game metadata."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/game-metadata", tags=["game-metadata"])
