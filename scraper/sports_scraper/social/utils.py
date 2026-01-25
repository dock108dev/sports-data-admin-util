"""Shared helpers for social ingestion."""

from __future__ import annotations

import re


STATUS_ID_PATTERN = re.compile(r"/status/(\d+)")


def extract_x_post_id(url: str | None) -> str | None:
    if not url:
        return None
    match = STATUS_ID_PATTERN.search(url)
    return match.group(1) if match else None
