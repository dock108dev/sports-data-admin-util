"""Docker container log viewer endpoint."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

import httpx

logger = logging.getLogger(__name__)

router = APIRouter()

ALLOWED_CONTAINERS: set[str] = {
    "sports-api",
    "sports-api-worker",
    "sports-scraper",
    "sports-social-scraper",
}

DOCKER_SOCKET_PATH = "/var/run/docker.sock"


class DockerLogsResponse(BaseModel):
    container: str
    lines: int
    logs: str


def _strip_docker_frame_headers(raw: bytes) -> str:
    """Strip 8-byte Docker stream multiplexing frame headers.

    The Docker Engine API returns log output with an 8-byte header per frame:
      - byte 0: stream type (0=stdin, 1=stdout, 2=stderr)
      - bytes 1-3: padding
      - bytes 4-7: payload size (big-endian uint32)
    """
    result: list[str] = []
    offset = 0
    while offset + 8 <= len(raw):
        size = int.from_bytes(raw[offset + 4 : offset + 8], "big")
        if offset + 8 + size > len(raw):
            break
        payload = raw[offset + 8 : offset + 8 + size]
        result.append(payload.decode("utf-8", errors="replace"))
        offset += 8 + size

    # If we couldn't parse any frames, fall back to raw decode (plain text logs)
    if not result and raw:
        return raw.decode("utf-8", errors="replace")

    return "".join(result)


@router.get("/scraper/logs", response_model=DockerLogsResponse)
async def get_docker_logs(
    container: str = Query(..., description="Container name"),
    lines: int = Query(1000, ge=1, le=10000, description="Number of tail lines"),
) -> DockerLogsResponse:
    """Fetch recent logs from an allowed Docker container."""
    if container not in ALLOWED_CONTAINERS:
        raise HTTPException(
            status_code=400,
            detail=f"Container '{container}' is not in the allow list. "
            f"Allowed: {', '.join(sorted(ALLOWED_CONTAINERS))}",
        )

    docker_url = (
        f"http://localhost/containers/{container}/logs"
        f"?stdout=1&stderr=1&tail={lines}&timestamps=1"
    )

    try:
        transport = httpx.AsyncHTTPTransport(uds=DOCKER_SOCKET_PATH)
        async with httpx.AsyncClient(transport=transport, timeout=10.0) as client:
            resp = await client.get(docker_url)
    except (OSError, httpx.ConnectError) as exc:
        logger.warning("Docker socket unavailable: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="Docker socket is not available. Is the socket mounted?",
        )

    if resp.status_code == 404:
        raise HTTPException(
            status_code=404,
            detail=f"Container '{container}' not found. Is it running?",
        )

    if resp.status_code != 200:
        logger.error(
            "Docker API error %s for container %s: %s",
            resp.status_code,
            container,
            resp.text,
        )
        raise HTTPException(
            status_code=502,
            detail=f"Docker API returned status {resp.status_code}",
        )

    log_text = _strip_docker_frame_headers(resp.content)

    return DockerLogsResponse(
        container=container,
        lines=lines,
        logs=log_text,
    )
