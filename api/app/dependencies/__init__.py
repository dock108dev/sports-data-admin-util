"""FastAPI dependencies for the sports-data-admin API."""

from app.dependencies.auth import verify_api_key

__all__ = ["verify_api_key"]
