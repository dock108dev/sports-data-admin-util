"""OTel metrics instruments for Odds API credit tracking.

Instruments are lazily initialized from the global MeterProvider on first use.
When opentelemetry-sdk is not installed or no endpoint is configured, all
functions are no-ops — callers never need to guard against import errors.
"""
from __future__ import annotations

import logging

_logger = logging.getLogger(__name__)
_initialized = False


def _instruments() -> None:
    global _initialized
    if _initialized:
        return

    _initialized = True
    try:
        from opentelemetry import metrics
        from opentelemetry.metrics import Observation

        meter = metrics.get_meter("odds", version="1.0")

        def _credits_today_callback(_options):
            from ..utils.odds_quota import get_daily_usage
            yield Observation(get_daily_usage())

        def _budget_weekly_callback(_options):
            from ..utils.odds_quota import get_weekly_cap
            yield Observation(get_weekly_cap())

        meter.create_observable_gauge(
            name="odds.api.credits_used_today",
            description="Odds API credits consumed today (UTC calendar day)",
            callbacks=[_credits_today_callback],
            unit="1",
        )
        meter.create_observable_gauge(
            name="odds.api.credits_budget_weekly",
            description="Configured weekly Odds API credit budget",
            callbacks=[_budget_weekly_callback],
            unit="1",
        )
    except ImportError:
        _logger.debug("opentelemetry not available — odds metrics are no-ops")


def init_odds_metrics() -> None:
    """Register Odds API OTel gauge instruments. Call once after telemetry is set up."""
    _instruments()
