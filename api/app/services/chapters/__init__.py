"""
Book + Chapters Model

A game is a book. Plays are pages. Chapters are contiguous play ranges
that represent coherent scenes.

This module replaces the legacy "Moments" concept with a simpler,
narrative-first architecture.
"""

from .types import Play, Chapter, GameStory, ChapterBoundary
from .builder import build_chapters

__all__ = [
    "Play",
    "Chapter",
    "GameStory",
    "ChapterBoundary",
    "build_chapters",
]
