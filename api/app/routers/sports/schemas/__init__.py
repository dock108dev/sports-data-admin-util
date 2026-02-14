"""Pydantic schemas for sports admin endpoints.

Re-exports all models from domain-grouped sub-modules for backward compatibility.
"""

from .common import (
    GamePhase,
    NHLDataHealth,
    NHLGoalieStat,
    NHLSkaterStat,
    OddsEntry,
    PlayEntry,
    PlayerStat,
    SocialPostEntry,
    TeamStat,
    TieredPlayGroup,
)
from .diagnostics import GameConflictEntry, JobRunResponse, MissingPbpEntry
from .game_flow import (
    BlockMiniBox,
    GameFlowBlock,
    GameFlowContent,
    GameFlowMoment,
    GameFlowPlay,
    GameFlowResponse,
    MomentBoxScore,
    MomentGoalieStat,
    MomentPlayerStat,
    MomentTeamBoxScore,
    TimelineArtifactResponse,
)
from .games import (
    GameDetailResponse,
    GameListResponse,
    GameMeta,
    GamePreviewScoreResponse,
    GameSummary,
    JobResponse,
)
from .scraper import ScrapeRunConfig, ScrapeRunCreateRequest, ScrapeRunResponse
from .teams import (
    TeamColorUpdate,
    TeamDetail,
    TeamGameSummary,
    TeamListResponse,
    TeamSocialInfo,
    TeamSummary,
    _HEX_COLOR_RE,
    _validate_hex_color,
)

__all__ = [
    # common
    "GamePhase",
    "NHLDataHealth",
    "NHLGoalieStat",
    "NHLSkaterStat",
    "OddsEntry",
    "PlayEntry",
    "PlayerStat",
    "SocialPostEntry",
    "TeamStat",
    "TieredPlayGroup",
    # diagnostics
    "GameConflictEntry",
    "JobRunResponse",
    "MissingPbpEntry",
    # game_flow
    "BlockMiniBox",
    "GameFlowBlock",
    "GameFlowContent",
    "GameFlowMoment",
    "GameFlowPlay",
    "GameFlowResponse",
    "MomentBoxScore",
    "MomentGoalieStat",
    "MomentPlayerStat",
    "MomentTeamBoxScore",
    "TimelineArtifactResponse",
    # games
    "GameDetailResponse",
    "GameListResponse",
    "GameMeta",
    "GamePreviewScoreResponse",
    "GameSummary",
    "JobResponse",
    # scraper
    "ScrapeRunConfig",
    "ScrapeRunCreateRequest",
    "ScrapeRunResponse",
    # teams
    "TeamColorUpdate",
    "TeamDetail",
    "TeamGameSummary",
    "TeamListResponse",
    "TeamSocialInfo",
    "TeamSummary",
    "_HEX_COLOR_RE",
    "_validate_hex_color",
]
