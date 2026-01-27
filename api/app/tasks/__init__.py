"""Background tasks for sports data admin."""

from .bulk_story_generation import run_bulk_story_generation

__all__ = ["run_bulk_story_generation"]
