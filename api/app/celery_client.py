"""Celery client for scheduling scraper jobs."""

from __future__ import annotations

from functools import lru_cache

from celery import Celery

from .config import settings


@lru_cache(maxsize=1)
def get_celery_app() -> Celery:
    app = Celery(
        "sports-data-admin",
        broker=settings.celery_broker,
        backend=settings.celery_backend,
    )
    app.conf.task_default_queue = settings.celery_default_queue
    app.conf.task_routes = {
        "run_scrape_job": {"queue": "sports-scraper", "routing_key": "sports-scraper"},
    }
    app.conf.task_always_eager = False
    app.conf.task_eager_propagates = True
    return app
