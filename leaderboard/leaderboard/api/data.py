from typing import Any, Dict, List

from pydantic import BaseModel, Field


class PingResponse(BaseModel):
    status: str


class VersionResponse(BaseModel):
    version: str


class LeaderboardResponse(BaseModel):
    leaderboard_id: str
    short_name: str


class GuildChannelResponse(BaseModel):
    id: str
    name: str
    leaderboards: List[LeaderboardResponse] = Field(default_factory=list)


class GuildResponse(BaseModel):
    id: str
    name: str
    channels: List[GuildChannelResponse] = Field(default_factory=list)


class GuildsResponse(BaseModel):
    guilds: List[GuildResponse] = Field(default_factory=list)
