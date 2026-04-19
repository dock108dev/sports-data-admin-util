"""Admin endpoint: quality score summary (LLM vs template A/B comparison).

GET /api/admin/quality/summary
  Returns p25/p50/p75 quality scores per sport per flow_source for the last
  7 days. Designed for programmatic access; the Grafana panel reads the same
  underlying data directly via PostgreSQL datasource.

Requires admin API key (enforced at router registration level in main.py).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db

logger = logging.getLogger(__name__)

router = APIRouter()

_ALIAS_CFG = ConfigDict(alias_generator=to_camel, populate_by_name=True)

_SUMMARY_SQL = text(
    """
    WITH effective AS (
        SELECT
            sport,
            COALESCE(flow_source, 'LLM') AS flow_source,
            COALESCE(
                quality_score,
                CASE
                    WHEN total_ai_calls = 0 THEN 5.0
                    ELSE LEAST(100.0, GREATEST(0.0,
                        50.0
                        + (COALESCE(block_count, 3) - 3) * 12.5
                        - (total_ai_calls - 1) * 20.0
                    ))
                END
            ) AS eff_score
        FROM sports_game_stories
        WHERE generated_at >= NOW() - INTERVAL '7 days'
          AND generated_at <  NOW()
    )
    SELECT
        sport,
        flow_source,
        ROUND(PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY eff_score)::numeric, 2) AS p25,
        ROUND(PERCENTILE_CONT(0.5)  WITHIN GROUP (ORDER BY eff_score)::numeric, 2) AS p50,
        ROUND(PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY eff_score)::numeric, 2) AS p75,
        COUNT(*)::int AS flow_count
    FROM effective
    GROUP BY sport, flow_source
    ORDER BY sport, flow_source
    """
)


class QualityScoreRow(BaseModel):
    """Per-sport, per-source quality score distribution for the last 7 days."""

    model_config = _ALIAS_CFG

    sport: str
    flow_source: Literal["LLM", "TEMPLATE"]
    p25: float
    p50: float
    p75: float
    flow_count: int


class QualitySummaryResponse(BaseModel):
    """Quality score A/B distribution: LLM vs template flows, last 7 days."""

    model_config = _ALIAS_CFG

    generated_at: datetime
    window_days: int
    rows: list[QualityScoreRow]


@router.get(
    "/quality/summary",
    response_model=QualitySummaryResponse,
    summary="Quality score distribution: LLM vs template (last 7 days)",
    description=(
        "Returns p25/p50/p75 quality scores per sport per `flow_source` "
        "(`LLM` or `TEMPLATE`) for the last 7 days. "
        "Quality score is taken from the stored `quality_score` column when "
        "present; falls back to the derived heuristic "
        "(block_count + total_ai_calls) for older rows. "
        "Admin API key required."
    ),
)
async def get_quality_summary(
    db: AsyncSession = Depends(get_db),
) -> QualitySummaryResponse:
    """Return p25/p50/p75 quality scores per sport/flow_source for the last 7 days."""
    result = await db.execute(_SUMMARY_SQL)
    rows = result.mappings().all()

    return QualitySummaryResponse(
        generated_at=datetime.now(UTC),
        window_days=7,
        rows=[
            QualityScoreRow(
                sport=row["sport"],
                flow_source=row["flow_source"],
                p25=float(row["p25"]),
                p50=float(row["p50"]),
                p75=float(row["p75"]),
                flow_count=int(row["flow_count"]),
            )
            for row in rows
        ],
    )
