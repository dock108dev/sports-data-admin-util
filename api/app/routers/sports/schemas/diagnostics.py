"""Diagnostic and job-related Pydantic schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class JobRunResponse(BaseModel):
    """Job run response with camelCase output."""

    model_config = ConfigDict(populate_by_name=True)

    id: int
    phase: str
    leagues: list[str]
    status: str
    started_at: datetime = Field(..., alias="startedAt")
    finished_at: datetime | None = Field(None, alias="finishedAt")
    duration_seconds: float | None = Field(None, alias="durationSeconds")
    error_summary: str | None = Field(None, alias="errorSummary")
    summary_data: dict[str, Any] | None = Field(None, alias="summaryData")
    celery_task_id: str | None = Field(None, alias="celeryTaskId")
    created_at: datetime = Field(..., alias="createdAt")


class MissingPbpEntry(BaseModel):
    """Missing PBP entry with camelCase output."""

    model_config = ConfigDict(populate_by_name=True)

    game_id: int = Field(..., alias="gameId")
    league_code: str = Field(..., alias="leagueCode")
    status: str
    reason: str
    detected_at: datetime = Field(..., alias="detectedAt")
    updated_at: datetime = Field(..., alias="updatedAt")


class GameConflictEntry(BaseModel):
    """Game conflict entry with camelCase output."""

    model_config = ConfigDict(populate_by_name=True)

    league_code: str = Field(..., alias="leagueCode")
    game_id: int = Field(..., alias="gameId")
    conflict_game_id: int = Field(..., alias="conflictGameId")
    external_id: str = Field(..., alias="externalId")
    source: str
    conflict_fields: dict[str, Any] = Field(..., alias="conflictFields")
    created_at: datetime = Field(..., alias="createdAt")
    resolved_at: datetime | None = Field(None, alias="resolvedAt")
