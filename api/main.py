from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from starlette.responses import JSONResponse

from app.config import settings
from app.db import engine
from app.logging_config import configure_logging
from app.middleware.logging import StructuredLoggingMiddleware
from app.middleware.rate_limit import RateLimitMiddleware
from app.routers import game_snapshots, reading_positions, social, sports
from app.routers.admin import frontend_payload, moments, pbp, pipeline, resolution, timeline_jobs

configure_logging(
    service="sports-data-admin-api",
    environment=settings.environment,
    log_level=settings.log_level,
)

app = FastAPI(title="sports-data-admin", version="1.0.0")
logger = logging.getLogger(__name__)

app.add_middleware(StructuredLoggingMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sports.router)
app.include_router(social.router)
app.include_router(reading_positions.router)
app.include_router(game_snapshots.router)
app.include_router(timeline_jobs.router, prefix="/api/admin/sports", tags=["admin"])
app.include_router(pipeline.router, prefix="/api/admin/sports", tags=["admin", "pipeline"])
app.include_router(pbp.router, prefix="/api/admin/sports", tags=["admin", "pbp"])
app.include_router(moments.router, prefix="/api/admin/sports", tags=["admin", "moments"])
app.include_router(resolution.router, prefix="/api/admin/sports", tags=["admin", "resolution"])
app.include_router(frontend_payload.router, prefix="/api/admin/sports", tags=["admin", "frontend-payload"])


@app.get("/healthz")
async def healthcheck() -> JSONResponse:
    components: dict[str, str] = {"app": "ok", "db": "ok"}

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        logger.exception("Healthcheck database connectivity failed.")
        components["db"] = "error"

    status = "ok" if components["db"] == "ok" else "unhealthy"
    payload: dict[str, str] = {"status": status, **components}
    if status != "ok":
        payload["error"] = "database unavailable"
        return JSONResponse(payload, status_code=503)
    return JSONResponse(payload)
