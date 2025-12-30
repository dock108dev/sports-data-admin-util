from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.middleware.logging import StructuredLoggingMiddleware
from app.middleware.rate_limit import RateLimitMiddleware
from app.routers import sports, social

app = FastAPI(title="sports-data-admin", version="1.0.0")

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


@app.get("/healthz")
async def healthcheck() -> dict[str, str]:
    return {"status": "ok"}

