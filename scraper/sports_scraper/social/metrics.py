"""OTel metrics instruments for social scraping.

Instruments are lazily initialized from the global MeterProvider on first use.
When opentelemetry-sdk is not installed or no endpoint is configured, all
functions are no-ops — callers never need to guard against import errors.
"""
from __future__ import annotations

import logging

_logger = logging.getLogger(__name__)

_initialized = False
_scrape_result: object = None


class _Noop:
    """Minimal no-op stand-in for an OTel Counter."""

    def add(self, *args, **kwargs) -> None:  # noqa: ANN002
        pass


_NOOP = _Noop()


def _instruments():
    global _initialized, _scrape_result
    if _initialized:
        return _scrape_result

    _initialized = True
    try:
        from opentelemetry import metrics

        meter = metrics.get_meter("social", version="1.0")
        _scrape_result = meter.create_counter(
            name="social.scrape.result",
            description="Count of social scrape attempts, tagged by outcome and team",
        )
    except ImportError:
        _logger.debug("opentelemetry not available — social metrics are no-ops")
        _scrape_result = _NOOP

    return _scrape_result


def increment_scrape_result(team_id: int, *, success: bool) -> None:
    """Increment social.scrape.result counter for one scrape attempt.

    Args:
        team_id: Database ID of the team whose timeline was scraped.
        success: True if collect_posts() returned without error; False otherwise.
    """
    counter = _instruments()
    counter.add(1, attributes={"success": success, "team_id": str(team_id)})
